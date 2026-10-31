import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from homelab import vaultwarden as v
from homelab.config import ConfigError, ROOT
from homelab.privatefs import atomic_json, create_private_directory


class VaultwardenPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab vaultwarden ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.runtime = {'context': 'local-test', 'endpoint': 'npipe:////./pipe/test',
                        'engine_id': 'engine-test'}
        self.plan = v.make_plan(self.base / 'install', 18050, self.runtime)
        self.owner = 'a' * 32

    def test_plan_is_deterministic_private_and_noop(self):
        self.assertEqual(self.plan, v.make_plan(self.base / 'install', 18050,
                                               self.runtime))
        self.assertEqual(list(self.base.iterdir()), [])
        self.assertEqual(self.plan['access'], 'loopback')
        self.assertEqual(self.plan['admin'], 'disabled')
        self.assertFalse(self.plan['docker_socket'])
        self.assertEqual(self.plan['recovery_method'],
                         'sqlite-vacuum-filesystem-restore')
        self.assertEqual(set(self.plan['runtime_user']), {'uid', 'gid', 'source'})

    def test_plan_tampering_and_unsafe_inputs_are_refused(self):
        for field, value in [('images', {}), ('port', 80), ('access', 'public'),
                             ('admin', 'enabled'), ('docker_socket', True),
                             ('registration', 'public'), ('runtime_user', {
                                 'uid': 65534, 'gid': 65534, 'source': 'tampered'})]:
            changed = copy.deepcopy(self.plan)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                v.validate_plan(changed)
        for root, port in ((ROOT / 'runtime', 18050),
                           (self.base / '$INPUT', 18050),
                           (self.base / 'missing/root', 18050),
                           (self.base / 'other', True)):
            with self.subTest(root=root), self.assertRaises(ConfigError):
                v.make_plan(root, port, self.runtime)

    def test_compose_is_loopback_internal_bounded_and_unprivileged(self):
        spec = v.compose(self.plan, self.owner)
        service = spec['services']['app']
        self.assertEqual(service['ports'], [{
            'target': 80, 'published': '18050', 'host_ip': '127.0.0.1',
            'protocol': 'tcp'}])
        self.assertTrue(spec['networks']['default']['internal'])
        self.assertTrue(service['read_only'])
        self.assertEqual(service['cap_drop'], ['ALL'])
        self.assertIn('no-new-privileges:true', service['security_opt'])
        self.assertEqual(service['user'],
                         f'{self.plan["runtime_user"]["uid"]}:'
                         f'{self.plan["runtime_user"]["gid"]}')
        self.assertEqual(service['tmpfs'], [
            '/tmp:rw,noexec,nosuid,size=64m,uid='
            + str(self.plan['runtime_user']['uid']) + ',gid='
            + str(self.plan['runtime_user']['gid']) + ',mode=0700'])
        self.assertEqual(service['mem_limit'], '384m')
        self.assertEqual(service['memswap_limit'], '512m')
        self.assertEqual(service['pids_limit'], 256)
        self.assertEqual(service['environment']['DISABLE_ADMIN_TOKEN'], 'true')
        self.assertEqual(service['environment']['INVITATIONS_ALLOWED'], 'false')
        self.assertNotIn('docker.sock', json.dumps(spec))
        self.assertIn('@sha256:', service['image'])

    def test_linux_runtime_matches_private_host_directory_owner(self):
        with patch.object(v, 'host_platform', return_value='linux'), \
                patch.object(v.os, 'getuid', return_value=1001, create=True), \
                patch.object(v.os, 'getgid', return_value=1002, create=True):
            plan = v.make_plan(self.base / 'linux-install', 18051, self.runtime)
            self.assertEqual(plan['runtime_user'], {
                'uid': 1001, 'gid': 1002, 'source': 'host-owner'})
            service = v.compose(plan, self.owner)['services']['app']
            self.assertEqual(service['user'], '1001:1002')
            self.assertIn('uid=1001,gid=1002,mode=0700', service['tmpfs'][0])

    def test_credentials_are_random_synthetic_and_strict(self):
        first, second = v.new_credentials(), v.new_credentials()
        self.assertNotEqual(first, second)
        self.assertEqual(v.validate_credentials(first), first)
        for changed in ({'fixture_email': 'real@example.com',
                         'fixture_password': first['fixture_password']},
                        {'fixture_email': v.FIXTURE_EMAIL,
                         'fixture_password': 'short'},
                        {**first, 'extra': 'value'}):
            with self.assertRaises(ConfigError):
                v.validate_credentials(changed)

    def test_browser_parser_requires_decryption_download_and_independent_sessions(self):
        evidence = browser_evidence()
        raw = {key: evidence[key] for key in (
            'kind', 'item_id', 'title', 'body', 'title_sha256', 'body_sha256',
            'attachment', 'browser', 'headless', 'rendered_title', 'decrypted_body',
            'attachment_downloaded', 'reload_persistence', 'independent_sessions')}
        self.assertEqual(v.parse_browser_output(json.dumps(raw)), raw)
        for changed in ({**raw, 'decrypted_body': False},
                        {**raw, 'reload_persistence': False},
                        {**raw, 'independent_sessions': False},
                        {**raw, 'body_sha256': '0' * 64},
                        {**raw, 'attachment': {**raw['attachment'],
                                                   'bytes': 1}}):
            with self.subTest(change=changed), self.assertRaises(ConfigError):
                v.parse_browser_output(json.dumps(changed))

    def test_confirmation_precedes_runtime_or_mutation(self):
        with patch.object(v, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            v.operate(self.plan, 'stop', 'wrong')
        runtime.assert_not_called()
        with patch.object(v, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            v.exercise(self.plan, 'wrong')
        runtime.assert_not_called()
        with patch.object(v, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            v.backup(self.plan, self.base / 'backup', 'wrong')
        runtime.assert_not_called()


def browser_evidence():
    return {
        'kind': 'vaultwarden-browser-vault-v1',
        'item_id': '11111111-2222-3333-4444-555555555555',
        'title': v.FIXTURE_TITLE, 'body': v.FIXTURE_BODY,
        'title_sha256': hashlib.sha256(v.FIXTURE_TITLE.encode()).hexdigest(),
        'body_sha256': hashlib.sha256(v.FIXTURE_BODY.encode()).hexdigest(),
        'attachment': {
            'filename': v.FIXTURE_ATTACHMENT,
            'bytes': len(v.FIXTURE_ATTACHMENT_BODY),
            'sha256': hashlib.sha256(v.FIXTURE_ATTACHMENT_BODY).hexdigest()},
        'browser': 'chromium', 'headless': True, 'rendered_title': True,
        'decrypted_body': True, 'attachment_downloaded': True,
        'reload_persistence': True, 'independent_sessions': True,
        'screenshot_sha256': '3' * 64, 'browser_source_id': '4' * 64,
        'browser_image': 'mcr.microsoft.com/playwright@sha256:' + '5' * 64,
    }


class VaultwardenBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab vaultwarden backup ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'snapshot'
        create_private_directory(self.root)
        create_private_directory(self.root / 'data')
        create_private_directory(self.root / 'data' / 'attachments')
        create_private_directory(self.root / 'data' / 'sends')
        database = self.root / 'data' / 'db.sqlite3'
        database.write_bytes(b'SQLite format 3\x00' + b'\x00' * 8192)
        (self.root / 'data' / 'rsa_key.pem').write_text(
            'synthetic-rsa-private-key\n', encoding='utf-8')
        attachment = self.root / 'data' / 'attachments' / 'fixture.bin'
        attachment.write_bytes(b'synthetic-encrypted-attachment')
        v.tree_files(self.root / 'data', protect_new=True)
        self.credentials = {'fixture_email': v.FIXTURE_EMAIL,
                            'fixture_password': 'Vw1-' + 'a' * 32}
        atomic_json(self.root / 'credentials.json', self.credentials)
        (self.root / 'compose.private.json').write_text('{"services":{}}\n',
                                                         encoding='utf-8')
        (self.root / 'sanitized-config.json').write_text('{"kind":"fixture"}\n',
                                                          encoding='utf-8')
        for name in ('compose.private.json', 'sanitized-config.json'):
            v.protect_file(self.root / name)
        self.browser = browser_evidence()
        atomic_json(self.root / 'browser-fixture.json', self.browser)
        database = self.root / 'data' / 'db.sqlite3'
        self.manifest = {
            'kind': 'vaultwarden-consistent-backup-v1',
            'created_utc': '2026-10-30T00:00:00+00:00', 'images': v.images(),
            'method': 'sqlite-vacuum-filesystem-restore',
            'authoritative_material': ['sqlite-vacuum-snapshot', 'rsa-keys',
                                       'attachments', 'sends', 'private-credentials'],
            'derived_material': ['container-image', 'web-vault-assets', 'icon-cache',
                                 'temporary-files', 'sqlite-wal', 'sqlite-shm'],
            'consistency': {'sqlite_vacuum_exit_verified': True,
                            'application_quiesced_for_copy': True,
                            'rsa_keys_copied': True,
                            'attachment_tree_copied': True,
                            'send_tree_copied': True},
            'recovery_status': 'pending-independent-restore',
            'credentials_hash': v.digest(self.credentials),
            'configuration_sha256': {
                'private': v.file_hash(self.root / 'compose.private.json'),
                'sanitized': v.file_hash(self.root / 'sanitized-config.json')},
            'database_sha256': v.file_hash(database),
            'database_bytes': database.stat().st_size,
            'data_tree': v.tree_files(self.root / 'data'),
            'browser_sha256': v.file_hash(self.root / 'browser-fixture.json'),
            'browser': self.browser, 'summary': None,
        }
        self.manifest['summary'] = v.backup_summary(self.manifest)
        atomic_json(self.root / 'manifest.json', self.manifest)

    def test_complete_backup_verifies_and_binds_recovery_plan(self):
        manifest = v.verify_backup(self.root)
        self.assertEqual(manifest['summary']['vault_items'], 1)
        runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock',
                   'engine_id': 'test'}
        plan = v.make_plan(self.root.parent / 'restore', 18051, runtime, self.root)
        self.assertEqual(plan['recovery']['method'],
                         'sqlite-vacuum-filesystem-restore')
        self.assertEqual(plan['recovery']['manifest_id'], v.digest(manifest))

    def test_database_tree_and_credentials_tampering_are_refused(self):
        database = self.root / 'data' / 'db.sqlite3'
        database.write_bytes(b'changed')
        v.protect_file(database)
        with self.assertRaisesRegex(ConfigError, 'SQLite'):
            v.verify_backup(self.root)
        database.write_bytes(b'SQLite format 3\x00' + b'\x00' * 8192)
        v.protect_file(database)
        (self.root / 'data' / 'attachments' / 'extra').write_bytes(b'extra')
        v.protect_file(self.root / 'data' / 'attachments' / 'extra')
        with self.assertRaisesRegex(ConfigError, 'tree checksum'):
            v.verify_backup(self.root)

    def test_transient_wal_or_manifest_drift_is_refused(self):
        wal = self.root / 'data' / 'db.sqlite3-wal'
        wal.write_bytes(b'transient')
        v.protect_file(wal)
        with self.assertRaisesRegex(ConfigError, 'WAL'):
            v.verify_backup(self.root)
        wal.unlink()
        changed = {**self.manifest, 'images': {}}
        atomic_json(self.root / 'manifest.json', changed, replace=True)
        with self.assertRaisesRegex(ConfigError, 'image'):
            v.verify_backup(self.root)


if __name__ == '__main__':
    unittest.main()
