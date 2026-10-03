import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from homelab.config import ConfigError, ROOT, load_json
from homelab.privatefs import (atomic_json, create_private_directory, operation_lock,
                               read_private, safe_path, verify_private)
from homelab.sandbox import apply, make_plan, public_plan, retire, status, validate_plan


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='homelab phase3 ')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / 'installation'
        self.data = self.base / 'data'
        self.backup = self.base / 'backup'
        self.plan = make_plan(self.root, self.data, self.backup)

    def execute(self, **kwargs):
        return apply(self.plan, self.plan['plan_id'], **kwargs)

    def test_plan_is_deterministic_redacted_and_noop(self):
        self.assertEqual(self.plan, make_plan(self.root, self.data, self.backup))
        self.assertEqual(list(self.base.iterdir()), [])
        self.assertNotIn(str(self.base), json.dumps(public_plan(self.plan)))
        self.assertFalse(self.plan['docker'])
        self.assertFalse(self.plan['network'])

    def test_reject_confirmation_before_mutation(self):
        with self.assertRaises(ConfigError):
            apply(self.plan, 'wrong')
        self.assertEqual(list(self.base.iterdir()), [])

    def test_modified_plan_rejected(self):
        changed = copy.deepcopy(self.plan)
        changed['operations'].append('unapproved-operation')
        with self.assertRaises(ConfigError):
            apply(changed, changed['plan_id'])
        self.assertEqual(list(self.base.iterdir()), [])

    def test_phase2_application_plan_rejected(self):
        with self.assertRaises(ConfigError):
            validate_plan({'kind': 'homelab-review-plan'})

    def test_occupied_storage_preflight_does_not_create_root(self):
        self.data.mkdir()
        sentinel = self.data / 'existing.txt'
        sentinel.write_text('preserve')
        with self.assertRaises(ConfigError):
            self.execute()
        self.assertFalse(self.root.exists())
        self.assertEqual(sentinel.read_text(), 'preserve')

    def test_even_empty_unowned_installation_is_refused(self):
        create_private_directory(self.root)
        with self.assertRaises((ConfigError, OSError)):
            self.execute()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_paths_overlap_and_repository_forbidden(self):
        for root, data, backup in ((self.root, self.root / 'data', self.backup),
                                   (ROOT / 'runtime', self.data, self.backup)):
            with self.assertRaises(ConfigError):
                make_plan(root, data, backup)

    def test_missing_parent_forbidden(self):
        with self.assertRaises(ConfigError):
            make_plan(self.root / 'nested', self.data, self.backup)

    def test_new_storage_owner_permissions(self):
        self.execute()
        for directory in (self.root, self.data, self.backup):
            verify_private(directory, directory=True)
            for file in directory.iterdir():
                verify_private(file)

    def test_apply_retry_is_content_and_journal_idempotent(self):
        first = self.execute()
        files = {file: (file.read_bytes(), file.stat().st_mtime_ns) for directory in (self.root, self.data, self.backup)
                 for file in directory.iterdir()}
        self.assertEqual(self.execute(), first)
        self.assertEqual(status(self.plan), first)
        for file, evidence in files.items():
            self.assertEqual((file.read_bytes(), file.stat().st_mtime_ns), evidence)

    def test_operation_boundary_interruptions_resume(self):
        for boundary in ('storage', 'secret', 'content', 'activation'):
            with self.subTest(boundary=boundary):
                # Separate owned roots for each transaction scenario.
                self.root = self.base / (boundary + '-installation')
                self.data = self.base / (boundary + '-data')
                self.backup = self.base / (boundary + '-backup')
                self.plan = make_plan(self.root, self.data, self.backup)
                def interrupt(name):
                    if name == boundary:
                        raise KeyboardInterrupt
                with self.assertRaises(KeyboardInterrupt):
                    self.execute(checkpoint=interrupt)
                secret_path = self.root / 'secret.json'
                before = secret_path.read_bytes() if secret_path.exists() else None
                self.assertEqual(self.execute()['status'], 'ready')
                if before is not None:
                    self.assertEqual(secret_path.read_bytes(), before)

    def test_dependency_failure_stops_later_steps(self):
        with patch('homelab.sandbox.secret_file', side_effect=ConfigError('synthetic dependency failure')):
            with self.assertRaises(ConfigError):
                self.execute()
        self.assertFalse((self.data / 'synthetic.json').exists())
        self.assertFalse((self.root / 'active.json').exists())
        self.assertEqual(self.execute()['status'], 'ready')

    def test_missing_secret_is_not_regenerated(self):
        self.execute()
        (self.root / 'secret.json').unlink()  # Synthetic fixture only.
        with self.assertRaises(ConfigError):
            self.execute()
        self.assertFalse((self.root / 'secret.json').exists())

    def test_secret_and_content_tampering_preserved_and_refused(self):
        self.execute()
        content = self.data / 'synthetic.json'
        old = content.read_bytes()
        content.write_text('{"foreign":true}')
        with self.assertRaises(ConfigError):
            self.execute()
        self.assertEqual(content.read_text(), '{"foreign":true}')
        content.write_bytes(old)
        secret = self.root / 'secret.json'
        value = load_json(secret)
        value['token'] = 'a' * 64
        secret.write_text(json.dumps(value))
        with self.assertRaises(ConfigError):
            self.execute()
        self.assertEqual(load_json(secret)['token'], 'a' * 64)

    def test_foreign_storage_marker_blocks_retry(self):
        self.execute()
        marker = self.data / 'owner.json'
        value = load_json(marker)
        value['owner'] = '0' * 32
        marker.write_text(json.dumps(value))
        with self.assertRaises(ConfigError):
            self.execute()

    def test_journal_transition_tampering_is_refused(self):
        self.execute()
        state = self.root / 'state.json'
        value = load_json(state)
        value['events'].reverse()
        state.write_text(json.dumps(value))
        with self.assertRaises(ConfigError):
            self.execute()

    def test_pending_atomic_file_blocks_and_is_retained(self):
        self.execute()
        residue = self.root / '.pending-interrupted'
        residue.write_text('synthetic residue')
        with self.assertRaisesRegex(ConfigError, 'Interrupted atomic'):
            self.execute()
        self.assertEqual(residue.read_text(), 'synthetic residue')

    def test_non_destructive_retirement_and_interruption(self):
        self.execute()
        secret = (self.root / 'secret.json').read_bytes()
        data = (self.data / 'synthetic.json').read_bytes()
        def interrupt(_):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            retire(self.plan, self.plan['plan_id'], checkpoint=interrupt)
        self.assertEqual(retire(self.plan, self.plan['plan_id'])['status'], 'retired')
        self.assertEqual(status(self.plan)['status'], 'retired')
        self.assertEqual(retire(self.plan, self.plan['plan_id'])['status'], 'retired')
        self.assertFalse((self.root / 'active.json').exists())
        self.assertEqual((self.root / 'secret.json').read_bytes(), secret)
        self.assertEqual((self.data / 'synthetic.json').read_bytes(), data)
        with self.assertRaises(ConfigError):
            self.execute()

    def test_retire_refuses_unknown_activation(self):
        self.execute()
        active = self.root / 'active.json'
        active.write_text('{"not-owned":true}')
        with self.assertRaises(ConfigError):
            retire(self.plan, self.plan['plan_id'])
        self.assertTrue(active.exists())

    def test_lock_exclusion_and_release_on_process_death(self):
        self.execute()
        script = ('from pathlib import Path; from homelab.privatefs import operation_lock; import sys; '
                  'lock=operation_lock(Path(sys.argv[1])); lock.__enter__(); print("locked",flush=True); sys.stdin.read()')
        child = subprocess.Popen([sys.executable, '-c', script, str(self.root / 'operation.lock')], cwd=ROOT,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'locked')
            with self.assertRaises(ConfigError):
                self.execute()
            child.kill()  # Exact test child; OS must release its lock without deleting the file.
            child.wait(timeout=10)
            self.assertEqual(self.execute()['status'], 'ready')
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)

    def test_hardlinks_refused(self):
        create_private_directory(self.root)
        atomic_json(self.root / 'original.json', {'test': True})
        os.link(self.root / 'original.json', self.root / 'alias.json')
        with self.assertRaises(ConfigError):
            read_private(self.root / 'alias.json')

    def test_failed_atomic_replace_preserves_previous_state(self):
        create_private_directory(self.root)
        target = self.root / 'sample.json'
        atomic_json(target, {'revision': 1})
        with patch('homelab.privatefs.os.replace', side_effect=OSError('synthetic write failure')):
            with self.assertRaises(OSError):
                atomic_json(target, {'revision': 2}, replace=True)
        self.assertEqual(read_private(target), {'revision': 1})
        self.assertEqual(len(list(self.root.glob('.pending-*'))), 1)

    def test_hard_exit_after_secret_reuses_credential(self):
        planfile = self.base / 'review.json'
        planfile.write_text(json.dumps(self.plan))
        script = ('import os,sys; from pathlib import Path; from homelab.config import load_json; '
                  'from homelab.sandbox import apply; p=load_json(Path(sys.argv[1])); '
                  'apply(p,p["plan_id"],checkpoint=lambda step: os._exit(75) if step=="secret" else None)')
        child = subprocess.run([sys.executable, '-c', script, str(planfile)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(child.returncode, 75)
        credential = (self.root / 'secret.json').read_bytes()
        self.assertFalse((self.data / 'synthetic.json').exists())
        self.assertEqual(self.execute()['status'], 'ready')
        self.assertEqual((self.root / 'secret.json').read_bytes(), credential)

    @unittest.skipUnless(os.name == 'nt', 'Windows DACL test; POSIX mode test is separate')
    def test_windows_acl_rejects_added_reader(self):
        create_private_directory(self.root)
        path = self.root / 'sample.json'
        atomic_json(path, {'synthetic': True})
        script = r'''
$ErrorActionPreference='Stop'
$path=[Console]::In.ReadToEnd()
$acl=[IO.File]::GetAccessControl($path)
$sid=[Security.Principal.SecurityIdentifier]::new('S-1-1-0')
$acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid,'Read','Allow'))
[IO.File]::SetAccessControl($path,$acl)
'''
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                input=str(path), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, 'Synthetic DACL modification failed')
        with self.assertRaises(ConfigError):
            verify_private(path)

    def test_symlink_guard(self):
        with patch('homelab.privatefs.Path.is_symlink', return_value=True):
            with self.assertRaises(ConfigError):
                safe_path(self.root)

    @unittest.skipIf(os.name == 'nt', 'POSIX mode test; Windows uses actual ACL validation above')
    def test_permission_drift_refused_not_repaired(self):
        self.execute()
        (self.root / 'secret.json').chmod(0o644)
        with self.assertRaises(ConfigError):
            self.execute()
        self.assertEqual((self.root / 'secret.json').stat().st_mode & 0o777, 0o644)

    def test_cli_never_displays_secret_values(self):
        planfile = self.base / 'review.json'
        planfile.write_text(json.dumps(self.plan))
        command = [sys.executable, '-m', 'homelab', 'sandbox', 'apply', '--plan', str(planfile), '--confirm', self.plan['plan_id']]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        secret = load_json(self.root / 'secret.json')['token']
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertNotIn(str(self.base), result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'ready')


if __name__ == '__main__':
    unittest.main()
