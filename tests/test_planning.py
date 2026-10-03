import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from homelab.config import ConfigError, ROOT, canonical, catalogs, load_json, logical_path, resolve, validate_config, validate_planning
from homelab.io import write_private
from homelab.planner import create_plan
from homelab.wizard import configure


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.modules, self.planning = catalogs()
        self.config = load_json(ROOT / 'examples/windows.settings.example.json')

    def test_settings_examples(self):
        for path in (ROOT / 'examples').glob('*.settings.example.json'):
            with self.subTest(path=path.name):
                result = create_plan(load_json(path), self.modules, self.planning)
                self.assertEqual(result['issues'], [])
                self.assertFalse(result['execution_allowed'])

    def test_selection_order_deterministic(self):
        first = create_plan(self.config, self.modules, self.planning)
        self.config['services'].reverse()
        self.assertEqual(first, create_plan(self.config, self.modules, self.planning))

    def test_plan_hash_binds_content(self):
        plan = create_plan(self.config, self.modules, self.planning)
        fingerprint = plan.pop('plan_id')
        self.assertEqual(fingerprint, hashlib.sha256(canonical(plan).encode()).hexdigest())

    def test_plan_hash_binds_private_inputs_without_exposing_them(self):
        first = create_plan(self.config, self.modules, self.planning)
        self.config['paths']['media_root'] = 'F:\\PrivateMedia'
        second = create_plan(self.config, self.modules, self.planning)
        self.assertNotEqual(first['plan_id'], second['plan_id'])
        self.assertNotIn('PrivateMedia', json.dumps(second))
        self.assertNotIn('example-lab', json.dumps(second))

    def test_no_operations_or_secret_values(self):
        result = create_plan(self.config, self.modules, self.planning)
        self.assertEqual(result['deployment_operations'], [])
        self.assertFalse(result['host_checked'])

    def test_dependency_closure_and_stable_order(self):
        modules = {'app': {'dependencies': ['cache', 'database']}, 'cache': {'dependencies': []}, 'database': {'dependencies': []}}
        self.assertEqual(resolve(['app', 'cache'], modules), ['cache', 'database', 'app'])

    def test_cycle_unknown_and_self_dependency(self):
        for modules in ({'a': {'dependencies': ['missing']}}, {'a': {'dependencies': ['a']}},
                        {'a': {'dependencies': ['b']}, 'b': {'dependencies': ['a']}}):
            with self.subTest(modules=modules), self.assertRaises(ConfigError):
                resolve(['a'], modules)

    def test_reject_secrets_and_unknown_fields(self):
        self.config['password'] = 'do-not-print-this'
        with self.assertRaises(ConfigError) as result:
            validate_config(self.config, self.modules, self.planning)
        self.assertNotIn('do-not-print-this', str(result.exception))

    def test_refuse_unsupported_modes_and_gpu(self):
        for key, value in [('mode', 'adopt'), ('mode', 'restore'), ('mode', 'replica'), ('gpu', 'enabled'), ('access', 'public')]:
            config = copy.deepcopy(self.config)
            config[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ConfigError):
                validate_config(config, self.modules, self.planning)

    def test_unknown_and_duplicate_services(self):
        for selection in ([], ['missing'], ['glance', 'glance'], [123]):
            self.config['services'] = selection
            with self.subTest(selection=selection), self.assertRaises(ConfigError):
                validate_config(self.config, self.modules, self.planning)

    def test_bad_paths(self):
        for value in ('relative', 'C:\\', 'C:\\data\\..\\other', '\\\\server\\share\\data', 'C:\\NUL\\data', 'C:\\data:stream', 'C:\\a.\\data', 'C:\\a\npassword'):
            with self.subTest(path=value), self.assertRaises(ConfigError):
                logical_path(value, 'windows')
        for value in ('/', 'relative', '/data/../other', '//server/share'):
            with self.subTest(path=value), self.assertRaises(ConfigError):
                logical_path(value, 'linux')

    def test_paths_with_spaces(self):
        self.config['paths']['media_root'] = 'F:\\My Media'
        validate_config(self.config, self.modules, self.planning)
        self.assertEqual(str(logical_path('/srv/My Media', 'linux')), '/srv/My Media')

    def test_case_insensitive_windows_overlap(self):
        self.config['paths']['backup_root'] = self.config['paths']['media_root'].lower()
        with self.assertRaisesRegex(ConfigError, 'overlap'):
            validate_config(self.config, self.modules, self.planning)

    def test_nested_root_rejected(self):
        self.config['paths']['backup_root'] = self.config['paths']['media_root'] + '\\backups'
        with self.assertRaisesRegex(ConfigError, 'overlap'):
            validate_config(self.config, self.modules, self.planning)

    def test_named_volume_cannot_claim_custom_drive(self):
        self.config['paths']['database_root'] = 'F:\\Database'
        with self.assertRaisesRegex(ConfigError, 'independently'):
            validate_config(self.config, self.modules, self.planning)

    def test_bind_database_is_explicit_unvalidated_intent(self):
        self.config['database_storage'] = 'bind'
        self.config['paths']['database_root'] = 'F:\\Database'
        plan = create_plan(self.config, self.modules, self.planning)
        self.assertTrue(any('unvalidated' in warning for warning in plan['warnings']))

    def test_overrides_must_be_selected_and_independent(self):
        for overrides in ({'missing': {'media_root': 'F:\\Custom'}}, {'glance': {'media_root': 'D:\\Homelab\\Media\\custom'}},
                          {'glance': {'database_root': 'F:\\Custom'}}):
            self.config['service_paths'] = overrides
            with self.subTest(overrides=overrides), self.assertRaises(ConfigError):
                validate_config(self.config, self.modules, self.planning)

    def test_independent_override(self):
        self.config['service_paths'] = {'paperless-ngx': {'media_root': 'F:\\Documents'}}
        result = create_plan(self.config, self.modules, self.planning)
        self.assertEqual(result['storage']['per_service_overrides'], {'paperless-ngx': ['media_root']})
        self.assertNotIn('Documents', canonical(result))

    def test_invalid_numbers(self):
        for value in (0, -1, True, 1.5, '6', 100_000):
            self.config['resource_budget']['memory_gib'] = value
            with self.subTest(value=value), self.assertRaises(ConfigError):
                validate_config(self.config, self.modules, self.planning)

    def test_budget_issue_not_silently_clamped(self):
        self.config['resource_budget']['memory_gib'] = 1
        result = create_plan(self.config, self.modules, self.planning)
        self.assertTrue(any(issue['code'] == 'memory-budget' for issue in result['issues']))
        self.assertEqual(result['resources']['budget']['memory_gib'], 1)

    def test_port_collision(self):
        self.config['port_overrides'] = {'glance.http': 3001}
        self.assertTrue(any(issue['code'] == 'port-overlap' for issue in create_plan(self.config, self.modules, self.planning)['issues']))

    def test_bad_port_overrides(self):
        for overrides in ({'missing.http': 1000}, {'glance.http': True}, {'glance.http': 0}, {'glance.http': 65536}):
            self.config['port_overrides'] = overrides
            with self.subTest(overrides=overrides), self.assertRaises(ConfigError):
                validate_config(self.config, self.modules, self.planning)

    def test_udp_range_bounds(self):
        self.config['services'] = ['matrix']
        self.config['port_overrides'] = {'matrix.relay': 65530}
        with self.assertRaises(ConfigError):
            validate_config(self.config, self.modules, self.planning)

    def test_different_protocol_same_port_allowed(self):
        self.config['services'] = ['matrix']
        result = create_plan(self.config, self.modules, self.planning)
        self.assertFalse(any(issue['code'] == 'port-overlap' for issue in result['issues']))

    def test_planning_metadata_coverage(self):
        planning = load_json(ROOT / 'catalog/planning.json')
        planning['modules'].pop('glance')
        with self.assertRaises(ConfigError):
            validate_planning(planning, set(self.modules))

    def test_json_duplicate_and_non_finite(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'input.json'
            for content in ('{"key":1,"key":2}', '{"value":NaN}'):
                source.write_text(content, encoding='utf-8')
                with self.subTest(content=content), self.assertRaises(ConfigError):
                    load_json(source)

    def test_output_exclusive_and_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary).resolve() / 'settings.json'
            write_private(destination, self.config)
            self.assertEqual(load_json(destination), self.config)
            with self.assertRaises(ConfigError):
                write_private(destination, {})
            self.assertEqual(load_json(destination), self.config)

    def test_output_refuses_repository_relative_and_missing_parent(self):
        for destination in (ROOT / 'unsafe.json', Path('relative.json'), ROOT / 'missing-parent/settings.json'):
            with self.subTest(destination=destination), self.assertRaises(ConfigError):
                write_private(destination, {})

    def test_output_refuses_other_git_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            (directory / '.git').mkdir()
            with self.assertRaises(ConfigError):
                write_private(directory / 'settings.json', {})

    def test_wizard_save_and_cancel(self):
        # selection, OS, architecture, identity, three roots, DB policy, access,
        # CPU/RAM/headroom, disk reserve, custom storage, port overrides, save
        answers = ['', 'windows', 'amd64', '', '', '', '', '', '', '', '', '', '', '', '', 'y']
        with patch('homelab.wizard.host_platform', return_value='windows'), patch('homelab.wizard.host_architecture', return_value='amd64'):
            iterator = iter(answers)
            result = configure(self.modules, self.planning, ask=lambda _: next(iterator), tell=lambda _: None)
            self.assertEqual(result['services'], ['glance', 'uptime-kuma'])
            answers[-1] = 'n'
            iterator = iter(answers)
            self.assertIsNone(configure(self.modules, self.planning, ask=lambda _: next(iterator), tell=lambda _: None))

    def test_cli_refuses_deployment_command(self):
        result = subprocess.run([sys.executable, '-m', 'homelab', 'apply'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)

    def test_offline_cli_repeatable_from_other_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            arguments = [sys.executable, str(ROOT / 'homelab_cli.py'), 'plan', '--config', str(ROOT / 'examples/windows.settings.example.json'), '--json']
            first = subprocess.run(arguments, cwd=temporary, capture_output=True, text=True, check=True)
            second = subprocess.run(arguments, cwd=temporary, capture_output=True, text=True, check=True)
            self.assertEqual(first.stdout, second.stdout)
            self.assertFalse(json.loads(first.stdout)['execution_allowed'])

    def test_native_launcher_output_and_exit_code(self):
        prefix = (['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(ROOT / 'bootstrap.ps1')]
                  if os.name == 'nt' else ['sh', str(ROOT / 'bootstrap.sh')])
        with tempfile.TemporaryDirectory(prefix='homelab launcher ') as temporary:
            result = subprocess.run(prefix + ['plan', '--config', str(ROOT / 'examples/windows.settings.example.json'), '--json'],
                                    cwd=temporary, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)['execution_allowed'])
            invalid = subprocess.run(prefix + ['apply'], cwd=temporary, capture_output=True, text=True)
            self.assertEqual(invalid.returncode, 2)


if __name__ == '__main__':
    unittest.main()
