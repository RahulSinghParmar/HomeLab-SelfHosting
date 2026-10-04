"""Kuma contract and backup guards. No real Docker daemon is used by these tests."""
from contextlib import nullcontext
import copy
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from homelab import kuma as k
from homelab.config import ConfigError, ROOT
from homelab.privatefs import atomic_json, create_private_directory


class KumaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab kuma ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.runtime = {'context': 'local-test', 'endpoint': 'unix:///test/docker.sock', 'engine_id': 'test-engine'}
        self.plan = k.make_plan(self.base / 'install', 13001, self.runtime)
        self.owner = 'a' * 32

    def resources(self, running=True):
        containers = {}
        for role in ('kuma', 'fixture'):
            ports = {'3001/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '13001'}]} if role == 'kuma' else {}
            containers[role] = {'Id': 'id-' + role,
                'Config': {'Labels': {**k.tags(self.plan, self.owner), 'com.docker.compose.service': role},
                           'Image': self.plan['image'], 'Env': ['UPTIME_KUMA_DB_TYPE=sqlite'],
                           'Cmd': ['node', 'server/server.js'] if role == 'kuma' else ['node', '-e', k.FIXTURE]},
                'HostConfig': {'ReadonlyRootfs': True, 'Privileged': False, 'CapDrop': ['ALL'],
                               'SecurityOpt': ['no-new-privileges:true'], 'PidsLimit': 150,
                               'Memory': (512 if role == 'kuma' else 64) * 1024**2,
                               'NanoCpus': 1000000000 if role == 'kuma' else 250000000,
                               'RestartPolicy': {'Name': 'unless-stopped'},
                               'LogConfig': {'Type': 'json-file', 'Config': {'max-size': '5m', 'max-file': '2'}},
                               'PortBindings': ports, 'Tmpfs': {'/tmp': 'rw,noexec,nosuid,size=64m'} if role == 'kuma' else {}},
                'State': {'Running': running, 'Paused': False, 'Status': 'running' if running else 'exited'},
                'NetworkSettings': {'Ports': ports, 'Networks': {k.project(self.plan) + '_default': {}}},
                'Mounts': [{'Type': 'volume', 'Name': k.project(self.plan) + '_data', 'Destination': '/app/data', 'RW': True}] if role == 'kuma' else []}
        return {'containers': containers,
                'networks': [{'Id': 'network-id', 'Name': k.project(self.plan) + '_default', 'Labels': k.tags(self.plan, self.owner), 'Driver': 'bridge', 'Internal': False, 'Containers': {c['Id']: {} for c in containers.values()}}],
                'volumes': [{'Name': k.project(self.plan) + '_data', 'Labels': k.tags(self.plan, self.owner), 'Driver': 'local', 'Options': None}]}

    def inspect(self, resources, attached='id-kuma'):
        with patch.object(k, 'docker', side_effect=['id-kuma id-fixture', json.dumps(list(resources['containers'].values())),
                                                   'network-id', json.dumps(resources['networks']),
                                                   k.project(self.plan) + '_data', json.dumps(resources['volumes']), attached]):
            return k.inventory(self.plan, self.owner)

    def simulate(self, status, resources, action, plan=None):
        state = {'status': status, 'owner': self.owner}
        with patch.object(k, 'local_runtime', return_value=self.runtime), patch.object(k, 'prepare'), \
                patch.object(k, 'operation_lock', return_value=nullcontext()), patch.object(k, 'state_read', return_value=state), \
                patch.object(k, 'inventory', return_value=resources), patch.object(k, 'read_private', return_value=copy.deepcopy(state)), \
                patch.object(k, 'atomic_json'), patch.object(k, 'port_free'), patch.object(k, 'docker') as docker:
            selected = plan or self.plan
            result = k.operate(selected, action, selected['plan_id'])
            return result, [call.args[0] for call in docker.call_args_list]

    def test_plan_deterministic_no_writes(self):
        self.assertEqual(self.plan, k.make_plan(self.base / 'install', 13001, self.runtime))
        self.assertEqual(list(self.base.iterdir()), [])

    def test_plan_tampering_refused(self):
        for field, value in [('image', 'foreign:latest'), ('port', 80), ('network', 'host'), ('docker_socket', True), ('platform', 'unknown')]:
            plan = copy.deepcopy(self.plan)
            plan[field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                k.validate_plan(plan)

    def test_unsafe_paths_and_ports_refused(self):
        for root, port in [(ROOT / 'runtime', 13001), (self.base / '$INPUT', 13001), (self.base / 'missing' / 'root', 13001), (self.base / 'root', True), (self.base / 'root', 65536)]:
            with self.subTest(root=root, port=port), self.assertRaises(ConfigError):
                k.make_plan(root, port, self.runtime)

    def test_spec_is_bounded_and_socket_free(self):
        spec = k.compose(self.plan, self.owner)
        self.assertEqual(set(spec['services']), {'kuma', 'fixture'})
        self.assertNotIn('docker.sock', json.dumps(spec))
        self.assertEqual(spec['services']['kuma']['ports'][0]['host_ip'], '127.0.0.1')
        self.assertNotIn('ports', spec['services']['fixture'])
        self.assertEqual(spec['services']['kuma']['volumes'][0]['type'], 'volume')
        self.assertTrue(spec['services']['kuma']['volumes'][0]['volume']['nocopy'])
        for service in spec['services'].values():
            self.assertTrue(service['read_only'])
            self.assertEqual(service['cap_drop'], ['ALL'])
            self.assertEqual(service['pull_policy'], 'never')

    def test_inventory_accepts_owned_resources(self):
        self.assertEqual(len(self.inspect(self.resources())['containers']), 2)

    def test_foreign_labels_refused(self):
        resources = self.resources()
        resources['containers']['kuma']['Config']['Labels']['org.homelab.owner'] = 'foreign'
        with self.assertRaises(ConfigError):
            self.inspect(resources)

    def test_container_drift_refused(self):
        for field, value in [('Privileged', True), ('Memory', 0), ('PortBindings', {}), ('Tmpfs', {}), ('CapAdd', ['NET_ADMIN']), ('ReadonlyRootfs', False)]:
            resources = self.resources()
            resources['containers']['kuma']['HostConfig'][field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                self.inspect(resources)

    def test_unpublished_port_refused(self):
        resources = self.resources()
        resources['containers']['kuma']['NetworkSettings']['Ports'] = {}
        with self.assertRaises(ConfigError):
            self.inspect(resources)

    def test_foreign_volume_mount_refused(self):
        resources = self.resources()
        resources['containers']['kuma']['Mounts'][0]['Name'] = 'existing-data'
        with self.assertRaises(ConfigError):
            self.inspect(resources)

    def test_foreign_volume_attachment_refused(self):
        with self.assertRaises(ConfigError):
            self.inspect(self.resources(), attached='id-kuma other-container')

    def test_foreign_network_attachment_refused(self):
        resources = self.resources()
        resources['networks'][0]['Containers']['other-container'] = {}
        with self.assertRaises(ConfigError):
            self.inspect(resources)

    def test_fixture_command_drift_refused(self):
        resources = self.resources()
        resources['containers']['fixture']['Config']['Cmd'] = ['sh']
        with self.assertRaises(ConfigError):
            self.inspect(resources)

    def test_confirmation_before_host_access(self):
        with patch.object(k, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            k.operate(self.plan, 'up', 'wrong')
        runtime.assert_not_called()

    def test_engine_drift_before_storage(self):
        with patch.object(k, 'local_runtime', return_value={**self.runtime, 'engine_id': 'other'}), self.assertRaises(ConfigError):
            k.operate(self.plan, 'up', self.plan['plan_id'])
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
        del resources['containers']['fixture']
        with self.assertRaisesRegex(ConfigError, 'Incomplete'):
            self.simulate('prepared', resources, 'up')

    def test_interrupted_restore_is_fail_closed(self):
        with self.assertRaisesRegex(ConfigError, 'Interrupted restore'):
            self.simulate('restore-copying', self.resources(False), 'up')

    def test_paused_container_refused(self):
        resources = self.resources()
        resources['containers']['fixture']['State']['Paused'] = True
        with self.assertRaises(ConfigError):
            self.simulate('running', resources, 'fixture-down')

    def test_outage_only_stops_fixture(self):
        _, commands = self.simulate('running', self.resources(), 'fixture-down')
        self.assertEqual(commands, [['stop', '--time', '10', 'id-fixture']])

    def test_running_removal_refused(self):
        with self.assertRaisesRegex(ConfigError, 'Stop all'):
            self.simulate('running', self.resources(), 'remove')

    def test_removal_never_deletes_volume(self):
        _, commands = self.simulate('stopped', self.resources(False), 'remove')
        self.assertEqual(commands, [['rm', 'id-kuma'], ['rm', 'id-fixture'], ['network', 'rm', 'network-id']])

    def test_backup_requires_stopped_owned_services(self):
        with patch.object(k, 'local_runtime', return_value=self.runtime), patch.object(k, 'operation_lock', return_value=nullcontext()), \
                patch.object(k, 'state_read', return_value={'status': 'running', 'owner': self.owner}), \
                patch.object(k, 'inventory', return_value=self.resources()), self.assertRaises(ConfigError):
            k.backup(self.plan, self.base / 'snapshot', self.plan['plan_id'])
        self.assertFalse((self.base / 'snapshot').exists())

    def test_backup_confirmation_required(self):
        with patch.object(k, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            k.backup(self.plan, self.base / 'snapshot', 'wrong')
        runtime.assert_not_called()


class KumaBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab kuma recovery ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'snapshot'
        create_private_directory(self.root)
        create_private_directory(self.root / 'data')
        db = self.root / 'data/kuma.db'
        with sqlite3.connect(db) as connection:
            connection.executescript('''
                CREATE TABLE monitor (name TEXT, type TEXT, url TEXT);
                INSERT INTO monitor VALUES ('Blueprint fixture','http','http://fixture:8080');
                INSERT INTO monitor VALUES ('Blueprint self-check','http','http://127.0.0.1:3001');
                CREATE TABLE notification (name TEXT);
                CREATE TABLE user (username TEXT);
                INSERT INTO user VALUES ('blueprint-admin');
                CREATE TABLE status_page (slug TEXT);
                INSERT INTO status_page VALUES ('blueprint');
                CREATE TABLE heartbeat (status INTEGER);
                INSERT INTO heartbeat VALUES (1),(0),(1);
            ''')
        connection.close()
        k.tree_files(self.root / 'data', protect_new=True)
        self.credentials = {'username': 'blueprint-admin', 'password': secrets.token_urlsafe(32)}
        atomic_json(self.root / 'credentials.json', self.credentials)
        self.manifest = {'kind': 'kuma-stopped-backup-v1', 'image': k.load_json(k.MODULE / 'image.json')['image'],
                         'files': k.tree_files(self.root / 'data'), 'credential_hash': k.digest(self.credentials),
                         'summary': k.database_summary(self.root / 'data')}
        atomic_json(self.root / 'manifest.json', self.manifest)

    def test_nonempty_history_and_credentials_verify(self):
        value = k.verify_backup(self.root)
        self.assertEqual(value['summary']['heartbeats'], {'0': 1, '1': 2})
        self.assertEqual(value['summary']['monitor_count'], 2)

    def test_changed_snapshot_refused(self):
        with (self.root / 'data/kuma.db').open('ab') as target:
            target.write(b'changed')
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            k.verify_backup(self.root)

    def test_changed_credentials_refused(self):
        atomic_json(self.root / 'credentials.json', {'username': 'other'}, replace=True)
        with self.assertRaisesRegex(ConfigError, 'credential'):
            k.verify_backup(self.root)

    def test_extra_snapshot_file_refused(self):
        atomic_json(self.root / 'data/extra.json', {})
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            k.verify_backup(self.root)

    def test_recovery_plan_binds_manifest_and_refuses_overlap(self):
        runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock', 'engine_id': 'test'}
        plan = k.make_plan(self.root.parent / 'recovered', 13002, runtime, self.root)
        self.assertEqual(plan['recovery']['manifest_id'], k.digest(self.manifest))
        self.assertEqual(k.validate_plan(plan), plan)
        with self.assertRaises(ConfigError):
            k.make_plan(self.root / 'recovered', 13002, runtime, self.root)

    def test_invalid_sqlite_is_sanitized_error(self):
        # Separate malformed file, without damaging the valid snapshot fixture.
        malformed = self.root.parent / 'invalid'
        malformed.mkdir()
        (malformed / 'kuma.db').write_bytes(b'not a database')
        with self.assertRaisesRegex(ConfigError, 'SQLite snapshot cannot be validated'):
            k.database_summary(malformed)

    def test_foreign_monitors_or_notifications_refused(self):
        connection = sqlite3.connect(self.root / 'data/kuma.db')
        try:
            connection.execute("INSERT INTO notification VALUES ('foreign')")
            connection.commit()
            with self.assertRaisesRegex(ConfigError, 'Notifications'):
                k.database_summary(self.root / 'data')
        finally:
            connection.close()


if __name__ == '__main__':
    unittest.main()
