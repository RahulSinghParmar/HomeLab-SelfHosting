"""Isolated module tests. Docker responses are synthetic; no daemon is contacted."""
import copy
from contextlib import nullcontext
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from homelab import glance as g
from homelab.config import ConfigError, ROOT


class GlanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='homelab glance ')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.runtime = {'context': 'test-local', 'endpoint': 'unix:///test/docker.sock', 'engine_id': 'test-engine'}
        self.plan = g.make_plan(self.base / 'install', 18081, self.runtime)
        self.owner = 'a' * 32

    def rows(self):
        tags = {**g.labels(self.plan, self.owner), 'com.docker.compose.service': 'dashboard'}
        ports = {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '18081'}]}
        container = {'Id': 'test-container', 'Config': {'Labels': tags, 'Image': self.plan['image']},
                     'HostConfig': {'ReadonlyRootfs': True, 'Memory': 134217728, 'NanoCpus': 500000000,
                                    'PidsLimit': 100, 'PortBindings': ports, 'CapDrop': ['ALL'],
                                    'SecurityOpt': ['no-new-privileges:true'], 'Privileged': False,
                                    'RestartPolicy': {'Name': 'unless-stopped'},
                                    'LogConfig': {'Type': 'json-file', 'Config': {'max-size': '5m', 'max-file': '2'}}},
                     'Mounts': [{'Type': 'bind', 'Source': str(Path(self.plan['root']) / 'glance.yml'),
                                 'Destination': '/app/config/glance.yml', 'RW': False}],
                     'State': {'Running': True, 'Paused': False},
                     'NetworkSettings': {'Ports': ports, 'Networks': {g.project(self.plan) + '_default': {}}}}
        network = {'Id': 'test-network', 'Labels': g.labels(self.plan, self.owner), 'Internal': False,
                   'Driver': 'bridge', 'Containers': {'test-container': {}}}
        return container, network

    def inspect(self, container=None, network=None, owner=None):
        default_container, default_network = self.rows()
        container = default_container if container is None else container
        network = default_network if network is None else network
        with patch.object(g, 'docker', side_effect=['test-container', json.dumps([container]),
                                                    'test-network', json.dumps([network])]):
            return g.inventory(self.plan, self.owner if owner is None else owner)

    def test_deterministic_plan_no_writes(self):
        self.assertEqual(self.plan, g.make_plan(self.base / 'install', 18081, self.runtime))
        self.assertEqual(list(self.base.iterdir()), [])
        self.assertFalse(self.plan['docker_socket'])
        self.assertEqual(self.plan['access'], 'loopback')
        self.assertEqual(self.plan['network'], 'dedicated-bridge-outbound-allowed')

    def test_plan_tampering_rejected(self):
        for field, value in [('image', 'untrusted:latest'), ('port', 22), ('access', 'public'),
                             ('dashboard', {}), ('platform', 'unknown'), ('network', 'host')]:
            changed = copy.deepcopy(self.plan)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                g.validate_plan(changed)

    def test_paths_and_ports_rejected(self):
        for root, port in [(ROOT / 'runtime', 18081), (self.base / '$VALUE', 18081),
                           (self.base / 'absent' / 'nested', 18081), (self.base / 'install', True),
                           (self.base / 'install', 65536), (self.base / 'install', 80)]:
            with self.subTest(root=root, port=port), self.assertRaises(ConfigError):
                g.make_plan(root, port, self.runtime)

    def test_compose_security_and_no_pulls(self):
        spec = g.compose(self.plan, self.owner)
        service = spec['services']['dashboard']
        self.assertEqual(set(spec['services']), {'dashboard'})
        self.assertEqual(service['ports'][0]['host_ip'], '127.0.0.1')
        self.assertTrue(service['read_only'])
        self.assertEqual(service['pull_policy'], 'never')
        self.assertFalse(service['volumes'][0]['bind']['create_host_path'])
        self.assertEqual(service['cap_drop'], ['ALL'])
        self.assertEqual(service['mem_limit'], '128m')
        self.assertNotIn('docker.sock', json.dumps(spec))
        self.assertNotIn('container_name', service)

    def test_inventory_accepts_exact_owned_resources(self):
        self.assertEqual(len(self.inspect()['containers']), 1)

    def test_foreign_owner_rejected(self):
        with self.assertRaises(ConfigError):
            self.inspect(owner='b' * 32)

    def test_bind_source_drift_rejected(self):
        container, _ = self.rows()
        container['Mounts'][0]['Source'] = '/unrelated/config'
        with self.assertRaises(ConfigError):
            self.inspect(container=container)

    def test_privilege_resource_port_drift_rejected(self):
        for key, value in [('Privileged', True), ('Memory', 0), ('CapAdd', ['SYS_ADMIN']),
                           ('Devices', [{'PathOnHost': '/dev/example'}]), ('ReadonlyRootfs', False),
                           ('PortBindings', {}), ('SecurityOpt', [])]:
            container, _ = self.rows()
            container['HostConfig'][key] = value
            with self.subTest(key=key), self.assertRaises(ConfigError):
                self.inspect(container=container)

    def test_requested_but_unpublished_port_rejected(self):
        container, _ = self.rows()
        container['NetworkSettings']['Ports'] = {'8080/tcp': []}
        with self.assertRaisesRegex(ConfigError, 'not actually published'):
            self.inspect(container=container)

    def test_internal_network_or_foreign_attachment_rejected(self):
        for key, value in [('Internal', True), ('Driver', 'host'), ('Containers', {'other': {}})]:
            _, network = self.rows()
            network[key] = value
            with self.subTest(key=key), self.assertRaises(ConfigError):
                self.inspect(network=network)

    def test_extra_network_rejected(self):
        container, _ = self.rows()
        container['NetworkSettings']['Networks']['other'] = {}
        with self.assertRaises(ConfigError):
            self.inspect(container=container)

    def test_multiple_containers_refused(self):
        with patch.object(g, 'docker', return_value='first second'), self.assertRaises(ConfigError):
            g.inventory(self.plan, self.owner)

    def test_confirmation_checked_before_docker(self):
        with patch.object(g, 'docker') as docker, self.assertRaises(ConfigError):
            g.operate(self.plan, 'up', 'wrong')
        docker.assert_not_called()

    def test_engine_change_refused_before_storage(self):
        with patch.object(g, 'local_runtime', return_value={**self.runtime, 'engine_id': 'different'}), self.assertRaises(ConfigError):
            g.operate(self.plan, 'up', self.plan['plan_id'])
        self.assertFalse(Path(self.plan['root']).exists())

    def test_docker_overrides_rejected(self):
        for key in ('DOCKER_HOST', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
            with patch.dict(os.environ, {key: 'override'}), patch.object(g.subprocess, 'run') as run, self.assertRaises(ConfigError):
                g.docker(['info'])
            run.assert_not_called()

    def test_compose_environment_stripped_and_no_shell(self):
        result = subprocess.CompletedProcess([], 0, 'ok', '')
        with patch.dict(os.environ, {'COMPOSE_FILE': '/untrusted', 'COMPOSE_PROFILES': 'all'}), patch.object(g.subprocess, 'run', return_value=result) as run:
            g.docker(['info'])
        kwargs = run.call_args.kwargs
        self.assertFalse(kwargs['shell'])
        self.assertNotIn('COMPOSE_FILE', kwargs['env'])
        self.assertNotIn('COMPOSE_PROFILES', kwargs['env'])
        self.assertEqual(kwargs['env']['COMPOSE_DISABLE_ENV_FILE'], 'true')

    def test_errors_do_not_echo_docker_output(self):
        with patch.object(g.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, 'private', 'secret-value')):
            with self.assertRaises(ConfigError) as caught:
                g.docker(['info'])
        self.assertNotIn('secret-value', str(caught.exception))

    def test_port_collision(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            with self.assertRaises(ConfigError):
                g.port_free(listener.getsockname()[1])

    def test_export_integrity_and_template_gate(self):
        source = self.base / 'export.json'
        value = {'kind': 'homelab-glance-config-export', 'config': self.plan['dashboard'], 'sha256': g.digest(self.plan['dashboard'])}
        source.write_text(json.dumps(value), encoding='utf-8')
        g.restore_config(source)
        value['config'] = {'foreign': True}
        source.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaises(ConfigError):
            g.restore_config(source)
        value['sha256'] = g.digest(value['config'])
        source.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaises(ConfigError):
            g.restore_config(source)

    def test_owned_files_export_restart_and_data_preserving_removal(self):
        # Real private filesystem/ACL/lock checks; daemon actions are mocked.
        empty = {'containers': [], 'networks': []}
        with patch.object(g, 'inventory', return_value=empty), patch.object(g, 'port_free'), patch.object(g, 'docker', return_value='[{"Os":"linux","Architecture":"amd64"}]'):
            state = g.prepare(self.plan)
        self.owner = state['owner']
        container, network = self.rows()
        owned = {'containers': [container], 'networks': [network]}
        with patch.object(g, 'local_runtime', return_value=self.runtime), patch.object(g, 'inventory', return_value=owned), patch.object(g, 'docker') as docker:
            g.operate(self.plan, 'up', self.plan['plan_id'])
            root = Path(self.plan['root'])
            original = (root / 'state.json').read_bytes()
            g.operate(self.plan, 'up', self.plan['plan_id'])
            self.assertEqual((root / 'state.json').read_bytes(), original)
            docker.assert_not_called()
            with self.assertRaises(ConfigError):
                g.operate(self.plan, 'remove', self.plan['plan_id'])
            g.operate(self.plan, 'stop', self.plan['plan_id'])
            self.assertEqual(docker.call_args.args[0], ['stop', '--time', '10', 'test-container'])
            container['State']['Running'] = False
            with patch.object(g, 'port_free'):
                g.operate(self.plan, 'up', self.plan['plan_id'])
            self.assertEqual(docker.call_args.args[0], ['start', 'test-container'])
        exported = self.base / 'export.json'
        g.export_config(self.plan, exported)
        g.restore_config(exported)
        with patch.object(g, 'local_runtime', return_value=self.runtime), patch.object(g, 'inventory', side_effect=[owned, {'containers': [], 'networks': [network]}, empty]), patch.object(g, 'docker') as docker:
            result = g.operate(self.plan, 'remove', self.plan['plan_id'])
            self.assertEqual([call.args[0] for call in docker.call_args_list], [['rm', 'test-container'], ['network', 'rm', 'test-network']])
            self.assertEqual(result['state'], 'removed')
        self.assertTrue((root / 'glance.yml').exists())
        self.assertTrue(exported.exists())
        with patch.object(g, 'local_runtime', return_value=self.runtime), patch.object(g, 'inventory', return_value=empty), self.assertRaises(ConfigError):
            g.operate(self.plan, 'up', self.plan['plan_id'])

    def simulated_operation(self, state, resources, action):
        with patch.object(g, 'local_runtime', return_value=self.runtime), patch.object(g, 'prepare'), \
                patch.object(g, 'operation_lock', return_value=nullcontext()), patch.object(g, 'state_read', return_value=state), \
                patch.object(g, 'inventory', return_value=resources), patch.object(g, 'read_private', return_value=copy.deepcopy(state)), \
                patch.object(g, 'atomic_json'), patch.object(g, 'port_free'), patch.object(g, 'docker') as docker:
            result = g.operate(self.plan, action, self.plan['plan_id'])
            return result, [call.args[0] for call in docker.call_args_list]

    def test_interrupted_up_reconciles_existing_owned_container(self):
        container, network = self.rows()
        state = {'status': 'prepared', 'owner': self.owner}
        result, commands = self.simulated_operation(state, {'containers': [container], 'networks': [network]}, 'up')
        self.assertEqual(result['state'], 'running')
        self.assertEqual(commands, [])

    def test_missing_recorded_container_not_recreated(self):
        with self.assertRaisesRegex(ConfigError, 'missing'):
            self.simulated_operation({'status': 'running', 'owner': self.owner}, {'containers': [], 'networks': []}, 'up')

    def test_interrupted_removal_finishes_without_data_deletion(self):
        _, network = self.rows()
        result, commands = self.simulated_operation({'status': 'removing', 'owner': self.owner}, {'containers': [], 'networks': [network]}, 'remove')
        self.assertEqual(result['state'], 'removed')
        self.assertEqual(commands, [['network', 'rm', 'test-network']])

    def test_removed_state_cannot_adopt_reappearing_resources(self):
        container, network = self.rows()
        with self.assertRaisesRegex(ConfigError, 'reappeared'):
            self.simulated_operation({'status': 'removed', 'owner': self.owner}, {'containers': [container], 'networks': [network]}, 'remove')

    def test_paused_container_needs_review(self):
        container, network = self.rows()
        container['State']['Paused'] = True
        with self.assertRaisesRegex(ConfigError, 'Paused'):
            self.simulated_operation({'status': 'running', 'owner': self.owner}, {'containers': [container], 'networks': [network]}, 'up')

    def test_remote_context_and_arm_engine_refused(self):
        with patch.object(g, 'docker', side_effect=['test-local', json.dumps('ssh://test.example')]), self.assertRaises(ConfigError):
            g.local_runtime()
        with patch.object(g, 'docker', side_effect=['test-local', json.dumps('unix:///test/docker.sock'), json.dumps({'id': 'test', 'os': 'linux', 'arch': 'aarch64'})]), self.assertRaises(ConfigError):
            g.local_runtime()


if __name__ == '__main__':
    unittest.main()
