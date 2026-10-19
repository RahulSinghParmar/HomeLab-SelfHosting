"""Paperless-ngx isolation, document exercise and recovery contracts."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from homelab import paperless as p
from homelab.config import ConfigError, ROOT
from homelab.privatefs import atomic_json, create_private_directory


class PaperlessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab paperless ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.runtime = {'context': 'local-test', 'endpoint': 'unix:///test/docker.sock',
                        'engine_id': 'test-engine'}
        self.plan = p.make_plan(self.base / 'install', 18010, self.runtime)
        self.owner = 'a' * 32
        self.credentials = {'database_password': 'b' * 64, 'broker_password': 'c' * 64,
                            'secret_key': 'd' * 96}

    def test_plan_is_deterministic_and_noop(self):
        self.assertEqual(self.plan, p.make_plan(self.base / 'install', 18010, self.runtime))
        self.assertEqual(list(self.base.iterdir()), [])
        self.assertEqual(self.plan['recovery_method'], 'document-exporter-importer')
        self.assertEqual(self.plan['access'], 'loopback')

    def test_plan_tampering_and_unsafe_inputs_refused(self):
        for field, value in [('images', {}), ('port', 80), ('access', 'public'),
                             ('mail', 'enabled'), ('docker_socket', True)]:
            changed = copy.deepcopy(self.plan)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                p.validate_plan(changed)
        for root, port in ((ROOT / 'runtime', 18010), (self.base / '$INPUT', 18010),
                           (self.base / 'missing/root', 18010), (self.base / 'other', True)):
            with self.subTest(root=root), self.assertRaises(ConfigError):
                p.make_plan(root, port, self.runtime)

    def test_compose_is_private_bounded_and_nonfloating(self):
        spec = p.compose(self.plan, self.owner, self.credentials)
        services = spec['services']
        self.assertEqual(set(services), set(p.SERVICES))
        self.assertEqual(services['paperless']['ports'], [{
            'target': 8000, 'published': '18010', 'host_ip': '127.0.0.1', 'protocol': 'tcp'}])
        self.assertNotIn('ports', services['broker'])
        self.assertNotIn('ports', services['database'])
        self.assertTrue(spec['networks']['backend']['internal'])
        self.assertEqual(services['paperless']['environment']['PAPERLESS_ACCOUNT_ALLOW_SIGNUPS'], 'false')
        self.assertEqual(services['paperless']['environment']['PAPERLESS_AI_ENABLED'], 'false')
        self.assertNotIn('docker.sock', json.dumps(spec))
        self.assertTrue(all('@sha256:' in service['image'] for service in services.values()))
        self.assertEqual(services['paperless']['mem_limit'], '1792m')

    def test_credentials_are_random_and_strict(self):
        first, second = p.new_credentials(), p.new_credentials()
        self.assertNotEqual(first, second)
        self.assertEqual(p.validate_credentials(first), first)
        for changed in ({'database_password': 'short', 'broker_password': 'c' * 64,
                         'secret_key': 'd' * 96},
                        {**self.credentials, 'extra': 'e' * 64}):
            with self.assertRaises(ConfigError):
                p.validate_credentials(changed)

    def test_synthetic_pdf_is_small_searchable_and_validly_terminated(self):
        value = p.synthetic_pdf()
        self.assertTrue(value.startswith(b'%PDF-1.4'))
        self.assertTrue(value.endswith(b'%%EOF\n'))
        self.assertIn(b'HomeLab Paperless recovery validation', value)
        self.assertLess(len(value), 2048)

    def test_consume_fixture_is_owned_before_atomic_publication(self):
        staged = '/usr/src/paperless/consume/.paperless-recovery-fixture.uploading'
        destination = '/usr/src/paperless/consume/paperless-recovery-fixture.pdf'
        fixture = self.base / 'fixture.pdf'
        with patch.object(p, 'docker') as docker:
            p.stage_consume_fixture('local-test', 'container-id', fixture)
        self.assertEqual([call.args[0] for call in docker.call_args_list], [
            ['cp', str(fixture), 'container-id:' + staged],
            ['exec', 'container-id', 'chown', 'paperless:paperless', staged],
            ['exec', 'container-id', 'chmod', '0600', staged],
            ['exec', 'container-id', 'mv', '--', staged, destination],
        ])
        self.assertTrue(all(call.kwargs == {'context': 'local-test'}
                            for call in docker.call_args_list))

    def test_content_inventory_accepts_only_bounded_json_line(self):
        payload = {'documents': 1, 'rows': [{'title': 'fixture'}]}
        with patch.object(p, 'docker', return_value='startup line\n' + json.dumps(payload)):
            self.assertEqual(p.content_inventory(self.plan), payload)
        with patch.object(p, 'docker', return_value='private log only'), self.assertRaises(ConfigError):
            p.content_inventory(self.plan)

    def test_confirmation_precedes_runtime_or_mutation(self):
        with patch.object(p, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            p.operate(self.plan, 'stop', 'wrong')
        runtime.assert_not_called()
        with patch.object(p, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            p.exercise(self.plan, 'wrong')
        runtime.assert_not_called()
        with patch.object(p, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            p.backup(self.plan, self.base / 'backup', 'wrong')
        runtime.assert_not_called()


class PaperlessBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab paperless backup ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'snapshot'
        create_private_directory(self.root)
        create_private_directory(self.root / 'document-export')
        create_private_directory(self.root / 'filesystem')
        for name in ('data', 'media', 'export'):
            create_private_directory(self.root / 'filesystem' / name)
        (self.root / 'document-export/manifest.json').write_text('{"fixture":true}\n', encoding='utf-8')
        (self.root / 'document-export/fixture.pdf').write_bytes(p.synthetic_pdf())
        (self.root / 'filesystem/data/index').write_bytes(b'synthetic-index')
        (self.root / 'filesystem/media/original.pdf').write_bytes(p.synthetic_pdf())
        (self.root / 'filesystem/export/readme').write_text('synthetic\n', encoding='utf-8')
        (self.root / 'paperless-postgres.dump').write_bytes(b'PGDMP-synthetic')
        self.credentials = {'database_password': '1' * 64, 'broker_password': '2' * 64,
                            'secret_key': '3' * 96}
        atomic_json(self.root / 'credentials.json', self.credentials)
        for child in ('document-export', 'filesystem'):
            p.tree_files(self.root / child, protect_new=True)
        if p.os.name == 'nt':
            p.windows_acl(self.root / 'paperless-postgres.dump', create=True)
        else:
            (self.root / 'paperless-postgres.dump').chmod(0o600)
        trees = {'document-export': p.tree_files(self.root / 'document-export'),
                 **{name: p.tree_files(self.root / 'filesystem' / name)
                    for name in ('data', 'media', 'export')}}
        checksum = hashlib.sha256(p.synthetic_pdf()).hexdigest()
        inventory = {'documents': 1, 'rows': [{
            'title': 'Phase 5 Recovery Fixture', 'checksum': checksum,
            'original_filename': 'fixture.pdf', 'tags': ['phase5-recovery'],
            'file_sha256': checksum, 'content_marker': True}]}
        (self.root / 'compose.private.json').write_text('{"services":{}}\n', encoding='utf-8')
        (self.root / 'sanitized-config.json').write_text('{"kind":"fixture"}\n', encoding='utf-8')
        for name in ('compose.private.json', 'sanitized-config.json'):
            if p.os.name == 'nt':
                p.windows_acl(self.root / name, create=True)
            else:
                (self.root / name).chmod(0o600)
        self.manifest = {'kind': 'paperless-consistent-backup-v1',
                         'created_utc': '2026-10-16T00:00:00+00:00', 'images': p.images(),
                         'method': 'document-exporter-importer',
                         'secondary_material': ['postgres-custom-dump', 'data', 'media', 'export'],
                         'consistency': {'application_quiesced': True,
                                         'document_export_complete': True,
                                         'postgres_archive_readable': True,
                                         'filesystem_copy_complete': True},
                         'recovery_status': 'pending-independent-restore',
                         'credentials_hash': p.digest(self.credentials),
                         'configuration_sha256': {
                             'private': p.file_hash(self.root / 'compose.private.json'),
                             'sanitized': p.file_hash(self.root / 'sanitized-config.json')},
                         'database_sha256': p.file_hash(self.root / 'paperless-postgres.dump'),
                         'trees': trees, 'inventory': inventory, 'summary': None}
        self.manifest['summary'] = p.backup_summary(self.manifest)
        atomic_json(self.root / 'manifest.json', self.manifest)

    def test_backup_evidence_and_recovery_plan(self):
        manifest = p.verify_backup(self.root)
        self.assertEqual(manifest['summary']['documents'], 1)
        runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock', 'engine_id': 'test'}
        plan = p.make_plan(self.root.parent / 'restore', 18011, runtime, self.root)
        self.assertEqual(plan['recovery']['method'], 'document-exporter-importer')
        self.assertEqual(plan['recovery']['manifest_id'], p.digest(manifest))
        spec = p.compose(plan, 'f' * 32, self.credentials)
        restore_mount = spec['services']['paperless']['volumes'][-1]
        self.assertEqual(restore_mount['target'], '/restore-import')
        self.assertTrue(restore_mount['read_only'])

    def test_changed_missing_extra_or_empty_content_refused(self):
        (self.root / 'document-export/fixture.pdf').write_bytes(b'changed')
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            p.verify_backup(self.root)
        (self.root / 'document-export/fixture.pdf').write_bytes(p.synthetic_pdf())
        p.tree_files(self.root / 'document-export', protect_new=True)
        (self.root / 'filesystem/media/extra').write_bytes(b'extra')
        p.tree_files(self.root / 'filesystem/media', protect_new=True)
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            p.verify_backup(self.root)

    def test_credentials_database_and_manifest_tampering_refused(self):
        (self.root / 'paperless-postgres.dump').write_bytes(b'changed')
        if p.os.name == 'nt':
            p.windows_acl(self.root / 'paperless-postgres.dump', create=True)
        with self.assertRaisesRegex(ConfigError, 'PostgreSQL'):
            p.verify_backup(self.root)
        changed = {**self.manifest, 'images': {}}
        atomic_json(self.root / 'manifest.json', changed, replace=True)
        with self.assertRaisesRegex(ConfigError, 'image'):
            p.verify_backup(self.root)


if __name__ == '__main__':
    unittest.main()
