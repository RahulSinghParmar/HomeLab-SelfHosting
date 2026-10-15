"""Beszel contracts and fault guards, without contacting a Docker daemon."""
from contextlib import closing, nullcontext
import copy
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from homelab import beszel as b
from homelab.config import ConfigError, ROOT
from homelab.privatefs import atomic_json, create_private_directory

KEY = 'ssh-ed25519 ' + 'A' * 68


class BeszelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab beszel ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.runtime = {'context': 'local-test', 'endpoint': 'unix:///test/docker.sock', 'engine_id': 'test-engine'}
        self.plan = b.make_plan(self.base / 'install', 18090, self.runtime)
        self.owner = 'a' * 32

    def resources(self, running=True):
        containers = {}
        for role, spec in b.compose(self.plan, self.owner, KEY)['services'].items():
            ports = {'8090/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '18090'}]} if role == 'hub' else {}
            containers[role] = {'Id': 'id-' + role,
                'Config': {'Labels': {**b.tags(self.plan, self.owner), 'com.docker.compose.service': role},
                           'Image': self.plan['images'][role], 'Env': [k+'='+v for k, v in spec['environment'].items()],
                           'Cmd': ['serve', '--http=0.0.0.0:8090'] if role == 'hub' else None,
                           'Entrypoint': ['/beszel'] if role == 'hub' else ['/agent']},
                'HostConfig': {'ReadonlyRootfs': True, 'Privileged': False, 'CapDrop': ['ALL'],
                               'SecurityOpt': ['no-new-privileges:true'], 'PidsLimit': 100,
                               'Memory': (256 if role == 'hub' else 128) * 1024**2, 'NanoCpus': 500000000,
                               'RestartPolicy': {'Name': 'unless-stopped'},
                               'LogConfig': {'Type': 'json-file', 'Config': {'max-size': '5m', 'max-file': '2'}},
                               'PortBindings': ports, 'Tmpfs': {'/tmp': 'rw,noexec,nosuid,size=32m'}},
                'State': {'Running': running, 'Paused': False, 'Status': 'running' if running else 'exited'},
                'NetworkSettings': {'Ports': ports, 'Networks': {b.project(self.plan) + '_default': {}}},
                'Mounts': [{'Type': 'volume', 'Name': b.project(self.plan) + '_' + role + '-data', 'Destination': b.TARGETS[role], 'RW': True}]}
        return {'containers': containers,
                'networks': [{'Id': 'network-id', 'Name': b.project(self.plan) + '_default', 'Labels': b.tags(self.plan, self.owner), 'Driver': 'bridge', 'Internal': False, 'Containers': {c['Id']: {} for c in containers.values()}}],
                'volumes': [{'Name': b.project(self.plan) + '_' + role + '-data', 'Labels': b.tags(self.plan, self.owner), 'Driver': 'local', 'Options': None} for role in b.TARGETS]}

    def inspect(self, resources, attached='id-hub id-agent'):
        with patch.object(b, 'docker', side_effect=['id-hub id-agent', json.dumps(list(resources['containers'].values())),
                'network-id', json.dumps(resources['networks']), 'hub-data agent-data', json.dumps(resources['volumes']), attached, attached]):
            return b.inventory(self.plan, self.owner, KEY)

    def simulate(self, status, resources, action, key=KEY):
        state = {'status': status, 'owner': self.owner, 'public_key': key}
        with patch.object(b, 'local_runtime', return_value=self.runtime), patch.object(b, 'prepare'), \
                patch.object(b, 'operation_lock', return_value=nullcontext()), patch.object(b, 'state_read', return_value=state), \
                patch.object(b, 'inventory', return_value=resources), patch.object(b, 'read_private', return_value=copy.deepcopy(state)), \
                patch.object(b, 'atomic_json'), patch.object(b, 'port_free'), patch.object(b, 'docker') as docker:
            result = b.operate(self.plan, action, self.plan['plan_id'])
            return result, [call.args[0] for call in docker.call_args_list]

    def test_plan_is_deterministic_and_readonly(self):
        self.assertEqual(self.plan, b.make_plan(self.base / 'install', 18090, self.runtime))
        self.assertEqual(list(self.base.iterdir()), [])

    def test_plan_tampering_refused(self):
        for field, value in [('images', {}), ('port', 80), ('network', 'host'), ('docker_socket', True), ('metrics_scope', 'windows')]:
            plan = copy.deepcopy(self.plan)
            plan[field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                b.validate_plan(plan)

    def test_unsafe_paths_ports_refused(self):
        for root, port in [(ROOT / 'runtime', 18090), (self.base / '$INPUT', 18090), (self.base / 'missing/root', 18090), (self.base / 'root', True), (self.base / 'root', 65536)]:
            with self.subTest(root=root, port=port), self.assertRaises(ConfigError):
                b.make_plan(root, port, self.runtime)

    def test_bootstrap_has_only_hub(self):
        self.assertEqual(set(b.compose(self.plan, self.owner)['services']), {'hub'})

    def test_spec_bounded_and_no_host_access(self):
        spec = b.compose(self.plan, self.owner, KEY)
        self.assertEqual(set(spec['services']), {'hub', 'agent'})
        self.assertNotIn('docker.sock', json.dumps(spec))
        self.assertEqual(spec['services']['hub']['ports'][0]['host_ip'], '127.0.0.1')
        self.assertNotIn('ports', spec['services']['agent'])
        for service in spec['services'].values():
            self.assertTrue(service['read_only'])
            self.assertEqual(service['cap_drop'], ['ALL'])
            self.assertEqual(service['pull_policy'], 'never')
            self.assertTrue(service['volumes'][0]['volume']['nocopy'])

    def test_public_key_rejects_interpolation_or_multiple_keys(self):
        for key in ['', KEY + '\n' + KEY, KEY + '$OTHER', 'ssh-rsa anything']:
            with self.subTest(key=key), self.assertRaises(ConfigError):
                b.valid_key(key)

    def test_inventory_accepts_owned_resources(self):
        self.assertEqual(len(self.inspect(self.resources())['containers']), 2)

    def test_container_security_resource_port_drift_refused(self):
        for field, value in [('Privileged', True), ('Memory', 0), ('PortBindings', {}), ('Tmpfs', {}), ('CapAdd', ['NET_ADMIN']), ('ReadonlyRootfs', False), ('PidMode', 'host'), ('DeviceRequests', [{}])]:
            resources = self.resources()
            resources['containers']['hub']['HostConfig'][field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                self.inspect(resources)

    def test_unpublished_port_refused(self):
        resources = self.resources()
        resources['containers']['hub']['NetworkSettings']['Ports'] = {}
        with self.assertRaises(ConfigError):
            self.inspect(resources)

    def test_foreign_labels_refused(self):
        resources = self.resources()
        resources['containers']['hub']['Config']['Labels']['org.homelab.owner'] = 'other'
        with self.assertRaises(ConfigError):
            self.inspect(resources)

    def test_environment_or_process_drift_refused(self):
        for field, value in [('Env', ['AUTO_LOGIN=admin@example.invalid']), ('Entrypoint', ['/bin/sh']), ('Cmd', ['other'])]:
            resources = self.resources()
            resources['containers']['hub']['Config'][field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                self.inspect(resources)

    def test_foreign_volume_mount_refused(self):
        resources = self.resources()
        resources['containers']['agent']['Mounts'][0]['Name'] = 'existing-data'
        with self.assertRaises(ConfigError):
            self.inspect(resources)

    def test_foreign_volume_attachment_refused(self):
        with self.assertRaises(ConfigError):
            self.inspect(self.resources(), attached='id-hub other-container')

    def test_foreign_network_attachment_refused(self):
        resources = self.resources()
        resources['networks'][0]['Containers']['other-container'] = {}
        with self.assertRaises(ConfigError):
            self.inspect(resources)

    def test_confirmation_before_host_access(self):
        with patch.object(b, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            b.operate(self.plan, 'up', 'wrong')
        runtime.assert_not_called()

    def test_engine_drift_before_storage(self):
        with patch.object(b, 'local_runtime', return_value={**self.runtime, 'engine_id': 'other'}), self.assertRaises(ConfigError):
            b.operate(self.plan, 'up', self.plan['plan_id'])
        self.assertFalse(Path(self.plan['root']).exists())

    def test_running_retry_does_not_restart(self):
        result, commands = self.simulate('running', self.resources(), 'up')
        self.assertEqual(commands, [])
        self.assertEqual(result['state'], 'running')

    def test_recorded_missing_container_not_recreated(self):
        resources = self.resources()
        resources['containers'] = {}
        with self.assertRaisesRegex(ConfigError, 'missing'):
            self.simulate('running', resources, 'up')

    def test_partial_service_creation_refused(self):
        resources = self.resources()
        del resources['containers']['agent']
        with self.assertRaisesRegex(ConfigError, 'Incomplete'):
            self.simulate('running', resources, 'up')

    def test_interrupted_restore_is_fail_closed(self):
        with self.assertRaisesRegex(ConfigError, 'Interrupted restore'):
            self.simulate('restore-copying', self.resources(False), 'up')

    def test_pairing_not_silently_completed_by_up(self):
        with self.assertRaisesRegex(ConfigError, 'pairing'):
            self.simulate('pairing', self.resources(), 'up')

    def test_paused_container_refused(self):
        resources = self.resources()
        resources['containers']['agent']['State']['Paused'] = True
        with self.assertRaises(ConfigError):
            self.simulate('running', resources, 'agent-down')

    def test_outage_only_stops_agent(self):
        _, commands = self.simulate('running', self.resources(), 'agent-down')
        self.assertEqual(commands, [['stop', '--time', '10', 'id-agent']])

    def test_running_removal_refused(self):
        with self.assertRaisesRegex(ConfigError, 'Stop all'):
            self.simulate('running', self.resources(), 'remove')

    def test_removal_preserves_both_volumes(self):
        _, commands = self.simulate('stopped', self.resources(False), 'remove')
        self.assertEqual(commands, [['rm', 'id-hub'], ['rm', 'id-agent'], ['network', 'rm', 'network-id']])

    def test_redirect_refused(self):
        with self.assertRaisesRegex(ConfigError, 'forwarding'):
            b.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid')

    def test_api_error_is_sanitized(self):
        with patch.object(b.urllib.request, 'build_opener') as build:
            build.return_value.open.side_effect = urllib.error.URLError('secret response')
            with self.assertRaises(ConfigError) as raised:
                b.api(self.plan, '/api/health', token='secret-token')
            self.assertNotIn('secret', str(raised.exception))
            request = build.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, 'http://127.0.0.1:18090/api/health')
            self.assertEqual(build.call_args.args[0].proxies, {})

    def test_foreign_system_not_adopted(self):
        with patch.object(b, 'api', return_value={'totalItems': 2, 'items': [{}, {}]}), self.assertRaises(ConfigError):
            b.systems(self.plan, 'token', 'user')

    def test_metrics_omit_private_hardware_values(self):
        with patch.object(b, 'systems', return_value=[{'id': 'system', 'status': 'up'}]), \
                patch.object(b, 'api', return_value={'totalItems': 1, 'items': [{'id': 'record', 'system': 'system', 'created': 'time', 'stats': {'cpu': 7, 'private': 'not-for-output'}}]}):
            result = b.metrics(self.plan, 'token', 'user')
        self.assertEqual(result['gpu'], 'not-exposed')
        self.assertNotIn('not-for-output', json.dumps(result))

    def test_backup_requires_stopped_services(self):
        with patch.object(b, 'local_runtime', return_value=self.runtime), patch.object(b, 'operation_lock', return_value=nullcontext()), \
                patch.object(b, 'state_read', return_value={'status': 'running', 'owner': self.owner, 'public_key': KEY}), \
                patch.object(b, 'inventory', return_value=self.resources()), self.assertRaises(ConfigError):
            b.backup(self.plan, self.base / 'snapshot', self.plan['plan_id'])
        self.assertFalse((self.base / 'snapshot').exists())


class BeszelBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab beszel recovery ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'snapshot'
        create_private_directory(self.root)
        for role in b.TARGETS:
            create_private_directory(self.root / role)
        with closing(sqlite3.connect(self.root / 'hub/data.db')) as connection:
            connection.executescript('''
                CREATE TABLE users (id TEXT,email TEXT,role TEXT);
                INSERT INTO users VALUES ('user','admin@example.invalid','admin');
                CREATE TABLE _superusers (email TEXT);
                INSERT INTO _superusers VALUES ('admin@example.invalid');
                CREATE TABLE systems (id TEXT,name TEXT,host TEXT,port TEXT,users TEXT);
                INSERT INTO systems VALUES ('system','Blueprint Docker agent','agent','45876','["user"]');
                CREATE TABLE alerts (id TEXT);
                CREATE TABLE system_stats (id TEXT,system TEXT,stats TEXT,created TEXT);
                INSERT INTO system_stats VALUES ('record','system','{"cpu":5,"m":2}','time');
            ''')
        (self.root / 'hub/id_ed25519').write_text('synthetic fixture only', encoding='utf-8')
        files = {r: b.tree_files(self.root / r, protect_new=True) for r in b.TARGETS}
        credentials = {'email': b.EMAIL, 'password': secrets.token_urlsafe(32)}
        atomic_json(self.root / 'credentials.json', credentials)
        self.manifest = {'kind': 'beszel-stopped-backup-v1', 'images': {r: b.load_json(b.MODULE / 'image.json')[r] for r in b.TARGETS},
            'files': files, 'credential_hash': b.digest(credentials), 'public_key': KEY, 'summary': b.database_summary(self.root / 'hub')}
        atomic_json(self.root / 'manifest.json', self.manifest)

    def test_content_and_history_verified(self):
        self.assertEqual(b.verify_backup(self.root)['summary']['history_count'], 1)

    def test_tampered_database_refused(self):
        with (self.root / 'hub/data.db').open('ab') as target:
            target.write(b'changed')
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            b.verify_backup(self.root)

    def test_tampered_credentials_refused(self):
        atomic_json(self.root / 'credentials.json', {'email': 'other'}, replace=True)
        with self.assertRaisesRegex(ConfigError, 'credential'):
            b.verify_backup(self.root)

    def test_extra_agent_file_refused(self):
        atomic_json(self.root / 'agent/extra.json', {})
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            b.verify_backup(self.root)

    def test_foreign_system_refused(self):
        with closing(sqlite3.connect(self.root / 'hub/data.db')) as connection:
            connection.execute("UPDATE systems SET host='production.invalid'")
            connection.commit()
        with self.assertRaisesRegex(ConfigError, 'system set'):
            b.database_summary(self.root / 'hub')

    def test_checkpointed_wal_database_inspection_changes_no_files(self):
        with closing(sqlite3.connect(self.root / 'hub/data.db')) as connection:
            self.assertEqual(connection.execute('PRAGMA journal_mode=WAL').fetchone(), ('wal',))
        before = {p.name: p.read_bytes() for p in (self.root / 'hub').iterdir()}
        b.database_summary(self.root / 'hub')
        b.database_summary(self.root / 'hub')
        after = {p.name: p.read_bytes() for p in (self.root / 'hub').iterdir()}
        self.assertEqual(before, after)

    def test_nonempty_wal_never_ignored(self):
        (self.root / 'hub/data.db-wal').write_bytes(b'pending transaction')
        with self.assertRaisesRegex(ConfigError, 'Uncheckpointed'):
            b.database_summary(self.root / 'hub')

    def test_nonempty_auxiliary_journal_never_ignored(self):
        (self.root / 'hub/auxiliary.db').write_bytes(b'fixture')
        (self.root / 'hub/auxiliary.db-journal').write_bytes(b'pending transaction')
        with self.assertRaisesRegex(ConfigError, 'Uncheckpointed'):
            b.database_summary(self.root / 'hub')

    def test_recovery_plan_binds_manifest(self):
        runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock', 'engine_id': 'test'}
        plan = b.make_plan(self.root.parent / 'recovered', 18091, runtime, self.root)
        self.assertEqual(plan['recovery']['manifest_id'], b.digest(self.manifest))
        self.assertEqual(b.validate_plan(plan), plan)
        with self.assertRaises(ConfigError):
            b.make_plan(self.root / 'recovered', 18091, runtime, self.root)


if __name__ == '__main__':
    unittest.main()
