import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.validate_phase6_closure import ROOT, validate_closure


class Phase6ClosureTests(unittest.TestCase):
    def test_final_closure_contract_passes(self):
        result = validate_closure(ROOT)
        self.assertIn("eight explicit media integrations", result)
        self.assertIn("stopped-state restore validation", result)
        self.assertIn("Intel QSV with CPU fallback", result)

    def test_closure_does_not_claim_production_adoption(self):
        value = json.loads((ROOT / "modules/phase6/closure.json").read_text())
        self.assertFalse(value["production_adoption"])
        self.assertFalse(value["production_media_used"])
        self.assertEqual([item["id"] for item in value["modules"]],
                         ["immich", "media-management", "jellyfin"])

    def test_removed_media_component_is_rejected(self):
        value = json.loads((ROOT / "modules/phase6/closure.json").read_text())
        changed = copy.deepcopy(value)
        changed["modules"][1]["components"].pop()

        def altered_load(path):
            if Path(path).name == "closure.json":
                return changed
            return json.loads(Path(path).read_text(encoding="utf-8"))

        with patch("tools.validate_phase6_closure.load", side_effect=altered_load):
            with self.assertRaisesRegex(ValueError, "Media-management"):
                validate_closure(ROOT)


if __name__ == "__main__":
    unittest.main()
