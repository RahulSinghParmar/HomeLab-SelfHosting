"""Stirling-PDF isolation, document exercise and recovery contracts."""
from contextlib import nullcontext
import copy
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
import zlib
from unittest.mock import patch

from homelab import stirling as s
from homelab.config import ConfigError, ROOT
from homelab.privatefs import atomic_json, create_private_directory


class Headers:
    def get_content_type(self):
        return 'application/pdf'


class Response:
    status = 200
    headers = Headers()

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _limit):
        return self.payload


class StirlingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab stirling ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.runtime = {'context': 'local-test', 'endpoint': 'unix:///test/docker.sock', 'engine_id': 'test-engine'}
        self.plan = s.make_plan(self.base / 'install', 19000, self.runtime)
        self.owner = 'b' * 32

    def resources(self, running=True):
        ports = {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '19000'}]}
        environment = [f'{key}={value}' for key, value in s.compose(self.plan, self.owner)['services']['stirling']['environment'].items()]
        mounts = [{'Type': 'volume', 'Name': s.project(self.plan) + '_' + name,
                   'Destination': target, 'RW': True} for name, target in s.AREAS.items()]
        container = {
            'Id': 'id-stirling',
            'Config': {'Labels': {**s.tags(self.plan, self.owner), 'com.docker.compose.service': 'stirling'},
                       'Image': self.plan['image'], 'Env': environment,
                       'Healthcheck': s.expected_healthcheck()},
            'HostConfig': {'ReadonlyRootfs': True, 'Privileged': False, 'CapDrop': ['ALL'],
                           'CapAdd': ['CAP_' + value for value in self.plan['capabilities']],
                           'Devices': None, 'DeviceRequests': None,
                           'SecurityOpt': ['no-new-privileges:true'], 'PidsLimit': s.PIDS,
                           'Tmpfs': s.expected_tmpfs(),
                           'Memory': s.MEMORY_MIB * 1024**2, 'NanoCpus': s.CPUS * 1_000_000_000,
                           'RestartPolicy': {'Name': 'unless-stopped'},
                           'LogConfig': {'Type': 'json-file', 'Config': {'max-size': '10m', 'max-file': '2'}},
                           'PortBindings': ports},
            'State': {'Running': running, 'Paused': False, 'Status': 'running' if running else 'exited',
                      'Health': {'Status': 'healthy' if running else 'unhealthy'}},
            'NetworkSettings': {'Ports': ports, 'Networks': {s.project(self.plan) + '_default': {}}},
            'Mounts': mounts,
        }
        volumes = [{'Name': s.project(self.plan) + '_' + name, 'Labels': s.tags(self.plan, self.owner),
                    'Driver': 'local', 'Options': None} for name in s.AREAS]
        return {'containers': {'stirling': container},
                'networks': [{'Id': 'network-id', 'Name': s.project(self.plan) + '_default',
                              'Labels': s.tags(self.plan, self.owner), 'Driver': 'bridge', 'Internal': False,
                              'Containers': {'id-stirling': {}}}],
                'volumes': volumes}

    def inspect(self, resources, attached='id-stirling'):
        volume_ids = ' '.join(volume['Name'] for volume in resources['volumes'])
        replies = ['id-stirling', json.dumps(list(resources['containers'].values())),
                   'network-id', json.dumps(resources['networks']), volume_ids,
                   json.dumps(resources['volumes'])] + [attached] * len(resources['volumes'])
        with patch.object(s, 'docker', side_effect=replies):
            return s.inventory(self.plan, self.owner)

    def simulate(self, status, resources, action):
        state = {'status': status, 'owner': self.owner}
        with patch.object(s, 'local_runtime', return_value=self.runtime), patch.object(s, 'prepare'), \
                patch.object(s, 'operation_lock', return_value=nullcontext()), \
                patch.object(s, 'state_read', return_value=state), patch.object(s, 'inventory', return_value=resources), \
                patch.object(s, 'read_private', return_value=copy.deepcopy(state)), patch.object(s, 'atomic_json'), \
                patch.object(s, 'port_free'), patch.object(s, 'docker') as docker:
            result = s.operate(self.plan, action, self.plan['plan_id'])
            return result, [call.args[0] for call in docker.call_args_list]

    def test_plan_is_deterministic_and_noop(self):
        self.assertEqual(self.plan, s.make_plan(self.base / 'install', 19000, self.runtime))
        self.assertEqual(list(self.base.iterdir()), [])

    def test_plan_tampering_and_unsafe_inputs_refused(self):
        for field, value in [('image', 'foreign:latest'), ('port', 80), ('authentication', 'public'),
                             ('docker_socket', True), ('platform', 'unknown')]:
            changed = copy.deepcopy(self.plan)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                s.validate_plan(changed)
        for root, port in ((ROOT / 'runtime', 19000), (self.base / '$INPUT', 19000),
                           (self.base / 'missing/root', 19000), (self.base / 'other', True)):
            with self.subTest(root=root), self.assertRaises(ConfigError):
                s.make_plan(root, port, self.runtime)

    def test_compose_is_loopback_bounded_and_persistent(self):
        spec = s.compose(self.plan, self.owner)
        service = spec['services']['stirling']
        self.assertEqual(service['ports'][0]['host_ip'], '127.0.0.1')
        self.assertTrue(service['read_only'])
        self.assertEqual(service['cap_drop'], ['ALL'])
        self.assertEqual(service['cap_add'], ['CHOWN', 'SETGID', 'SETUID'])
        self.assertNotIn('docker.sock', json.dumps(spec))
        self.assertEqual(service['mem_limit'], '1536m')
        self.assertEqual(service['cpus'], 2)
        self.assertEqual(set(spec['volumes']), set(s.AREAS))
        self.assertEqual({row['target'] for row in service['volumes']}, set(s.AREAS.values()))
        self.assertEqual(service['environment']['SECURITY_ENABLELOGIN'], 'false')
        self.assertEqual(service['environment']['SYSTEM_ENABLEANALYTICS'], 'false')

    def test_inventory_accepts_exact_owned_resources(self):
        self.assertEqual(set(self.inspect(self.resources())['containers']), {'stirling'})

    def test_inventory_refuses_privilege_resource_port_mount_and_foreign_drift(self):
        changes = [
            lambda r: r['containers']['stirling']['HostConfig'].__setitem__('Privileged', True),
            lambda r: r['containers']['stirling']['HostConfig'].__setitem__('CapAdd', ['CAP_CHOWN']),
            lambda r: r['containers']['stirling']['HostConfig'].__setitem__('Memory', 0),
            lambda r: r['containers']['stirling']['HostConfig'].__setitem__('Tmpfs', {}),
            lambda r: r['containers']['stirling']['Config'].__setitem__('Healthcheck', {}),
            lambda r: r['containers']['stirling']['HostConfig'].__setitem__('PortBindings', {}),
            lambda r: r['containers']['stirling']['Mounts'][0].__setitem__('Name', 'foreign'),
            lambda r: r['containers']['stirling']['Config']['Labels'].__setitem__('org.homelab.owner', 'foreign'),
        ]
        for change in changes:
            resources = self.resources()
            change(resources)
            with self.assertRaises(ConfigError):
                self.inspect(resources)

    def test_foreign_network_or_volume_attachment_refused(self):
        resources = self.resources()
        resources['networks'][0]['Containers']['foreign'] = {}
        with self.assertRaises(ConfigError):
            self.inspect(resources)
        with self.assertRaises(ConfigError):
            self.inspect(self.resources(), attached='id-stirling foreign')

    def test_confirmation_and_engine_checked_before_mutation(self):
        with patch.object(s, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            s.operate(self.plan, 'stop', 'wrong')
        runtime.assert_not_called()
        with patch.object(s, 'local_runtime', return_value={'context': 'changed'}), \
                patch.object(s, 'state_read') as state, self.assertRaises(ConfigError):
            s.operate(self.plan, 'status')
        state.assert_not_called()

    def test_running_retry_stop_and_removal_contract(self):
        result, commands = self.simulate('running', self.resources(), 'up')
        self.assertEqual(commands, [])
        self.assertEqual(result['health'], 'healthy')
        _, commands = self.simulate('running', self.resources(), 'stop')
        self.assertEqual(commands, [['stop', '--time', '45', 'id-stirling']])
        with self.assertRaisesRegex(ConfigError, 'Stop'):
            self.simulate('running', self.resources(), 'remove')
        _, commands = self.simulate('stopped', self.resources(False), 'remove')
        self.assertEqual(commands, [['rm', 'id-stirling'], ['network', 'rm', 'network-id']])

    def test_missing_partial_interrupted_and_paused_states_fail_closed(self):
        resources = self.resources()
        resources['containers'] = {}
        with self.assertRaisesRegex(ConfigError, 'missing'):
            self.simulate('running', resources, 'up')
        resources = self.resources()
        resources['volumes'] = resources['volumes'][:-1]
        with self.assertRaisesRegex(ConfigError, 'Incomplete'):
            self.simulate('prepared', resources, 'up')
        with self.assertRaisesRegex(ConfigError, 'Interrupted restore'):
            self.simulate('restore-copying', self.resources(False), 'up')
        resources = self.resources()
        resources['containers']['stirling']['State']['Paused'] = True
        with self.assertRaisesRegex(ConfigError, 'Paused'):
            self.simulate('running', resources, 'stop')

    def test_synthetic_pdf_is_structurally_bounded(self):
        value = s.synthetic_pdf()
        self.assertTrue(value.startswith(b'%PDF-1.4'))
        self.assertTrue(value.endswith(b'%%EOF\n'))
        self.assertIn(b'HomeLab Stirling-PDF validation', value)
        self.assertLess(len(value), 2048)

    def test_compressed_pdf_rotation_syntax_is_bounded_and_visible(self):
        compressed = zlib.compress(b'<</Type /Page /Rotate 90 >>')
        value = (b'%PDF-1.6\n1 0 obj\n<</Filter /FlateDecode /Length '
                 + str(len(compressed)).encode() + b'>>\nstream\n' + compressed
                 + b'\nendstream\nendobj\n%%EOF\n')
        self.assertRegex(s.pdf_syntax(value), rb'/Rotate\s+90\b')
        oversized = zlib.compress(b'x' * 2_000_001)
        value = b'%PDF-1.6\n<</Filter /FlateDecode>>\nstream\n' + oversized + b'\nendstream\n%%EOF\n'
        with self.assertRaisesRegex(ConfigError, 'oversized|exceeds'):
            s.pdf_syntax(value)

    def test_exercise_posts_pdf_and_verifies_rotation(self):
        output = s.synthetic_pdf().replace(b'/MediaBox', b'/Rotate 90 /MediaBox')
        opener = unittest.mock.Mock()
        opener.open.return_value = Response(output)
        with patch.object(s, 'local_runtime', return_value=self.runtime), \
                patch.object(s, 'operation_lock', return_value=nullcontext()), \
                patch.object(s, 'state_read', return_value={'status': 'running', 'owner': self.owner}), \
                patch.object(s, 'inventory', return_value=self.resources()), \
                patch.object(s.urllib.request, 'build_opener', return_value=opener):
            result = s.exercise(self.plan, self.plan['plan_id'])
        request = opener.open.call_args.args[0]
        self.assertTrue(request.full_url.endswith('/api/v1/general/rotate-pdf'))
        self.assertIn(b'name="fileInput"', request.data)
        self.assertIn(b'name="angle"', request.data)
        self.assertEqual(result['rotation_degrees'], 90)
        self.assertFalse(result['persistent_input_retained'])

    def test_exercise_error_is_sanitized(self):
        opener = unittest.mock.Mock()
        opener.open.side_effect = urllib.error.URLError('private response content')
        with patch.object(s, 'local_runtime', return_value=self.runtime), \
                patch.object(s, 'operation_lock', return_value=nullcontext()), \
                patch.object(s, 'state_read', return_value={'status': 'running', 'owner': self.owner}), \
                patch.object(s, 'inventory', return_value=self.resources()), \
                patch.object(s.urllib.request, 'build_opener', return_value=opener), \
                self.assertRaisesRegex(ConfigError, '^Synthetic PDF request failed') as raised:
            s.exercise(self.plan, self.plan['plan_id'])
        self.assertNotIn('private response', str(raised.exception))

    def test_backup_requires_confirmation_and_stopped_service(self):
        with patch.object(s, 'local_runtime') as runtime, self.assertRaises(ConfigError):
            s.backup(self.plan, self.base / 'snapshot', 'wrong')
        runtime.assert_not_called()
        with patch.object(s, 'local_runtime', return_value=self.runtime), \
                patch.object(s, 'operation_lock', return_value=nullcontext()), \
                patch.object(s, 'state_read', return_value={'status': 'running', 'owner': self.owner}), \
                patch.object(s, 'inventory', return_value=self.resources()), self.assertRaises(ConfigError):
            s.backup(self.plan, self.base / 'snapshot', self.plan['plan_id'])


class StirlingBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='homelab stirling backup ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'snapshot'
        create_private_directory(self.root)
        for name in s.AREAS:
            create_private_directory(self.root / name)
        (self.root / 'configs/settings.yml').write_text('system:\n  defaultLocale: en-GB\n', encoding='utf-8')
        (self.root / 'pipeline/example.json').write_text('{}\n', encoding='utf-8')
        (self.root / 'tessdata/eng.traineddata').write_bytes(b'synthetic-language-data')
        for name in s.AREAS:
            s.tree_files(self.root / name, protect_new=True)
        self.trees = {name: s.tree_files(self.root / name) for name in s.AREAS}
        self.manifest = {'kind': 'stirling-stopped-backup-v1',
                         'image': s.load_json(s.MODULE / 'image.json')['image'],
                         'trees': self.trees, 'summary': s.snapshot_summary(self.root)}
        atomic_json(self.root / 'manifest.json', self.manifest)

    def test_backup_evidence_and_recovery_plan(self):
        manifest = s.verify_backup(self.root)
        self.assertTrue(manifest['summary']['settings_present'])
        self.assertEqual(manifest['summary']['file_counts']['tessdata'], 1)
        runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock', 'engine_id': 'test'}
        plan = s.make_plan(self.root.parent / 'restore', 19001, runtime, self.root)
        self.assertEqual(plan['recovery']['manifest_id'], s.digest(manifest))

    def test_changed_missing_or_extra_content_refused(self):
        (self.root / 'configs/settings.yml').write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            s.verify_backup(self.root)
        (self.root / 'configs/settings.yml').write_text('system:\n  defaultLocale: en-GB\n', encoding='utf-8')
        s.tree_files(self.root / 'configs', protect_new=True)
        (self.root / 'custom-files/extra.txt').write_text('extra', encoding='utf-8')
        s.tree_files(self.root / 'custom-files', protect_new=True)
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            s.verify_backup(self.root)

    def test_missing_settings_or_tessdata_refused(self):
        (self.root / 'configs/settings.yml').unlink()
        with self.assertRaisesRegex(ConfigError, 'settings'):
            s.snapshot_summary(self.root)
        (self.root / 'configs/settings.yml').write_text('restored', encoding='utf-8')
        s.tree_files(self.root / 'configs', protect_new=True)
        (self.root / 'tessdata/eng.traineddata').unlink()
        with self.assertRaisesRegex(ConfigError, 'language'):
            s.snapshot_summary(self.root)

    def test_overlap_and_manifest_tampering_refused(self):
        runtime = {'context': 'test', 'endpoint': 'unix:///test/docker.sock', 'engine_id': 'test'}
        with self.assertRaises(ConfigError):
            s.make_plan(self.root / 'restore', 19001, runtime, self.root)
        changed = {**self.manifest, 'image': 'foreign'}
        atomic_json(self.root / 'manifest.json', changed, replace=True)
        with self.assertRaisesRegex(ConfigError, 'image'):
            s.verify_backup(self.root)


if __name__ == '__main__':
    unittest.main()
