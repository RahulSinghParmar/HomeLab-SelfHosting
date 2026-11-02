import unittest

from tools.validate_phase6 import ROOT, validate_phase6


class Phase6ReleaseTests(unittest.TestCase):
    def test_media_foundation_contract_passes(self):
        result = validate_phase6(ROOT)
        self.assertIn("0.7.0-alpha.1", result)
        self.assertIn("Immich v3.3.5", result)
        self.assertIn("heavy jobs manual", result)
        self.assertIn("fails closed to CPU", result)


if __name__ == "__main__":
    unittest.main()
