import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from homelab.config import ConfigError
from homelab.privatefs import atomic_json, create_private_directory
from homelab import karakeep as k


def browser_evidence():
    return {
        'kind': 'karakeep-browser-bookmarks-v1',
        'text_id': 'text_bookmark_123', 'asset_id': 'asset_12345678',
        'asset_bookmark_id': 'asset_bookmark_123',
        'title': k.FIXTURE_TITLE, 'body': k.FIXTURE_BODY,
        'title_sha256': hashlib.sha256(k.FIXTURE_TITLE.encode()).hexdigest(),
        'body_sha256': hashlib.sha256(k.FIXTURE_BODY.encode()).hexdigest(),
        'asset': {'filename': k.FIXTURE_ASSET, 'bytes': len(k.FIXTURE_ASSET_BODY),
                  'sha256': hashlib.sha256(k.FIXTURE_ASSET_BODY).hexdigest()},
        'rendered_title': True, 'full_text_search': True,
        'asset_downloaded': True, 'search_reindexed': False,
        'browser': 'chromium', 'headless': True,
        'application_export': {'created': True, 'bookmark_count': 2, 'bytes': 800},
        'screenshot_sha256': '3' * 64, 'browser_source_id': '4' * 64,
        'browser_image': 'mcr.microsoft.com/playwright@sha256:' + '5' * 64,
    }


class KarakeepPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab karakeep ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock',
                        'engine_id': 'test'}
        self.owner = '1' * 32
        self.plan = k.make_plan(self.base / 'install', 18060, self.runtime)

    def test_plan_is_deterministic_and_rejects_drift(self):
        self.assertEqual(self.plan,
                         k.make_plan(self.base / 'install', 18060, self.runtime))
        self.assertEqual(self.plan['contract'], 'karakeep-isolated-recovery-v1')
        self.assertFalse(self.plan['docker_socket'])
        self.assertEqual(self.plan['derived_material'][:2],
                         ['queue-database', 'meilisearch-index'])
        changed = {**self.plan, 'port': 18061}
        with self.assertRaises(ConfigError):
            k.validate_plan(changed)

    def test_unsafe_roots_and_ports_are_refused(self):
        for root, port in ((self.base / 'bad$root', 18060),
                           (self.base / 'install', 80)):
            with self.subTest(root=root, port=port), self.assertRaises(ConfigError):
                k.make_plan(root, port, self.runtime)

    def test_compose_is_loopback_internal_bounded_and_unprivileged(self):
        credentials = k.new_credentials()
        spec = k.compose(self.plan, self.owner, credentials)
        self.assertEqual(set(spec['services']), {'app', 'chrome', 'search'})
        self.assertEqual(spec['services']['app']['ports'], [{
            'target': 3000, 'published': '18060', 'host_ip': '127.0.0.1',
            'protocol': 'tcp'}])
        self.assertTrue(spec['networks']['default']['internal'])
        for name, service in spec['services'].items():
            self.assertTrue(service['read_only'], name)
            self.assertEqual(service['cap_drop'], ['ALL'])
            self.assertIn('no-new-privileges:true', service['security_opt'])
            self.assertIn('@sha256:', service['image'])
        app = spec['services']['app']
        self.assertEqual(app['mem_limit'], '1024m')
        self.assertEqual(app['networks']['default']['aliases'], ['karakeep-web'])
        self.assertIn('/run:rw,exec,nosuid,size=32m', app['tmpfs'][1])
        self.assertNotIn('noexec', app['tmpfs'][1])
        self.assertEqual(app['environment']['INFERENCE_ENABLE_AUTO_TAGGING'], 'false')
        self.assertEqual(app['environment']['EMBEDDING_ENABLE_AUTO_INDEXING'], 'false')
        self.assertNotIn('OPENAI_API_KEY', app['environment'])
        self.assertNotIn('docker.sock', json.dumps(spec))

    def test_linux_runtime_matches_private_host_owner(self):
        with patch.object(k, 'host_platform', return_value='linux'), \
                patch.object(k.os, 'getuid', return_value=1001, create=True), \
                patch.object(k.os, 'getgid', return_value=1002, create=True):
            plan = k.make_plan(self.base / 'linux-install', 18061, self.runtime)
            self.assertEqual(plan['runtime_user'], {
                'uid': 1001, 'gid': 1002, 'source': 'host-owner'})
            spec = k.compose(plan, self.owner, k.new_credentials())
            self.assertEqual(spec['services']['app']['user'], '1001:1002')
            self.assertEqual(spec['services']['search']['user'], '1001:1002')

    def test_credentials_are_random_synthetic_and_strict(self):
        first, second = k.new_credentials(), k.new_credentials()
        self.assertNotEqual(first, second)
        self.assertEqual(k.validate_credentials(first, seeded=False), first)
        seeded = {**first, 'api_key': 'k' * 32,
                  'identifiers': {'textId': 'text_id_1234',
                                  'assetId': 'asset_id_1234',
                                  'assetBookmarkId': 'asset_bookmark_1234'}}
        self.assertEqual(k.validate_credentials(seeded, seeded=True), seeded)
        for changed in ({**first, 'fixture_email': 'real@example.com'},
                        {**first, 'fixture_password': 'short'},
                        {**first, 'extra': 'value'},
                        {**first, 'api_key': 'short', 'identifiers': {}}):
            with self.subTest(change=changed), self.assertRaises(ConfigError):
                k.validate_credentials(changed, seeded=True if changed.get('api_key') else None)

    def test_browser_parser_requires_render_search_and_exact_asset(self):
        evidence = browser_evidence()
        raw_keys = ('kind', 'text_id', 'asset_id', 'asset_bookmark_id', 'title',
                    'body', 'title_sha256', 'body_sha256', 'asset',
                    'rendered_title', 'full_text_search', 'asset_downloaded',
                    'search_reindexed', 'browser', 'headless', 'application_export')
        raw = {key: evidence[key] for key in raw_keys}
        self.assertEqual(k.parse_browser_output(json.dumps(raw)), raw)
        for changed in ({**raw, 'rendered_title': False},
                        {**raw, 'full_text_search': False},
                        {**raw, 'asset_downloaded': False},
                        {**raw, 'asset': {**raw['asset'], 'bytes': 1}}):
            with self.subTest(change=changed), self.assertRaises(ConfigError):
                k.parse_browser_output(json.dumps(changed))

    def test_confirmation_precedes_runtime_or_mutation(self):
        with patch.object(k, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            k.operate(self.plan, 'stop', 'wrong')
        runtime.assert_not_called()

    def test_exercise_source_supports_bounded_resume_contract(self):
        source = (Path(k.__file__).read_text(encoding='utf-8'))
        self.assertIn("if (root / 'browser-fixture.json').exists()", source)
        self.assertIn("'resumed_after_interruption': resumed", source)
        with patch.object(k, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            k.exercise(self.plan, 'wrong')
        runtime.assert_not_called()
        with patch.object(k, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            k.backup(self.plan, self.base / 'backup', 'wrong')
        runtime.assert_not_called()


class KarakeepBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab karakeep backup ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'snapshot'
        create_private_directory(self.root)
        create_private_directory(self.root / 'data')
        create_private_directory(self.root / 'data' / 'assets')
        database = self.root / 'data' / 'db.db'
        connection = sqlite3.connect(database)
        connection.execute('CREATE TABLE bookmarks (id TEXT PRIMARY KEY, title TEXT)')
        connection.execute('INSERT INTO bookmarks VALUES (?, ?)',
                           ('text_bookmark_123', k.FIXTURE_TITLE))
        connection.commit(); connection.close()
        (self.root / 'data' / 'assets' / k.FIXTURE_ASSET).write_bytes(
            k.FIXTURE_ASSET_BODY)
        k.tree_files(self.root / 'data', protect_new=True)
        self.credentials = k.new_credentials()
        self.credentials['api_key'] = 'k' * 32
        self.credentials['identifiers'] = {
            'textId': 'text_bookmark_123', 'assetId': 'asset_12345678',
            'assetBookmarkId': 'asset_bookmark_123'}
        atomic_json(self.root / 'credentials.json', self.credentials)
        (self.root / 'compose.private.json').write_text('{"services":{}}\n', encoding='utf-8')
        (self.root / 'sanitized-config.json').write_text('{"kind":"fixture"}\n', encoding='utf-8')
        self.browser = browser_evidence()
        atomic_json(self.root / 'browser-fixture.json', self.browser)
        with zipfile.ZipFile(self.root / 'application-export.zip', 'w') as archive:
            archive.writestr('bookmarks.json', json.dumps([
                {'title': k.FIXTURE_TITLE, 'text': k.FIXTURE_BODY},
                {'fileName': k.FIXTURE_ASSET}]))
        for name in ('compose.private.json', 'sanitized-config.json',
                     'application-export.zip'):
            k.protect_file(self.root / name)
        database = self.root / 'data' / 'db.db'
        export = self.root / 'application-export.zip'
        self.manifest = {
            'kind': 'karakeep-consistent-backup-v1',
            'created_utc': '2026-10-31T00:00:00+00:00', 'images': k.images(),
            'method': 'sqlite-quiesced-assets-reindex-restore',
            'authoritative_material': ['sqlite-database', 'asset-tree',
                                       'private-credentials'],
            'supplementary_material': ['application-logical-export'],
            'derived_material': ['queue-database', 'meilisearch-index',
                                 'container-images', 'temporary-files',
                                 'sqlite-wal', 'sqlite-shm'],
            'consistency': {'application_quiesced_for_copy': True,
                            'sqlite_quick_check_verified': True,
                            'asset_tree_copied': True,
                            'queue_database_excluded': True,
                            'search_index_excluded': True,
                            'logical_export_verified': True},
            'recovery_status': 'pending-independent-restore',
            'credentials_hash': k.digest(self.credentials),
            'configuration_sha256': {
                'private': k.file_hash(self.root / 'compose.private.json'),
                'sanitized': k.file_hash(self.root / 'sanitized-config.json')},
            'database_sha256': k.file_hash(database),
            'database_bytes': database.stat().st_size,
            'data_tree': k.tree_files(self.root / 'data'),
            'application_export': {'bytes': export.stat().st_size,
                                   'sha256': k.file_hash(export)},
            'browser_sha256': k.file_hash(self.root / 'browser-fixture.json'),
            'browser': self.browser, 'summary': None,
        }
        self.manifest['summary'] = k.backup_summary(self.manifest)
        atomic_json(self.root / 'manifest.json', self.manifest)

    def test_complete_backup_verifies_and_binds_recovery_plan(self):
        manifest = k.verify_backup(self.root)
        self.assertEqual(manifest['summary']['bookmarks'], 2)
        runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock',
                   'engine_id': 'test'}
        plan = k.make_plan(self.root.parent / 'restore', 18061, runtime, self.root)
        self.assertEqual(plan['recovery']['method'],
                         'sqlite-quiesced-assets-reindex-restore')
        self.assertEqual(plan['recovery']['manifest_id'], k.digest(manifest))

    def test_database_asset_export_and_credentials_tampering_are_refused(self):
        database = self.root / 'data' / 'db.db'
        database.write_bytes(b'changed')
        k.protect_file(database)
        with self.assertRaisesRegex(ConfigError, 'SQLite'):
            k.verify_backup(self.root)

    def test_derived_queue_or_index_material_is_refused(self):
        queue = self.root / 'data' / 'queue.db'
        queue.write_bytes(b'derived')
        k.protect_file(queue)
        with self.assertRaisesRegex(ConfigError, 'queue'):
            k.verify_backup(self.root)


if __name__ == '__main__':
    unittest.main()
