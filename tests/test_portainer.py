"""Portainer isolated-control, lifecycle and recovery contracts."""
from contextlib import nullcontext
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from homelab import portainer as p
from homelab.config import ConfigError, ROOT
from homelab.privatefs import atomic_json, create_private_directory


class PortainerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab portainer ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.runtime = {'context': 'local-test', 'endpoint': 'unix:///test/docker.sock',
                        'engine_id': 'test-engine'}
        self.plan = p.make_plan(self.base / 'install', 19443, self.runtime, p.GRANT)
        self.owner = 'c' * 32

    def resources(self, running=True):
        project = p.project(self.plan)
        port_binding = {'9443/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '19443'}]}
        common_host = {
            'RestartPolicy': {'Name': 'unless-stopped'},
            'LogConfig': {'Type': 'json-file', 'Config': {'max-size': '10m', 'max-file': '2'}},
            'Devices': None, 'DeviceRequests': None,
        }
        portainer = {
            'Id': 'id-portainer',
            'Config': {'Labels': {**p.tags(self.plan, self.owner),
                                  'com.docker.compose.service': 'portainer'},
                       'Image': self.plan['images']['portainer'], 'Cmd': p.portainer_command(self.plan),
                       'Env': []},
            'HostConfig': {**common_host, 'ReadonlyRootfs': True, 'Privileged': False,
                           'CapDrop': ['ALL'], 'CapAdd': None,
                           'SecurityOpt': ['no-new-privileges:true'],
                           'Memory': p.PORTAINER_MEMORY_MIB * 1024**2,
                           'NanoCpus': int(p.PORTAINER_CPUS * 1_000_000_000),
                           'PidsLimit': p.PORTAINER_PIDS, 'PortBindings': port_binding,
                           'Tmpfs': p.expected_portainer_tmpfs()},
            'State': {'Running': running, 'Paused': False,
                      'Status': 'running' if running else 'exited'},
            'NetworkSettings': {'Ports': port_binding if running else {},
                                'Networks': {project + '_frontend': {}, project + '_control': {}}},
            'Mounts': [
                {'Type': 'volume', 'Name': project + '_data', 'Destination': '/data', 'RW': True,
                 'Source': project + '_data'},
                {'Type': 'bind', 'Destination': '/run/secrets/portainer_admin_password', 'RW': False,
                 'Source': str(Path(self.plan['root']) / 'admin-password.txt')},
                {'Type': 'bind', 'Destination': '/run/secrets/portainer', 'RW': False,
                 'Source': str(Path(self.plan['root']) / 'encryption-key.txt')},
            ],
        }
        engine = {
            'Id': 'id-engine',
            'Config': {'Labels': {**p.tags(self.plan, self.owner),
                                  'com.docker.compose.service': 'engine'},
                       'Image': self.plan['images']['engine'], 'Cmd': p.engine_command(),
                       'Env': ['DOCKER_TLS_CERTDIR='], 'Healthcheck': p.engine_healthcheck()},
            'HostConfig': {**common_host, 'ReadonlyRootfs': False, 'Privileged': True,
                           'CapDrop': None, 'CapAdd': None, 'SecurityOpt': None,
                           'Memory': p.ENGINE_MEMORY_MIB * 1024**2,
                           'NanoCpus': p.ENGINE_CPUS * 1_000_000_000,
                           'PidsLimit': p.ENGINE_PIDS, 'PortBindings': {},
                           'Tmpfs': p.expected_engine_tmpfs()},
            'State': {'Running': running, 'Paused': False,
                      'Status': 'running' if running else 'exited',
                      'Health': {'Status': 'healthy' if running else 'unhealthy'}},
            'NetworkSettings': {'Ports': {}, 'Networks': {project + '_control': {}}},
            'Mounts': [],
        }
        networks = [
            {'Id': 'front-network', 'Name': project + '_frontend',
             'Labels': p.tags(self.plan, self.owner), 'Driver': 'bridge', 'Internal': False,
             'Containers': {'id-portainer': {}}},
            {'Id': 'control-network', 'Name': project + '_control',
             'Labels': p.tags(self.plan, self.owner), 'Driver': 'bridge', 'Internal': True,
             'Containers': {'id-portainer': {}, 'id-engine': {}}},
        ]
        volumes = [{'Name': project + '_data', 'Labels': p.tags(self.plan, self.owner),
                    'Driver': 'local', 'Options': None}]
        return {'containers': {'portainer': portainer, 'engine': engine},
                'networks': networks, 'volumes': volumes}

    def inspect(self, resources, attached='id-portainer'):
        replies = [
            'id-portainer id-engine', json.dumps(list(resources['containers'].values())),
            'front-network control-network', json.dumps(resources['networks']),
            p.project(self.plan) + '_data', json.dumps(resources['volumes']), attached,
        ]
        with patch.object(p, 'docker', side_effect=replies):
            return p.inventory(self.plan, self.owner)

    def simulate(self, status, resources, action):
        state = {'status': status, 'owner': self.owner}
        with (patch.object(p, 'local_runtime', return_value=self.runtime),
              patch.object(p, 'prepare'),
              patch.object(p, 'operation_lock', return_value=nullcontext()),
              patch.object(p, 'state_read', return_value=state),
              patch.object(p, 'inventory', return_value=resources),
              patch.object(p, 'read_private', return_value=copy.deepcopy(state)),
              patch.object(p, 'atomic_json'), patch.object(p, 'port_free'),
              patch.object(p, 'wait_engine'), patch.object(p, 'docker') as docker):
            result = p.operate(self.plan, action, self.plan['plan_id'])
            return result, [call.args[0] for call in docker.call_args_list]

    def test_plan_is_deterministic_and_requires_exact_control_grant(self):
        self.assertEqual(self.plan,
                         p.make_plan(self.base / 'install', 19443, self.runtime, p.GRANT))
        self.assertFalse(self.plan['permission']['host_engine_access'])
        self.assertTrue(self.plan['permission']['privileged_sidecar'])
        with self.assertRaisesRegex(ConfigError, 'exact'):
            p.make_plan(self.base / 'other', 19443, self.runtime, 'host-control')
        self.assertEqual(list(self.base.iterdir()), [])

    def test_plan_tampering_and_unsafe_inputs_refused(self):
        for field, value in [('host_docker_socket', True), ('access', 'public'),
                             ('network', 'host'), ('platform', 'foreign')]:
            changed = copy.deepcopy(self.plan)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                p.validate_plan(changed)
        for root, port in ((ROOT / 'runtime', 19443), (self.base / '$INPUT', 19443),
                           (self.base / 'missing/root', 19443), (self.base / 'other', True)):
            with self.subTest(root=root), self.assertRaises(ConfigError):
                p.make_plan(root, port, self.runtime, p.GRANT)

    def test_compose_has_isolated_explicit_control_only(self):
        spec = p.compose(self.plan, self.owner)
        server, engine = spec['services']['portainer'], spec['services']['engine']
        self.assertEqual(server['ports'][0]['host_ip'], '127.0.0.1')
        self.assertEqual(server['ports'][0]['target'], 9443)
        self.assertTrue(server['read_only'])
        self.assertFalse(server.get('privileged', False))
        self.assertEqual(server['cap_drop'], ['ALL'])
        self.assertNotIn('docker.sock', json.dumps(server))
        self.assertTrue(engine['privileged'])
        self.assertNotIn('ports', engine)
        self.assertEqual(engine['networks'], ['control'])
        self.assertTrue(spec['networks']['control']['internal'])
        self.assertFalse(spec['networks']['frontend']['internal'])
        for service in spec['services'].values():
            for binding in service.get('ports', []):
                self.assertNotEqual(binding.get('target'), 8000)
                self.assertNotEqual(str(binding.get('published')), '8000')
        self.assertIn('--http-disabled', server['command'])
        self.assertIn('--no-edge-compute', server['command'])
        self.assertIn('--secret-key-name=portainer', server['command'])
        self.assertFalse(any('trusted-origins' in item for item in server['command']))
        self.assertNotIn('--compact-db', server['command'])
        self.assertIn('--tls=false', engine['command'])

    def test_inventory_accepts_exact_owned_resources(self):
        self.assertEqual(set(self.inspect(self.resources())['containers']), {'portainer', 'engine'})

    def test_inventory_refuses_privilege_mount_resource_and_network_drift(self):
        changes = [
            lambda r: r['containers']['portainer']['HostConfig'].__setitem__('Privileged', True),
            lambda r: r['containers']['portainer']['Mounts'].append(
                {'Type': 'bind', 'Destination': '/var/run/docker.sock', 'RW': True,
                 'Source': '/var/run/docker.sock'}),
            lambda r: r['containers']['engine']['HostConfig'].__setitem__('Privileged', False),
            lambda r: r['containers']['engine']['HostConfig'].__setitem__('PortBindings',
                                                                          {'2375/tcp': []}),
            lambda r: r['containers']['portainer']['HostConfig'].__setitem__('Memory', 0),
            lambda r: r['networks'][1].__setitem__('Internal', False),
            lambda r: r['containers']['portainer']['Config']['Labels'].__setitem__(
                'org.homelab.owner', 'foreign'),
        ]
        for change in changes:
            resources = self.resources()
            change(resources)
            with self.subTest(change=change), self.assertRaises(ConfigError):
                self.inspect(resources)

    def test_foreign_network_or_volume_attachment_refused(self):
        resources = self.resources()
        resources['networks'][0]['Containers']['foreign'] = {}
        with self.assertRaises(ConfigError):
            self.inspect(resources)
        with self.assertRaises(ConfigError):
            self.inspect(self.resources(), attached='id-portainer foreign')

    def test_confirmation_and_engine_checked_before_mutation(self):
        with patch.object(p, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            p.operate(self.plan, 'stop', 'wrong')
        runtime.assert_not_called()
        with (patch.object(p, 'local_runtime', return_value={'context': 'changed'}),
              patch.object(p, 'state_read') as state, self.assertRaises(ConfigError)):
            p.operate(self.plan, 'status')
        state.assert_not_called()

    def test_running_stop_and_removal_contract(self):
        result, commands = self.simulate('running', self.resources(), 'up')
        self.assertEqual(commands, [])
        self.assertFalse(result['host_engine_access'])
        _, commands = self.simulate('running', self.resources(), 'stop')
        self.assertEqual(commands, [['stop', '--time', '30', 'id-portainer'],
                                    ['stop', '--time', '30', 'id-engine']])
        with self.assertRaisesRegex(ConfigError, 'Stop'):
            self.simulate('running', self.resources(), 'remove')
        _, commands = self.simulate('stopped', self.resources(False), 'remove')
        self.assertEqual(commands, [['rm', 'id-portainer'], ['rm', 'id-engine'],
                                    ['network', 'rm', 'front-network'],
                                    ['network', 'rm', 'control-network']])

    def test_missing_interrupted_and_paused_states_fail_closed(self):
        resources = self.resources()
        resources['containers'] = {}
        with self.assertRaisesRegex(ConfigError, 'missing'):
            self.simulate('running', resources, 'up')
        with self.assertRaisesRegex(ConfigError, 'Interrupted restore'):
            self.simulate('restore-copying', self.resources(False), 'up')
        resources = self.resources()
        resources['containers']['engine']['State']['Paused'] = True
        with self.assertRaisesRegex(ConfigError, 'Paused'):
            self.simulate('running', resources, 'stop')

    def test_exercise_uses_only_nested_endpoint_and_removes_probe(self):
        resources = self.resources()
        calls = []

        def api(_plan, path, **kwargs):
            calls.append((path, kwargs.get('method', 'GET')))
            if path == '/api/endpoints':
                return 200, [{'Id': 7, 'URL': 'tcp://engine:2375'}]
            if path.endswith('/docker/info'):
                return 200, {'Containers': 0, 'ServerVersion': '29.9.0'}
            if path.endswith('/networks/create'):
                return 201, {'Id': 'a' * 64}
            if path.endswith('/networks/' + 'a' * 64) and kwargs.get('method') == 'DELETE':
                return 204, None
            if path.endswith('/networks/' + 'a' * 64):
                return 200, {'Name': p.PROBE_NETWORK,
                             'Labels': {'org.homelab.synthetic': 'true'}}
            return 404, {'message': 'not found'}

        with (patch.object(p, 'local_runtime', return_value=self.runtime),
              patch.object(p, 'operation_lock', return_value=nullcontext()),
              patch.object(p, 'state_read', return_value={'status': 'running', 'owner': self.owner}),
              patch.object(p, 'inventory', return_value=resources),
              patch.object(p, 'authenticated', return_value='private-token'),
              patch.object(p, 'api', side_effect=api)):
            result = p.exercise(self.plan, self.plan['plan_id'])
        self.assertEqual(result['status'], 'passed')
        self.assertFalse(result['host_engine_access'])
        self.assertFalse(result['probe_retained'])
        self.assertIn((f'/api/endpoints/7/docker/networks/{"a" * 64}', 'DELETE'), calls)

    def test_api_transport_error_is_sanitized(self):
        opener = unittest.mock.Mock()
        opener.open.side_effect = urllib.error.URLError('private response content')
        with (patch.object(p.urllib.request, 'build_opener', return_value=opener),
              self.assertRaisesRegex(ConfigError, '^Portainer API request failed') as raised):
            p.api(self.plan, '/api/system/status')
        self.assertNotIn('private response', str(raised.exception))

    def test_backup_requires_confirmation_and_stopped_services(self):
        with patch.object(p, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            p.backup(self.plan, self.base / 'snapshot', 'wrong')
        runtime.assert_not_called()
        with (patch.object(p, 'local_runtime', return_value=self.runtime),
              patch.object(p, 'operation_lock', return_value=nullcontext()),
              patch.object(p, 'state_read', return_value={'status': 'running', 'owner': self.owner}),
              patch.object(p, 'inventory', return_value=self.resources()),
              self.assertRaises(ConfigError)):
            p.backup(self.plan, self.base / 'snapshot', self.plan['plan_id'])


class PortainerBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab portainer backup ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'snapshot'
        create_private_directory(self.root)
        create_private_directory(self.root / 'data')
        (self.root / 'data/portainer.edb').write_bytes(b'synthetic-edb-evidence')
        p.tree_files(self.root / 'data', protect_new=True)
        p.atomic_secret(self.root / 'admin-password.txt', 'synthetic-password-for-tests-only')
        p.atomic_secret(self.root / 'encryption-key.txt', 'synthetic-encryption-key-for-tests')
        self.tree = p.tree_files(self.root / 'data')
        images = p.load_json(p.MODULE / 'images.json')
        self.images = {'portainer': images['portainer_image'], 'engine': images['engine_image']}
        self.manifest = {
            'kind': 'portainer-stopped-backup-v1', 'images': self.images,
            'permission': 'isolated-nested-engine',
            'credential_hash': p.credential_hash(self.root), 'tree': self.tree,
            'encryption_key_hash': p.encryption_key_hash(self.root),
            'summary': p.snapshot_summary(self.root),
        }
        atomic_json(self.root / 'manifest.json', self.manifest)

    def replace_manifest(self, changed):
        atomic_json(self.root / 'manifest.changed.json', changed)
        (self.root / 'manifest.json').unlink()
        os.replace(self.root / 'manifest.changed.json', self.root / 'manifest.json')

    def test_backup_evidence_and_recovery_plan(self):
        manifest = p.verify_backup(self.root)
        self.assertTrue(manifest['summary']['database_present'])
        runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock', 'engine_id': 'test'}
        plan = p.make_plan(self.root.parent / 'restore', 19444, runtime, p.GRANT, self.root)
        self.assertEqual(plan['recovery']['manifest_id'], p.digest(manifest))

    def test_changed_missing_or_extra_content_refused(self):
        (self.root / 'data/portainer.edb').write_bytes(b'changed')
        p.tree_files(self.root / 'data', protect_new=True)
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            p.verify_backup(self.root)
        (self.root / 'data/portainer.edb').write_bytes(b'synthetic-edb-evidence')
        p.tree_files(self.root / 'data', protect_new=True)
        (self.root / 'data/extra').write_text('extra', encoding='utf-8')
        p.tree_files(self.root / 'data', protect_new=True)
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            p.verify_backup(self.root)

    def test_missing_database_or_credential_tampering_refused(self):
        (self.root / 'data/portainer.edb').unlink()
        with self.assertRaisesRegex(ConfigError, 'database'):
            p.snapshot_summary(self.root)
        self.replace_manifest({**self.manifest, 'credential_hash': '0' * 64})
        with self.assertRaisesRegex(ConfigError, 'credential'):
            p.verify_backup(self.root)

    def test_overlap_and_manifest_image_tampering_refused(self):
        runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock', 'engine_id': 'test'}
        with self.assertRaises(ConfigError):
            p.make_plan(self.root / 'restore', 19444, runtime, p.GRANT, self.root)
        changed = {**self.manifest, 'images': {**self.images, 'portainer': 'foreign'}}
        self.replace_manifest(changed)
        with self.assertRaisesRegex(ConfigError, 'image'):
            p.verify_backup(self.root)


if __name__ == '__main__':
    unittest.main()
