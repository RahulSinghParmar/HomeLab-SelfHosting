import json
import unittest

from tools.validate_phase5 import (
    EXPECTED_INTEGRATED_MODULES,
    ROOT,
    validate_integrated_contract,
    validate_reusable_workflow,
)


class Phase5IntegratedTests(unittest.TestCase):
    def test_integrated_contract_passes(self):
        result = validate_integrated_contract(ROOT)
        self.assertIn('six reusable encrypted recovery workflows', result)
        self.assertIn('distinct secrets', result)

    def test_manifest_has_six_unique_modules_and_secrets(self):
        manifest = json.loads(
            (ROOT / 'modules/phase5/recovery.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['modules'], list(EXPECTED_INTEGRATED_MODULES))
        self.assertEqual(len({item['id'] for item in manifest['modules']}), 6)
        self.assertEqual(len({item['secret'] for item in manifest['modules']}), 6)

    def test_each_recovery_workflow_is_reusable(self):
        for module in EXPECTED_INTEGRATED_MODULES:
            with self.subTest(module=module['id']):
                text = (ROOT / '.github/workflows' / module['workflow']).read_text(
                    encoding='utf-8')
                validate_reusable_workflow(text, module)

    def test_missing_reusable_trigger_is_rejected(self):
        module = EXPECTED_INTEGRATED_MODULES[0]
        path = ROOT / '.github/workflows' / module['workflow']
        text = path.read_text(encoding='utf-8').replace(
            '  workflow_call:', '  disabled_workflow_call:', 1)
        with self.assertRaisesRegex(ValueError, 'manual and reusable'):
            validate_reusable_workflow(text, module)

    def test_automatic_trigger_is_rejected(self):
        module = EXPECTED_INTEGRATED_MODULES[0]
        path = ROOT / '.github/workflows' / module['workflow']
        text = path.read_text(encoding='utf-8').replace(
            '  workflow_dispatch:', '  workflow_dispatch:\n  push:', 1)
        with self.assertRaisesRegex(ValueError, 'must not run automatically'):
            validate_reusable_workflow(text, module)

    def test_action_revision_drift_is_rejected(self):
        module = EXPECTED_INTEGRATED_MODULES[0]
        path = ROOT / '.github/workflows' / module['workflow']
        text = path.read_text(encoding='utf-8').replace(
            'actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333',
            'actions/download-artifact@main', 1)
        with self.assertRaisesRegex(ValueError, 'artifact action revisions changed'):
            validate_reusable_workflow(text, module)


if __name__ == '__main__':
    unittest.main()
