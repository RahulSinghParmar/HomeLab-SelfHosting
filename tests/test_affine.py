"""AFFiNE isolation, sync evidence and recovery contracts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from homelab import affine as a
from homelab.config import ConfigError, ROOT
from homelab.privatefs import atomic_json, create_private_directory


class AffineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab affine ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.runtime = {'context': 'local-test', 'endpoint': 'unix:///test/docker.sock',
                        'engine_id': 'test-engine'}
        self.plan = a.make_plan(self.base / 'install', 18020, self.runtime)
        self.owner = 'a' * 32
        self.credentials = {'database_password': 'b' * 64,
                            'redis_password': 'c' * 64,
                            'fixture_password': 'Aa1-' + 'd' * 24}

    def test_plan_is_deterministic_private_and_noop(self):
        self.assertEqual(self.plan, a.make_plan(self.base / 'install', 18020,
                                               self.runtime))
        self.assertEqual(list(self.base.iterdir()), [])
        self.assertEqual(self.plan['access'], 'loopback')
        self.assertFalse(self.plan['docker_socket'])
        self.assertEqual(self.plan['fixture_mode'], 'isolated-first-admin')
        self.assertEqual(self.plan['recovery_material'],
                         ['postgres-custom-dump', 'config', 'storage'])

    def test_plan_tampering_and_unsafe_inputs_refused(self):
        for field, value in [('images', {}), ('port', 80), ('access', 'public'),
                             ('ai', 'enabled'), ('docker_socket', True),
                             ('fixture_mode', 'production')]:
            changed = copy.deepcopy(self.plan)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                a.validate_plan(changed)
        for root, port in ((ROOT / 'runtime', 18020), (self.base / '$INPUT', 18020),
                           (self.base / 'missing/root', 18020),
                           (self.base / 'other', True)):
            with self.subTest(root=root), self.assertRaises(ConfigError):
                a.make_plan(root, port, self.runtime)

    def test_compose_is_loopback_bounded_and_models_one_shot_migration(self):
        spec = a.compose(self.plan, self.owner, self.credentials)
        services = spec['services']
        self.assertEqual(set(services), set(a.SERVICES))
        self.assertEqual(services['affine']['ports'], [{
            'target': 3010, 'published': '18020', 'host_ip': '127.0.0.1',
            'protocol': 'tcp'}])
        for role in ('redis', 'postgres', 'migration'):
            self.assertNotIn('ports', services[role])
        self.assertTrue(spec['networks']['backend']['internal'])
        self.assertEqual(services['migration']['restart'], 'no')
        self.assertEqual(services['migration']['command'],
                         ['sh', '-c', 'node ./scripts/self-host-predeploy.js'])
        self.assertEqual(services['affine']['environment']['DEPLOYMENT_TYPE'],
                         'selfhosted')
        self.assertEqual(services['affine']['environment']['AFFINE_INDEXER_ENABLED'],
                         'false')
        self.assertEqual(services['affine']['environment']['NODE_ENV'], 'production')
        self.assertNotIn('docker.sock', json.dumps(spec))
        self.assertTrue(all('@sha256:' in service['image']
                            for service in services.values()))
        self.assertEqual(services['affine']['mem_limit'], '1536m')

    def test_credentials_are_random_and_strict(self):
        first, second = a.new_credentials(), a.new_credentials()
        self.assertNotEqual(first, second)
        self.assertEqual(a.validate_credentials(first), first)
        for changed in ({'database_password': 'short', 'redis_password': 'c' * 64,
                         'fixture_password': 'Aa1-' + 'd' * 24},
                        {**self.credentials, 'extra': 'd' * 64}):
            with self.assertRaises(ConfigError):
                a.validate_credentials(changed)

    def test_fixture_parser_requires_semantic_and_second_session_evidence(self):
        value = {'kind': 'affine-synthetic-document-v1', 'workspace_id': 'workspace',
                 'doc_id': 'document', 'marker': a.MARKER,
                 'marker_sha256': '1' * 64, 'state_sha256': '2' * 64,
                 'independent_sessions': True}
        output = 'startup log\n' + json.dumps(value)
        self.assertEqual(a.parse_fixture_output(output), value)
        for change in ({**value, 'marker': 'wrong'},
                       {**value, 'independent_sessions': False},
                       {**value, 'state_sha256': 'short'}):
            with self.assertRaises(ConfigError):
                a.parse_fixture_output(json.dumps(change))

    def test_verify_fixture_invokes_bounded_read_only_mode(self):
        evidence = {'kind': 'affine-synthetic-document-v1',
                    'workspace_id': 'workspace', 'doc_id': 'document',
                    'marker': a.MARKER, 'marker_sha256': '1' * 64,
                    'state_sha256': '2' * 64, 'independent_sessions': True}
        with patch.object(a, 'docker', return_value=json.dumps(evidence)) as docker:
            self.assertEqual(a.verify_fixture(self.plan, evidence), evidence)
        command = docker.call_args.args[0]
        self.assertEqual(command[-5:], ['node', '/homelab/fixture.mjs', 'verify',
                                        'workspace', 'document'])
        self.assertEqual(docker.call_args.kwargs,
                         {'context': 'local-test', 'timeout': 120})

    def test_confirmation_precedes_runtime_or_mutation(self):
        with patch.object(a, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            a.operate(self.plan, 'stop', 'wrong')
        runtime.assert_not_called()
        with patch.object(a, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            a.exercise(self.plan, 'wrong')
        runtime.assert_not_called()
        with patch.object(a, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            a.backup(self.plan, self.base / 'backup', 'wrong')
        runtime.assert_not_called()


class AffineBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab affine backup ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'snapshot'
        create_private_directory(self.root)
        create_private_directory(self.root / 'config')
        create_private_directory(self.root / 'storage')
        (self.root / 'config/config.json').write_text('{"fixture":true}\n', encoding='utf-8')
        (self.root / 'config/private.key').write_text('synthetic-private-key\n', encoding='utf-8')
        (self.root / 'storage/object').write_bytes(b'synthetic-storage')
        for child in ('config', 'storage'):
            a.tree_files(self.root / child, protect_new=True)
        (self.root / 'affine-postgres.dump').write_bytes(b'PGDMP-synthetic')
        self.credentials = {'database_password': '1' * 64,
                            'redis_password': '2' * 64,
                            'fixture_password': 'Aa1-' + '3' * 24}
        atomic_json(self.root / 'credentials.json', self.credentials)
        (self.root / 'compose.private.json').write_text('{"services":{}}\n',
                                                         encoding='utf-8')
        (self.root / 'sanitized-config.json').write_text('{"kind":"fixture"}\n',
                                                          encoding='utf-8')
        for name in ('compose.private.json', 'sanitized-config.json',
                     'affine-postgres.dump'):
            a.protect_file(self.root / name)
        self.inventory = {'kind': 'affine-synthetic-document-v1',
                          'workspace_id': 'workspace', 'doc_id': 'document',
                          'marker': a.MARKER, 'marker_sha256': '3' * 64,
                          'state_sha256': '4' * 64,
                          'independent_sessions': True}
        self.manifest = {
            'kind': 'affine-consistent-backup-v1',
            'created_utc': '2026-10-20T00:00:00+00:00', 'images': a.images(),
            'method': 'postgres-config-storage',
            'material': ['postgres-custom-dump', 'config', 'storage'],
            'consistency': {'application_quiesced': True,
                            'migration_completed': True,
                            'postgres_archive_readable': True,
                            'config_copy_complete': True,
                            'storage_copy_complete': True},
            'recovery_status': 'pending-independent-restore',
            'credentials_hash': a.digest(self.credentials),
            'configuration_sha256': {
                'private': a.file_hash(self.root / 'compose.private.json'),
                'sanitized': a.file_hash(self.root / 'sanitized-config.json')},
            'database_sha256': a.file_hash(self.root / 'affine-postgres.dump'),
            'trees': {'config': a.tree_files(self.root / 'config'),
                      'storage': a.tree_files(self.root / 'storage')},
            'inventory': self.inventory, 'summary': None,
        }
        self.manifest['summary'] = a.backup_summary(self.manifest)
        atomic_json(self.root / 'manifest.json', self.manifest)

    def test_backup_evidence_and_recovery_plan(self):
        manifest = a.verify_backup(self.root)
        self.assertEqual(manifest['summary']['documents'], 1)
        runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock',
                   'engine_id': 'test'}
        plan = a.make_plan(self.root.parent / 'restore', 18021, runtime, self.root)
        self.assertEqual(plan['recovery']['method'], 'postgres-config-storage')
        self.assertEqual(plan['recovery']['manifest_id'], a.digest(manifest))

    def test_changed_database_tree_or_empty_evidence_refused(self):
        (self.root / 'affine-postgres.dump').write_bytes(b'changed')
        a.protect_file(self.root / 'affine-postgres.dump')
        with self.assertRaisesRegex(ConfigError, 'PostgreSQL'):
            a.verify_backup(self.root)
        (self.root / 'affine-postgres.dump').write_bytes(b'PGDMP-synthetic')
        a.protect_file(self.root / 'affine-postgres.dump')
        (self.root / 'storage/extra').write_bytes(b'extra')
        a.tree_files(self.root / 'storage', protect_new=True)
        with self.assertRaisesRegex(ConfigError, 'tree checksum'):
            a.verify_backup(self.root)

    def test_credentials_and_manifest_tampering_refused(self):
        changed = {**self.manifest, 'images': {}}
        atomic_json(self.root / 'manifest.json', changed, replace=True)
        with self.assertRaisesRegex(ConfigError, 'image'):
            a.verify_backup(self.root)


if __name__ == '__main__':
    unittest.main()
