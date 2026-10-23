"""Firefly III isolation, finance fixture and recovery contracts."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from homelab.config import ConfigError
from homelab.privatefs import atomic_json, create_private_directory
from homelab import firefly as f


class FireflyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab firefly ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock',
                        'engine_id': 'test'}
        self.plan = f.make_plan(self.base / 'installation', 18040, self.runtime)
        self.credentials = {
            'app_key': 'base64:' + base64.b64encode(b'a' * 32).decode('ascii'),
            'database_password': 'b' * 64,
            'cron_token': 'c' * 32,
        }
        self.owner = 'd' * 32

    def test_plan_is_deterministic_secret_free_and_loopback_only(self):
        self.assertEqual(self.plan,
                         f.make_plan(self.base / 'installation', 18040, self.runtime))
        rendered = json.dumps(self.plan)
        for value in self.credentials.values():
            self.assertNotIn(value, rendered)
        self.assertEqual(self.plan['access'], 'loopback')
        self.assertFalse(self.plan['docker_socket'])
        self.assertEqual(self.plan['external_integrations'], 'disabled')

    def test_compose_has_exact_images_isolation_and_resource_ceilings(self):
        spec = f.compose(self.plan, self.owner, self.credentials)
        self.assertEqual(set(spec['services']), set(f.SERVICES))
        self.assertTrue(spec['networks']['backend']['internal'])
        self.assertEqual(spec['services']['app']['ports'], [{
            'target': 8080, 'published': '18040', 'host_ip': '127.0.0.1',
            'protocol': 'tcp'}])
        self.assertNotIn('ports', spec['services']['database'])
        self.assertNotIn('ports', spec['services']['cron'])
        self.assertTrue(spec['services']['cron']['read_only'])
        self.assertEqual(spec['services']['app']['mem_limit'], '1024m')
        self.assertEqual(spec['services']['database']['mem_limit'], '512m')
        self.assertEqual(spec['services']['cron']['mem_limit'], '64m')
        rendered = json.dumps(spec)
        for value in self.credentials.values():
            self.assertNotIn(value, rendered)
        self.assertNotIn('/var/run/docker.sock', rendered)
        for role in f.SERVICES:
            self.assertEqual(spec['services'][role]['image'], self.plan['images'][role])
            self.assertIn('no-new-privileges:true',
                          spec['services'][role]['security_opt'])

    def test_credentials_are_strict(self):
        self.assertEqual(f.validate_credentials(self.credentials), self.credentials)
        for changed in (
                {**self.credentials, 'app_key': 'base64:not-valid'},
                {**self.credentials, 'database_password': 'short'},
                {**self.credentials, 'cron_token': 'x' * 32}):
            with self.assertRaises(ConfigError):
                f.validate_credentials(changed)

    def test_api_fixture_inventory_requires_exact_semantics_and_attachment(self):
        transaction = {'data': [{
            'id': '7', 'attributes': {'transactions': [{
                'transaction_journal_id': '11', 'description': f.FIXTURE_DESCRIPTION,
                'amount': '42.150000000000', 'currency_code': f.FIXTURE_CURRENCY,
                'source_name': f.FIXTURE_SOURCE,
                'destination_name': f.FIXTURE_DESTINATION,
                'category_name': f.FIXTURE_CATEGORY, 'tags': [f.FIXTURE_TAG],
            }]}}]}
        attachment = {'data': [{
            'id': '13', 'attributes': {'filename': f.FIXTURE_ATTACHMENT,
                                       'attachable_type': 'TransactionJournal',
                                       'attachable_id': 11}}]}
        with patch.object(f, '_json_api', side_effect=[transaction, attachment]), \
                patch.object(f, '_api_request',
                             return_value=(200, f.FIXTURE_ATTACHMENT_BODY)):
            result = f.fixture_inventory(self.plan, 't' * 100)
        self.assertEqual(result['amount'], f.FIXTURE_AMOUNT)
        self.assertEqual(result['group_id'], 7)
        self.assertEqual(result['journal_id'], 11)
        self.assertEqual(result['attachment']['sha256'],
                         hashlib.sha256(f.FIXTURE_ATTACHMENT_BODY).hexdigest())

    def test_create_fixture_uses_synthetic_values_only(self):
        account = {'data': {'id': '17'}}
        stored = {'data': {'attributes': {'transactions': [
            {'transaction_journal_id': 19}]}}}
        attachment = {'data': {'id': '23'}}
        with patch.object(f, '_json_api', side_effect=[account, stored, attachment]) as api, \
                patch.object(f, '_api_request', return_value=(204, b'')) as upload:
            result = f.create_fixture(self.plan, 't' * 100)
        self.assertEqual(result, 23)
        account_payload = api.call_args_list[0].kwargs['payload']
        self.assertEqual(account_payload['name'], f.FIXTURE_SOURCE)
        self.assertEqual(account_payload['account_role'], 'defaultAsset')
        payload = api.call_args_list[1].kwargs['payload']
        row = payload['transactions'][0]
        self.assertEqual(row['description'], f.FIXTURE_DESCRIPTION)
        self.assertEqual(row['amount'], f.FIXTURE_AMOUNT)
        self.assertEqual(row['source_id'], 17)
        self.assertEqual(row['destination_name'], f.FIXTURE_DESTINATION)
        self.assertEqual(f.FIXTURE_ATTACHMENT_BODY, upload.call_args.kwargs['body'])
        self.assertEqual('application/octet-stream',
                         upload.call_args.kwargs['content_type'])

    def test_restore_database_checks_import_and_live_database(self):
        backup = self.base / 'backup'
        backup.mkdir()
        (backup / 'firefly-mariadb.sql').write_text('synthetic', encoding='utf-8')
        with patch.object(f, 'docker') as docker:
            f._restore_database(self.plan, backup, 'database-id')
        commands = [call.args[0] for call in docker.call_args_list]
        rendered = '\n'.join(' '.join(command) for command in commands)
        self.assertIn('mariadb --user=firefly --database=firefly', rendered)
        self.assertIn('mariadb-check --user=firefly --check-upgrade firefly', rendered)
        self.assertNotIn('gzip', rendered)
        self.assertEqual(commands[-1][-3:], ['rm', '-f', commands[-1][-1]])

    def test_restore_filesystems_uses_bounded_ownership_helper(self):
        backup = self.base / 'backup'
        for name in f.APP_AREAS:
            (backup / 'filesystem' / name).mkdir(parents=True, exist_ok=True)
        with patch.object(f, 'docker') as docker:
            f._restore_filesystems(self.plan, backup, 'app-id')
        command = docker.call_args_list[-1].args[0]
        self.assertIn('run', command)
        self.assertIn('--rm', command)
        self.assertEqual(command[command.index('--user') + 1], '0')
        self.assertEqual(command[command.index('--cap-add') + 1], 'CHOWN')
        self.assertNotIn('--privileged', command)
        self.assertIn('chown -R www-data:www-data', command[-1])

    def test_confirmation_precedes_runtime_or_mutation(self):
        with patch.object(f, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            f.operate(self.plan, 'stop', 'wrong')
        runtime.assert_not_called()
        with patch.object(f, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            f.exercise(self.plan, 'wrong')
        runtime.assert_not_called()
        with patch.object(f, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            f.backup(self.plan, self.base / 'backup', 'wrong')
        runtime.assert_not_called()

    def test_owned_stopped_project_restarts_without_loopback_reprobe(self):
        state = {'kind': 'firefly-owned-v1', 'owner': self.owner,
                 'plan_id': self.plan['plan_id'], 'status': 'stopped',
                 'recovery': None}
        containers = {
            role: {'State': {'Running': False, 'Paused': False, 'Status': 'exited'}}
            for role in f.SERVICES
        }
        resources = {'containers': containers, 'networks': [],
                     'volumes': [{} for _ in f.VOLUMES]}
        with patch.object(f, 'prepare'), \
                patch.object(f, 'local_runtime', return_value=self.runtime), \
                patch.object(f, 'state_read', return_value=state), \
                patch.object(f, 'inventory', return_value=resources), \
                patch.object(f, 'operation_lock'), \
                patch.object(f, 'read_private', return_value=state), \
                patch.object(f, 'atomic_json'), \
                patch.object(f, 'wait_health'), \
                patch.object(f, 'docker') as docker, \
                patch.object(f, 'port_free') as port_probe:
            result = f.operate(self.plan, 'up', self.plan['plan_id'])
        port_probe.assert_not_called()
        self.assertTrue(any(call.args[0][-5:] == ['up', '-d', '--no-build', '--pull', 'never']
                            for call in docker.call_args_list))
        self.assertEqual(result['state'], 'running')


class FireflyBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab firefly backup ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'snapshot'
        create_private_directory(self.root)
        create_private_directory(self.root / 'filesystem')
        create_private_directory(self.root / 'filesystem' / 'upload')
        create_private_directory(self.root / 'filesystem' / 'export')
        (self.root / 'filesystem/upload/receipt.bin').write_bytes(
            f.FIXTURE_ATTACHMENT_BODY)
        (self.root / 'filesystem/export/transactions.csv').write_text(
            'description,amount\nsynthetic,42.15\n', encoding='utf-8')
        (self.root / 'firefly-mariadb.sql').write_bytes(b'-- MariaDB dump\n' + b'x' * 2048)
        self.credentials = {
            'app_key': 'base64:' + base64.b64encode(b'a' * 32).decode('ascii'),
            'database_password': 'b' * 64,
            'cron_token': 'c' * 32,
        }
        atomic_json(self.root / 'credentials.json', self.credentials)
        for name, content in (('compose.private.json', '{"services":{}}\n'),
                              ('sanitized-config.json', '{"kind":"fixture"}\n')):
            path = self.root / name
            path.write_text(content, encoding='utf-8')
            if f.os.name == 'nt':
                f.windows_acl(path, create=True)
            else:
                path.chmod(0o600)
        if f.os.name == 'nt':
            f.windows_acl(self.root / 'firefly-mariadb.sql', create=True)
        else:
            (self.root / 'firefly-mariadb.sql').chmod(0o600)
        f.tree_files(self.root / 'filesystem', protect_new=True)
        fixture = {
            'kind': 'firefly-synthetic-finance-fixture-v1',
            'transaction_groups': 1, 'description': f.FIXTURE_DESCRIPTION,
            'amount': f.FIXTURE_AMOUNT, 'currency_code': f.FIXTURE_CURRENCY,
            'source_name': f.FIXTURE_SOURCE,
            'destination_name': f.FIXTURE_DESTINATION,
            'category_name': f.FIXTURE_CATEGORY, 'tags': [f.FIXTURE_TAG],
            'group_id': 7, 'journal_id': 11,
            'attachment': {'filename': f.FIXTURE_ATTACHMENT,
                           'bytes': len(f.FIXTURE_ATTACHMENT_BODY),
                           'sha256': hashlib.sha256(
                               f.FIXTURE_ATTACHMENT_BODY).hexdigest()},
        }
        trees = {name: f.tree_files(self.root / 'filesystem' / name)
                 for name in f.APP_AREAS}
        database = self.root / 'firefly-mariadb.sql'
        self.manifest = {
            'kind': 'firefly-consistent-backup-v1',
            'created_utc': '2026-10-23T00:00:00+00:00', 'images': f.images(),
            'method': 'mariadb-filesystem-restore',
            'authoritative_material': ['mariadb-logical-dump', *f.APP_AREAS,
                                       'application-secrets'],
            'derived_material': ['application-image', 'runtime-cache',
                                 'oauth-test-token'],
            'consistency': {'cron_quiesced': True, 'application_quiesced': True,
                            'mariadb_dump_exit_verified': True,
                            'mariadb_live_check_passed': True,
                            'filesystem_copy_complete': True},
            'recovery_status': 'pending-independent-restore',
            'credentials_hash': f.digest(self.credentials),
            'configuration_sha256': {
                'private': f.file_hash(self.root / 'compose.private.json'),
                'sanitized': f.file_hash(self.root / 'sanitized-config.json')},
            'database_sha256': f.file_hash(database),
            'database_bytes': database.stat().st_size,
            'trees': trees, 'fixture': fixture, 'summary': None,
        }
        self.manifest['summary'] = f.backup_summary(self.manifest)
        atomic_json(self.root / 'manifest.json', self.manifest)

    def test_backup_evidence_and_recovery_plan(self):
        manifest = f.verify_backup(self.root)
        self.assertEqual(manifest['summary']['transaction_groups'], 1)
        self.assertGreaterEqual(manifest['summary']['upload_files'], 1)
        self.assertGreaterEqual(manifest['summary']['export_files'], 1)
        runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock',
                   'engine_id': 'test'}
        plan = f.make_plan(self.root.parent / 'restore', 18041, runtime, self.root)
        self.assertEqual(plan['recovery']['method'], 'mariadb-filesystem-restore')
        self.assertEqual(plan['recovery']['manifest_id'], f.digest(manifest))
        spec = f.compose(plan, 'f' * 32, self.credentials)
        self.assertNotIn(str(self.root), json.dumps(spec))

    def test_changed_or_extra_files_are_refused(self):
        (self.root / 'filesystem/upload/receipt.bin').write_bytes(b'changed')
        if f.os.name == 'nt':
            f.windows_acl(self.root / 'filesystem/upload/receipt.bin', create=True)
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            f.verify_backup(self.root)
        (self.root / 'filesystem/upload/receipt.bin').write_bytes(
            f.FIXTURE_ATTACHMENT_BODY)
        if f.os.name == 'nt':
            f.windows_acl(self.root / 'filesystem/upload/receipt.bin', create=True)
        extra = self.root / 'filesystem/export/extra.csv'
        extra.write_text('extra\n', encoding='utf-8')
        if f.os.name == 'nt':
            f.windows_acl(extra, create=True)
        else:
            extra.chmod(0o600)
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            f.verify_backup(self.root)

    def test_credentials_database_and_manifest_tampering_are_refused(self):
        (self.root / 'firefly-mariadb.sql').write_bytes(b'changed')
        if f.os.name == 'nt':
            f.windows_acl(self.root / 'firefly-mariadb.sql', create=True)
        with self.assertRaisesRegex(ConfigError, 'MariaDB'):
            f.verify_backup(self.root)
        changed = {**self.manifest, 'images': {}}
        atomic_json(self.root / 'manifest.json', changed, replace=True)
        with self.assertRaisesRegex(ConfigError, 'image'):
            f.verify_backup(self.root)


if __name__ == '__main__':
    unittest.main()
