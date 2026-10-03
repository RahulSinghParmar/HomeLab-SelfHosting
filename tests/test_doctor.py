import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from homelab.config import ROOT, catalogs, load_json
from homelab.doctor import GIB, diagnose, inspect_storage, local_endpoint, parse_lsof, parse_ss, host_ports, time_status


class FakeHost:
    def __init__(self, endpoint='unix:///var/run/docker.sock', engine=True, rows='', os_type='linux', memory=16 * GIB):
        self.endpoint, self.engine, self.rows, self.os_type, self.memory = endpoint, engine, rows, os_type, memory
        self.calls = []

    def __call__(self, arguments):
        self.calls.append(arguments)
        if arguments[0] != 'docker':
            return 'yes' if arguments[0] == 'timedatectl' else None
        if arguments[1:3] == ['context', 'show']:
            return 'fixture-local'
        if arguments[1:3] == ['context', 'inspect']:
            return json.dumps(self.endpoint)
        if arguments[1:3] != ['--context', 'fixture-local']:
            raise AssertionError('Daemon operations must pin the inspected context')
        verb = arguments[3]
        if verb == 'info':
            return json.dumps({'os': self.os_type, 'architecture': 'x86_64', 'cpus': 8, 'memory': self.memory}) if self.engine else None
        if verb == 'compose':
            self.assert_readonly_compose(arguments)
            return '5.5.1'
        if verb == 'ps':
            return self.rows
        raise AssertionError('Unexpected daemon operation')

    @staticmethod
    def assert_readonly_compose(arguments):
        if arguments[4:6] != ['version', '--short']:
            raise AssertionError('Only Compose version inspection is allowed')


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.modules, self.planning = catalogs()
        self.config = load_json(ROOT / 'examples/linux.settings.example.json')

    def check(self, runner=None, **kwargs):
        return diagnose(self.config, self.modules, self.planning, run=runner or FakeHost(), environment=kwargs.pop('environment', {}),
                        system=kwargs.pop('system', 'linux'), architecture=kwargs.pop('architecture', 'amd64'),
                        memory=kwargs.pop('memory', (32 * GIB, 16 * GIB)), ports=kwargs.pop('ports', set()),
                        storage_probe=lambda _: [], **kwargs)

    def test_good_probes_still_do_not_authorize_deployment(self):
        result = self.check()
        self.assertEqual(result['status'], 'review-required')
        self.assertFalse(result['execution_allowed'])

    def test_remote_and_malformed_endpoints_never_contact_daemon(self):
        for endpoint in ('ssh://user@example.com', 'tcp://example.com:2375', 'npipe:////remote/pipe/docker', None, 'unix://remote/var/run/docker.sock'):
            runner = FakeHost(endpoint=endpoint)
            result = self.check(runner)
            self.assertEqual(result['status'], 'blocked')
            self.assertFalse(any('--context' in call for call in runner.calls))
            self.assertNotIn('user@example.com', json.dumps(result))

    def test_endpoint_overrides_prevent_any_docker_query(self):
        for key in ('DOCKER_HOST', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
            runner = FakeHost()
            result = self.check(runner, environment={key: 'private-value'})
            self.assertFalse(any(call[0] == 'docker' for call in runner.calls))
            self.assertEqual(result['status'], 'blocked')
            self.assertNotIn('private-value', json.dumps(result))

    def test_valid_local_endpoints(self):
        self.assertTrue(local_endpoint('npipe:////./pipe/dockerDesktopLinuxEngine'))
        self.assertTrue(local_endpoint('unix:///var/run/docker.sock'))

    def test_absent_cli(self):
        self.assertEqual(self.check(lambda _: None)['status'], 'blocked')

    def test_daemon_unavailable(self):
        self.assertTrue(any(check['name'] == 'docker-engine' and check['status'] == 'block' for check in self.check(FakeHost(engine=False))['checks']))

    def test_wrong_engine_os(self):
        self.assertEqual(self.check(FakeHost(os_type='windows'))['status'], 'blocked')

    def test_unknown_engine_payload(self):
        def runner(args):
            if 'info' in args:
                return 'unexpected sensitive output'
            return self.fake(args)
        self.fake = FakeHost()
        result = self.check(runner)
        self.assertEqual(result['status'], 'blocked')
        self.assertNotIn('sensitive output', json.dumps(result))

    def test_engine_memory_limit(self):
        result = self.check(FakeHost(memory=2 * GIB))
        self.assertTrue(any(check['name'] == 'engine-budget' and check['status'] == 'block' for check in result['checks']))

    def test_host_memory_headroom(self):
        result = self.check(memory=(8 * GIB, 2 * GIB))
        self.assertTrue(any(check['name'] == 'host-headroom' and check['status'] == 'block' for check in result['checks']))

    def test_foreign_target(self):
        result = self.check(architecture='arm64')
        self.assertTrue(any(check['name'] == 'target' and check['status'] == 'block' for check in result['checks']))

    def test_unknown_memory_is_not_pass(self):
        result = self.check(memory=(None, None))
        self.assertTrue(any(check['name'] == 'host-headroom' and check['status'] == 'warn' for check in result['checks']))

    def test_listener_conflict(self):
        result = self.check(ports={('tcp', 8081)})
        self.assertTrue(any(check['name'] == 'port:glance.http' and check['status'] == 'block' for check in result['checks']))

    def test_unknown_listener_inventory_blocks(self):
        with patch('homelab.doctor.host_ports', return_value=None):
            result = self.check(ports=None)
        self.assertTrue(any(check['name'] == 'host-ports' and check['status'] == 'block' for check in result['checks']))

    def test_existing_project(self):
        rows = json.dumps({'project': 'hl-example-lab-glance', 'ports': ''})
        result = self.check(FakeHost(rows=rows))
        self.assertTrue(any(check['name'] == 'docker-existing' and check['status'] == 'block' for check in result['checks']))

    def test_docker_published_port_not_visible_to_native_probe(self):
        rows = json.dumps({'project': 'private-unrelated', 'ports': '127.0.0.1:8081->8080/tcp, [::]:13001->3001/tcp'})
        result = self.check(FakeHost(rows=rows))
        self.assertTrue(any(check['name'] == 'docker-ports' and check['status'] == 'block' for check in result['checks']))
        self.assertNotIn('private-unrelated', json.dumps(result))

    def test_ss_ipv4_ipv6_udp(self):
        text = 'tcp LISTEN 0 128 0.0.0.0:8080 0.0.0.0:*\nudp UNCONN 0 0 [::]:3478 [::]:*'
        self.assertEqual(parse_ss(text), {('tcp', 8080), ('udp', 3478)})

    def test_ss_invalid_is_not_empty_success(self):
        with self.assertRaises(ValueError):
            parse_ss('not a listener table')

    def test_lsof_protocol_fields(self):
        self.assertEqual(parse_lsof('p123\nf4\nPTCP\nn*:8096\nf5\nPUDP\nn[::1]:3478\n'), {('tcp', 8096), ('udp', 3478)})

    def test_lsof_invalid_is_not_empty_success(self):
        self.assertIsNone(host_ports('macos', lambda _: 'unrecognized output'))

    def test_windows_listener_json_and_invalid_data(self):
        self.assertEqual(host_ports('windows', lambda _: '[{"protocol":"tcp","port":3001}]'), {('tcp', 3001)})
        self.assertIsNone(host_ports('windows', lambda _: 'private malformed data'))

    def test_localized_time_is_unknown(self):
        self.assertEqual(time_status('windows', lambda _: 'localized status')[0], 'warn')
        self.assertEqual(time_status('linux', lambda _: 'no')[0], 'warn')
        self.assertEqual(time_status('linux', lambda _: 'yes')[0], 'pass')

    def test_windows_local_clock_not_accepted(self):
        self.assertEqual(time_status('windows', lambda _: 'Leap Indicator: 0\nSource: Local CMOS Clock')[0], 'warn')


class StorageTests(unittest.TestCase):
    def settings(self, base):
        system = 'windows' if os.name == 'nt' else 'linux'
        return {'platform': system, 'paths': {role: str(base / role) for role in ('installation_root', 'media_root', 'backup_root')} | {'database_root': None},
                'service_paths': {}, 'storage_reserve_gib': {role: 1 for role in ('installation_root', 'media_root', 'backup_root', 'database_root')}}

    def test_nonexistent_paths_are_only_inspected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            results = inspect_storage(self.settings(base))
            self.assertFalse(any(check['status'] == 'block' for check in results))
            self.assertEqual(list(base.iterdir()), [])

    def test_occupied_root_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            (base / 'media_root').mkdir()
            (base / 'media_root' / 'existing.txt').write_text('do not touch', encoding='utf-8')
            results = inspect_storage(self.settings(base))
            self.assertTrue(any(check['name'] == 'storage.media_root' and check['status'] == 'block' for check in results))

    def test_shared_filesystem_reserves_are_summed(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('homelab.doctor.shutil.disk_usage', return_value=type('Disk', (), {'free': 2 * GIB})()):
                results = inspect_storage(self.settings(Path(directory).resolve()))
            self.assertTrue(any(check['name'].startswith('storage.capacity:') and check['status'] == 'block' for check in results))

    def test_inaccessible_directory(self):
        with tempfile.TemporaryDirectory() as directory, patch('homelab.doctor.os.access', return_value=False):
            results = inspect_storage(self.settings(Path(directory).resolve()))
            self.assertTrue(any(check['status'] == 'block' for check in results))

    def test_repository_storage_refused(self):
        settings = self.settings(ROOT / 'never-created')
        results = inspect_storage(settings)
        self.assertTrue(any(check['status'] == 'block' for check in results))
        self.assertFalse((ROOT / 'never-created').exists())

    def test_other_repository_storage_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            (base / '.git').mkdir()
            results = inspect_storage(self.settings(base))
            self.assertTrue(all(check['status'] == 'block' for check in results if check['name'] != 'storage.docker-disk'))

    def test_symlink_guard_without_creating_link(self):
        with tempfile.TemporaryDirectory() as directory, patch('homelab.doctor.Path.is_symlink', return_value=True):
            results = inspect_storage(self.settings(Path(directory)))
            self.assertTrue(all(check['status'] == 'block' for check in results if check['name'] != 'storage.docker-disk'))

    def test_symlink_rejected_when_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            target = base / 'target'
            target.mkdir()
            link = base / 'link'
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest('Symlink creation not permitted in this test environment')
            result = inspect_storage(self.settings(link))
            self.assertTrue(any(check['status'] == 'block' for check in result))


if __name__ == '__main__':
    unittest.main()
