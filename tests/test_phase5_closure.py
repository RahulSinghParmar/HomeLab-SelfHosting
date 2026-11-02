import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.validate_phase5_closure import ROOT, validate_closure


class Phase5ClosureTests(unittest.TestCase):
    def test_final_closure_contract_passes(self):
        result = validate_closure(ROOT)
        self.assertIn("six application-consistent backups", result)
        self.assertIn("nonempty semantic restore proofs", result)
        self.assertIn("restore-gated 7/4/3 retention", result)

    def test_each_module_has_nonempty_fixture_and_semantic_proof(self):
        closure = json.loads((ROOT / "modules/phase5/closure.json").read_text())
        self.assertEqual(len(closure["modules"]), 6)
        for module in closure["modules"]:
            with self.subTest(module=module["id"]):
                self.assertTrue(module["fixture_marker"])
                self.assertGreaterEqual(len(module["authoritative_material"]), 3)
                self.assertGreaterEqual(len(module["semantic_proof_fields"]), 3)

    def test_closure_does_not_claim_production_adoption(self):
        closure = json.loads((ROOT / "modules/phase5/closure.json").read_text())
        self.assertFalse(closure["production_adoption"])
        self.assertFalse(closure["production_data_used"])
        self.assertTrue(closure["encryption"]["recovery_key_separate_from_repository"])
        self.assertTrue(closure["retention"]["apply_requires_restore_verified"])

    def test_missing_semantic_proof_field_is_rejected(self):
        closure = json.loads((ROOT / "modules/phase5/closure.json").read_text())
        closure["modules"][0]["semantic_proof_fields"] = []

        def altered_load(path):
            if Path(path).name == "closure.json":
                return closure
            return json.loads(Path(path).read_text(encoding="utf-8"))

        with patch("tools.validate_phase5_closure.load_json", side_effect=altered_load):
            with self.assertRaisesRegex(ValueError, "semantic restore proof"):
                validate_closure(ROOT)


if __name__ == "__main__":
    unittest.main()
