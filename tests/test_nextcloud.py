"""Nextcloud isolation, WebDAV fixture and consistent recovery contracts."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from homelab import nextcloud as n
from homelab.config import ConfigError, ROOT
from homelab.privatefs import atomic_json, create_private_directory


class NextcloudTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab nextcloud ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.runtime = {'context': 'local-test', 'endpoint': 'unix:///test/docker.sock',
                        'engine_id': 'test-engine'}
        self.plan = n.make_plan(self.base / 'install', 18030, self.runtime)
        self.owner = 'a' * 32
        self.credentials = {'database_password': 'b' * 64,
                            'cache_password': 'c' * 64,
                            'admin_password': 'd' * 64}

    def test_plan_is_deterministic_private_and_noop(self):
        self.assertEqual(self.plan, n.make_plan(self.base / 'install', 18030, self.runtime))
        self.assertEqual(list(self.base.iterdir()), [])
        self.assertEqual(self.plan['access'], 'loopback')
        self.assertEqual(self.plan['background_jobs'], 'cron')
        self.assertEqual(self.plan['external_storage'], 'not-mounted')
        self.assertFalse(self.plan['docker_socket'])

    def test_plan_tampering_and_unsafe_inputs_refused(self):
        for field, value in [('images', {}), ('port', 80), ('access', 'public'),
                             ('mail', 'enabled'), ('docker_socket', True),
                             ('external_storage', 'host-root')]:
            changed = copy.deepcopy(self.plan)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                n.validate_plan(changed)
        for root, port in ((ROOT / 'runtime', 18030), (self.base / '$INPUT', 18030),
                           (self.base / 'missing/root', 18030),
                           (self.base / 'other', True)):
            with self.subTest(root=root), self.assertRaises(ConfigError):
                n.make_plan(root, port, self.runtime)

    def test_compose_uses_file_secrets_loopback_and_internal_backend(self):
        spec = n.compose(self.plan, self.owner, self.credentials)
        services = spec['services']
        self.assertEqual(set(services), set(n.SERVICES))
        self.assertEqual(services['app']['ports'], [{
            'target': 80, 'published': '18030', 'host_ip': '127.0.0.1',
            'protocol': 'tcp'}])
        self.assertNotIn('ports', services['cache'])
        self.assertNotIn('ports', services['database'])
        self.assertNotIn('ports', services['cron'])
        self.assertTrue(spec['networks']['backend']['internal'])
        self.assertEqual(services['cron']['entrypoint'], ['/cron.sh'])
        self.assertEqual(services['app']['environment']['NEXTCLOUD_ADMIN_PASSWORD_FILE'],
                         '/run/secrets/admin_password')
        self.assertNotIn(self.credentials['admin_password'], json.dumps(spec))
        self.assertNotIn('docker.sock', json.dumps(spec))
        self.assertTrue(all('@sha256:' in n._role_image(self.plan, role)
                            for role in n.SERVICES))
        self.assertEqual(services['app']['mem_limit'], '1536m')

    def test_credentials_are_random_strict_and_not_embedded(self):
        first, second = n.new_credentials(), n.new_credentials()
        self.assertNotEqual(first, second)
        self.assertEqual(n.validate_credentials(first), first)
        for changed in ({'database_password': 'short', 'cache_password': 'c' * 64,
                         'admin_password': 'd' * 64},
                        {**self.credentials, 'extra': 'e' * 64},
                        {**self.credentials, 'admin_password': 'd' * 63 + '\n'}):
            with self.assertRaises(ConfigError):
                n.validate_credentials(changed)

    def test_database_role_is_bounded_and_restore_uses_private_sql_file(self):
        role = {'username': 'oc_admin', 'password': 'p' * 32}
        self.assertEqual(n.validate_database_role(role), role)
        for changed in ({'username': 'nextcloud', 'password': 'p' * 32},
                        {'username': 'bad-name', 'password': 'p' * 32},
                        {'username': 'oc_admin', 'password': 'short'}):
            with self.assertRaises(ConfigError):
                n.validate_database_role(changed)
        backup = self.base / 'role-backup'
        create_private_directory(backup)
        atomic_json(backup / 'database-application-role.json', role)
        root = Path(self.plan['root'])
        create_private_directory(root)
        with patch.object(n, 'docker') as docker:
            n._restore_database_role(self.plan, backup, 'database-id')
        calls = [call.args[0] for call in docker.call_args_list]
        self.assertEqual(calls[0][0], 'cp')
        self.assertIn('ON_ERROR_STOP=1', calls[1])
        self.assertIn('psql', calls[1])
        self.assertEqual(calls[-1][:4], ['exec', 'database-id', 'rm', '-f'])
        self.assertEqual(list(root.glob('restore-role-*.sql')), [])

    def test_webdav_request_uses_bounded_path_and_basic_auth(self):
        response = MagicMock()
        response.status = 200
        response.read.return_value = n.FIXTURE_BODY
        response.__enter__.return_value = response
        with patch.object(n.urllib.request, 'urlopen', return_value=response) as opened:
            status, payload = n.webdav_request(self.plan, self.credentials, 'GET')
        self.assertEqual((status, payload), (200, n.FIXTURE_BODY))
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url,
                         'http://127.0.0.1:18030/remote.php/dav/files/'
                         'homelab-admin/phase5-nextcloud-recovery.txt')
        self.assertTrue(request.headers['Authorization'].startswith('Basic '))

    def test_fixture_evidence_requires_exact_downloaded_bytes(self):
        with patch.object(n, 'webdav_request', return_value=(200, n.FIXTURE_BODY)):
            evidence = n.fixture_evidence(self.plan, self.credentials)
        self.assertEqual(evidence['sha256'], hashlib.sha256(n.FIXTURE_BODY).hexdigest())
        self.assertTrue(evidence['marker_verified'])
        with patch.object(n, 'webdav_request', return_value=(200, b'changed')), \
                self.assertRaises(ConfigError):
            n.fixture_evidence(self.plan, self.credentials)

    def test_restore_commands_are_scoped_to_owned_containers_and_volumes(self):
        backup = self.base / 'backup'
        (backup / 'filesystem').mkdir(parents=True)
        for name in n.APP_AREAS:
            (backup / 'filesystem' / name).mkdir()
        (backup / 'nextcloud-postgres.dump').write_bytes(b'PGDMP')
        with patch.object(n, 'docker') as docker:
            n._restore_database(self.plan, backup, 'database-id')
        calls = [call.args[0] for call in docker.call_args_list]
        self.assertEqual(calls[0][0], 'cp')
        self.assertIn('pg_restore', calls[1])
        self.assertIn('--clean', calls[1])
        self.assertNotIn('--no-owner', calls[1])
        with patch.object(n, 'docker') as docker:
            n._restore_filesystems(self.plan, backup, 'app-id')
        calls = [call.args[0] for call in docker.call_args_list]
        self.assertIn('find "$p" -mindepth 1 -delete', calls[0][-1])
        self.assertEqual(sum(1 for call in calls if call[0] == 'cp'), len(n.APP_AREAS))
        self.assertIn('www-data:www-data', calls[-1])
        with patch.object(n, 'docker') as docker:
            n._initialize_derived_html(self.plan)
        command = docker.call_args.args[0]
        self.assertEqual(command[-2:], ['-ec',
                         ('cp -a /usr/src/nextcloud/. /var/www/html/ && '
                          'chown -R www-data:www-data /var/www/html')])

    def test_confirmation_precedes_runtime_or_mutation(self):
        with patch.object(n, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            n.operate(self.plan, 'stop', 'wrong')
        runtime.assert_not_called()
        with patch.object(n, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            n.exercise(self.plan, 'wrong')
        runtime.assert_not_called()
        with patch.object(n, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            n.backup(self.plan, self.base / 'backup', 'wrong')
        runtime.assert_not_called()

    def test_owned_stopped_project_restarts_without_loopback_reprobe(self):
        state = {'kind': 'nextcloud-owned-v1', 'owner': self.owner,
                 'plan_id': self.plan['plan_id'], 'status': 'stopped',
                 'recovery': None}
        containers = {
            role: {'State': {'Running': False, 'Paused': False, 'Status': 'exited'}}
            for role in n.SERVICES
        }
        resources = {'containers': containers, 'networks': [],
                     'volumes': [{} for _ in n.VOLUMES]}
        with patch.object(n, 'prepare'), \
                patch.object(n, 'local_runtime', return_value=self.runtime), \
                patch.object(n, 'state_read', return_value=state), \
                patch.object(n, 'inventory', return_value=resources), \
                patch.object(n, 'operation_lock'), \
                patch.object(n, 'read_private', return_value=state), \
                patch.object(n, 'atomic_json'), \
                patch.object(n, 'wait_health'), \
                patch.object(n, '_occ'), \
                patch.object(n, 'docker') as docker, \
                patch.object(n, 'port_free') as port_probe:
            result = n.operate(self.plan, 'up', self.plan['plan_id'])
        port_probe.assert_not_called()
        self.assertTrue(any(call.args[0][-5:] == ['up', '-d', '--no-build', '--pull', 'never']
                            for call in docker.call_args_list))
        self.assertEqual(result['state'], 'running')


class NextcloudBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab nextcloud backup ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'snapshot'
        create_private_directory(self.root)
        create_private_directory(self.root / 'filesystem')
        for name in n.APP_AREAS:
            create_private_directory(self.root / 'filesystem' / name)
        (self.root / 'filesystem/config/config.php').write_text(
            "<?php $CONFIG = array ('installed' => true);\n", encoding='utf-8')
        (self.root / 'filesystem/data/fixture.bin').write_bytes(n.FIXTURE_BODY)
        (self.root / 'filesystem/custom-apps/.keep').write_text('synthetic\n', encoding='utf-8')
        (self.root / 'filesystem/themes/.keep').write_text('synthetic\n', encoding='utf-8')
        (self.root / 'nextcloud-postgres.dump').write_bytes(b'PGDMP-synthetic')
        self.credentials = {'database_password': '1' * 64,
                            'cache_password': '2' * 64,
                            'admin_password': '3' * 64}
        atomic_json(self.root / 'credentials.json', self.credentials)
        atomic_json(self.root / 'database-application-role.json',
                    {'username': 'oc_admin', 'password': '4' * 32})
        n.tree_files(self.root / 'filesystem', protect_new=True)
        for name, content in (('compose.private.json', '{"services":{}}\n'),
                              ('sanitized-config.json', '{"kind":"fixture"}\n')):
            path = self.root / name
            path.write_text(content, encoding='utf-8')
            if n.os.name == 'nt':
                n.windows_acl(path, create=True)
            else:
                path.chmod(0o600)
        for path in (self.root / 'nextcloud-postgres.dump',
                     self.root / 'database-application-role.json'):
            if n.os.name == 'nt':
                n.windows_acl(path, create=True)
            else:
                path.chmod(0o600)
        fixture = {'path': n.FIXTURE_NAME, 'bytes': len(n.FIXTURE_BODY),
                   'sha256': hashlib.sha256(n.FIXTURE_BODY).hexdigest(),
                   'marker_verified': True}
        trees = {name: n.tree_files(self.root / 'filesystem' / name)
                 for name in n.APP_AREAS}
        self.manifest = {
            'kind': 'nextcloud-consistent-backup-v1',
            'created_utc': '2026-10-21T00:00:00+00:00', 'images': n.images(),
            'method': 'postgres-filesystem-restore',
            'authoritative_material': ['postgres-custom-dump', *n.APP_AREAS],
            'derived_material': ['html', 'cache-data'],
            'consistency': {'maintenance_mode': True, 'cron_quiesced': True,
                            'application_quiesced': True,
                            'postgres_archive_readable': True,
                            'filesystem_copy_complete': True},
            'recovery_status': 'pending-independent-restore',
            'credentials_hash': n.digest(self.credentials),
            'configuration_sha256': {
                'private': n.file_hash(self.root / 'compose.private.json'),
                'sanitized': n.file_hash(self.root / 'sanitized-config.json')},
            'database_sha256': n.file_hash(self.root / 'nextcloud-postgres.dump'),
            'database_role_sha256': n.file_hash(
                self.root / 'database-application-role.json'),
            'trees': trees, 'fixture': fixture, 'summary': None,
        }
        self.manifest['summary'] = n.backup_summary(self.manifest)
        atomic_json(self.root / 'manifest.json', self.manifest)

    def test_backup_evidence_and_recovery_plan(self):
        manifest = n.verify_backup(self.root)
        self.assertEqual(manifest['summary']['files'], 1)
        runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock',
                   'engine_id': 'test'}
        plan = n.make_plan(self.root.parent / 'restore', 18031, runtime, self.root)
        self.assertEqual(plan['recovery']['method'], 'postgres-filesystem-restore')
        self.assertEqual(plan['recovery']['manifest_id'], n.digest(manifest))
        spec = n.compose(plan, 'f' * 32, self.credentials)
        self.assertNotIn(str(self.root), json.dumps(spec))

    def test_changed_or_extra_files_are_refused(self):
        (self.root / 'filesystem/data/fixture.bin').write_bytes(b'changed')
        if n.os.name == 'nt':
            n.windows_acl(self.root / 'filesystem/data/fixture.bin', create=True)
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            n.verify_backup(self.root)
        (self.root / 'filesystem/data/fixture.bin').write_bytes(n.FIXTURE_BODY)
        if n.os.name == 'nt':
            n.windows_acl(self.root / 'filesystem/data/fixture.bin', create=True)
        extra = self.root / 'filesystem/data/extra.bin'
        extra.write_bytes(b'extra')
        if n.os.name == 'nt':
            n.windows_acl(extra, create=True)
        else:
            extra.chmod(0o600)
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            n.verify_backup(self.root)

    def test_credentials_database_and_manifest_tampering_are_refused(self):
        (self.root / 'nextcloud-postgres.dump').write_bytes(b'changed')
        if n.os.name == 'nt':
            n.windows_acl(self.root / 'nextcloud-postgres.dump', create=True)
        with self.assertRaisesRegex(ConfigError, 'PostgreSQL'):
            n.verify_backup(self.root)
        changed = {**self.manifest, 'images': {}}
        atomic_json(self.root / 'manifest.json', changed, replace=True)
        with self.assertRaisesRegex(ConfigError, 'image'):
            n.verify_backup(self.root)


if __name__ == '__main__':
    unittest.main()
