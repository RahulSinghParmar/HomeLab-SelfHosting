"""Encrypted Paperless restic vault contracts."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from homelab import paperless_vault as v
from homelab.config import ConfigError
from homelab.privatefs import atomic_json, read_private, windows_acl


TOOL = {'path': '<restic>', 'version': '0.19.1', 'sha256': 'a' * 64,
        'archive_sha256': 'b' * 64}


class PaperlessVaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab paperless vault ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        first, second = self.base / 'operational', self.base / 'recovery'
        first.mkdir()
        second.mkdir()
        self.password = first / 'password.txt'
        self.recovery = second / 'password.txt'
        for path in (self.password, self.recovery):
            path.write_text('x' * 64 + '\n', encoding='ascii')
            if os.name == 'nt':
                windows_acl(path, create=True)
            else:
                path.chmod(0o600)
        self.binary = self.base / ('restic.exe' if os.name == 'nt' else 'restic')
        self.binary.write_bytes(b'x')
        self.tool = {**TOOL, 'path': str(self.binary)}
        self.patch_tool = patch.object(v, 'validate_tool', return_value=self.tool)
        self.patch_tool.start()
        self.addCleanup(self.patch_tool.stop)
        self.plan = v.make_plan(self.base / 'state', self.base / 'repository', self.password,
                                self.recovery, self.binary)
        self.manifest = {'inventory': {'documents': 1, 'rows': [{
            'title': 'Fixture', 'checksum': 'f' * 64, 'file_sha256': 'f' * 64,
            'original_filename': 'fixture.pdf', 'tags': ['phase5-recovery'],
            'content_marker': True}]},
                         'summary': None}
        self.manifest['summary'] = v.backup_summary(self.manifest)

    def initialize(self):
        with patch.object(v, '_restic', return_value=''), \
                patch.object(v, '_repository_id', return_value='c' * 64):
            return v.initialize(self.plan, self.plan['plan_id'])

    def test_plan_is_deterministic_and_contains_no_key_material(self):
        same = v.make_plan(self.base / 'state', self.base / 'repository', self.password,
                           self.recovery, self.binary)
        self.assertEqual(self.plan, same)
        self.assertEqual(self.plan['retention'], {'daily': 7, 'weekly': 4, 'monthly': 3})
        self.assertFalse(self.plan['off_host_verified'])
        self.assertNotIn('x' * 32, json.dumps(self.plan))

    def test_key_files_must_match_and_use_separate_directories(self):
        same_directory = self.password.parent / 'copy.txt'
        same_directory.write_text('x' * 64 + '\n', encoding='ascii')
        if os.name == 'nt':
            windows_acl(same_directory, create=True)
        else:
            same_directory.chmod(0o600)
        with self.assertRaises(ConfigError):
            v.validate_key_custody(self.password, same_directory)
        self.recovery.write_text('y' * 64 + '\n', encoding='ascii')
        if os.name == 'nt':
            windows_acl(self.recovery, create=True)
        with self.assertRaises(ConfigError):
            v.validate_key_custody(self.password, self.recovery)

    def test_key_generation_is_confirmation_gated_and_never_returns_secret(self):
        first, second = self.base / 'generated-operational', self.base / 'generated-recovery'
        first.mkdir()
        second.mkdir()
        operational, recovery = first / 'key.txt', second / 'key.txt'
        with self.assertRaises(ConfigError):
            v.create_keys(operational, recovery, 'wrong')
        self.assertFalse(operational.exists())
        result = v.create_keys(operational, recovery, 'CREATE-PAPERLESS-RECOVERY-KEY')
        self.assertFalse(result['secret_displayed'])
        self.assertEqual(operational.read_bytes(), recovery.read_bytes())
        self.assertNotIn(operational.read_text(encoding='ascii').strip(), json.dumps(result))

    def test_confirmation_precedes_validation_or_mutation(self):
        with patch.object(v, 'validate_plan') as validate, self.assertRaises(ConfigError):
            v.initialize(self.plan, 'wrong')
        validate.assert_not_called()

    def test_initialize_records_repository_identity_without_secret(self):
        result = self.initialize()
        self.assertTrue(result['encrypted'])
        state = read_private(Path(self.plan['state_root']) / 'state.json')
        self.assertEqual(state['repository_id'], 'c' * 64)
        self.assertEqual(state['status'], 'ready')
        self.assertNotIn('x' * 32, json.dumps(state))

    def test_snapshot_store_binds_verified_manifest(self):
        self.initialize()
        source = self.base / 'application-backup'
        source.mkdir()
        with patch.object(v, '_repository_id', return_value='c' * 64), \
                patch.object(v, 'verify_backup', return_value=self.manifest):
            snapshot = v.make_snapshot_plan(self.plan, source)
            output = json.dumps({'message_type': 'summary', 'snapshot_id': 'd' * 64})
            with patch.object(v, '_restic', return_value=output):
                result = v.store(self.plan, snapshot, snapshot['snapshot_plan_id'])
        self.assertEqual(result['snapshot_id'], 'd' * 64)
        state = read_private(Path(self.plan['state_root']) / 'state.json')
        self.assertEqual(state['last_snapshot'], 'd' * 64)

    def test_restore_verifies_manifest_before_protecting_snapshot(self):
        self.initialize()
        source = self.base / 'application-backup'
        source.mkdir()
        with patch.object(v, '_repository_id', return_value='c' * 64), \
                patch.object(v, 'verify_backup', return_value=self.manifest):
            snapshot = v.make_snapshot_plan(self.plan, source)
            target = self.base / 'restored'
            calls = []

            def command(_plan, arguments, **_kwargs):
                calls.append(arguments)
                return ''

            with patch.object(v, '_restic', side_effect=command), \
                    patch.object(v, '_snapshots', return_value=[{'id': 'd' * 64}]), \
                    patch.object(v, '_locate_backup', return_value=target):
                result = v.restore(self.plan, snapshot, 'd' * 64, target,
                                   snapshot['snapshot_plan_id'])
        self.assertTrue(result['recovery_verified'])
        self.assertTrue(any(arguments[:3] == ['tag', '--add', v.VERIFIED_TAG]
                            for arguments in calls))
        state = read_private(Path(self.plan['state_root']) / 'state.json')
        self.assertEqual(state['last_verified'], 'd' * 64)

    def test_restore_refuses_tampered_snapshot_reference(self):
        self.initialize()
        source = self.base / 'application-backup'
        source.mkdir()
        with patch.object(v, '_repository_id', return_value='c' * 64), \
                patch.object(v, 'verify_backup', return_value=self.manifest):
            snapshot = v.make_snapshot_plan(self.plan, source)
        snapshot['summary']['documents'] = 2
        with patch.object(v, '_repository_id', return_value='c' * 64), \
                patch.object(v, '_restic') as restic, self.assertRaises(ConfigError):
            v.restore(self.plan, snapshot, 'd' * 64, self.base / 'restored',
                      snapshot['snapshot_plan_id'])
        restic.assert_not_called()

    def test_check_binds_latest_snapshot(self):
        self.initialize()
        state_path = Path(self.plan['state_root']) / 'state.json'
        state = read_private(state_path)
        state['last_snapshot'] = 'd' * 64
        atomic_json(state_path, state, replace=True)
        with patch.object(v, '_repository_id', return_value='c' * 64), \
                patch.object(v, '_snapshots', return_value=[{'id': 'd' * 64}]), \
                patch.object(v, '_restic', return_value=''):
            result = v.check(self.plan, self.plan['plan_id'])
        self.assertEqual(result['checked_snapshot'], 'd' * 64)
        self.assertEqual(read_private(state_path)['last_checked_snapshot'], 'd' * 64)

    def test_retention_is_blocked_until_restore_and_defaults_to_dry_run(self):
        self.initialize()
        with patch.object(v, '_repository_id', return_value='c' * 64), \
                self.assertRaises(ConfigError):
            v.retention(self.plan)
        state_path = Path(self.plan['state_root']) / 'state.json'
        state = read_private(state_path)
        state['last_verified'] = 'd' * 64
        state['last_snapshot'] = 'd' * 64
        state['last_checked_snapshot'] = 'd' * 64
        atomic_json(state_path, state, replace=True)
        with patch.object(v, '_repository_id', return_value='c' * 64), \
                patch.object(v, '_snapshots', return_value=[{
                    'id': 'd' * 64, 'tags': [v.VERIFIED_TAG]}]), \
                patch.object(v, '_restic', return_value='') as restic:
            result = v.retention(self.plan)
        self.assertEqual(result['mode'], 'preview')
        arguments = restic.call_args.args[1]
        self.assertIn('--dry-run', arguments)
        self.assertNotIn('--prune', arguments)

    def test_retention_refuses_missing_protection_tag(self):
        self.initialize()
        state_path = Path(self.plan['state_root']) / 'state.json'
        state = read_private(state_path)
        state['last_verified'] = 'd' * 64
        state['last_snapshot'] = 'd' * 64
        state['last_checked_snapshot'] = 'd' * 64
        atomic_json(state_path, state, replace=True)
        with patch.object(v, '_repository_id', return_value='c' * 64), \
                patch.object(v, '_snapshots', return_value=[{'id': 'd' * 64, 'tags': []}]), \
                self.assertRaises(ConfigError):
            v.retention(self.plan)

    def test_retention_refuses_unchecked_latest_snapshot(self):
        self.initialize()
        state_path = Path(self.plan['state_root']) / 'state.json'
        state = read_private(state_path)
        state['last_snapshot'] = 'd' * 64
        state['last_verified'] = 'd' * 64
        atomic_json(state_path, state, replace=True)
        with patch.object(v, '_repository_id', return_value='c' * 64), \
                patch.object(v, '_snapshots') as snapshots, self.assertRaises(ConfigError):
            v.retention(self.plan)
        snapshots.assert_not_called()

    def test_malformed_restic_summary_is_refused(self):
        self.assertEqual(v._json_lines('noise\n{"message_type":"summary"}'),
                         [{'message_type': 'summary'}])
        with self.assertRaises(ConfigError):
            v._json_lines('{broken')


if __name__ == '__main__':
    unittest.main()
