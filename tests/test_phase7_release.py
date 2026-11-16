import unittest

from tools.validate_phase7 import ROOT, validate_phase7


class Phase7ReleaseTests(unittest.TestCase):
    def test_development_and_matrix_foundation_contract_passes(self):
        result = validate_phase7(ROOT)
        self.assertIn("0.8.0-alpha.2", result)
        self.assertIn("code-server and Matrix", result)
        self.assertIn("room/message/media recovery", result)


if __name__ == "__main__":
    unittest.main()
