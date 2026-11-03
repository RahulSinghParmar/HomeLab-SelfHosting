import unittest

from tools.validate_phase6 import ROOT, validate_phase6


class Phase6ReleaseTests(unittest.TestCase):
    def test_media_and_immich_contract_passes(self):
        result = validate_phase6(ROOT)
        self.assertIn("0.7.0-alpha.3", result)
        self.assertIn("Immich v3.3.5", result)
        self.assertIn("protected-original recovery", result)
        self.assertIn("encrypted off-host full-data", result)
        self.assertIn("clean-runner restoration", result)


if __name__ == "__main__":
    unittest.main()
