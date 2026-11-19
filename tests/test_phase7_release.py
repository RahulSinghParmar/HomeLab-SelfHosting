import unittest

from tools.validate_phase7 import ROOT, validate_phase7


class Phase7ReleaseTests(unittest.TestCase):
    def test_development_matrix_and_coolify_contract_passes(self):
        result = validate_phase7(ROOT)
        self.assertIn("0.8.0-rc.1", result)
        self.assertIn("code-server and Matrix", result)
        self.assertIn("Coolify adapter", result)
        self.assertIn("production migration", result)
        self.assertIn("Matrix/Element/TURN", result)
        self.assertIn("native Windows lifecycle", result)


if __name__ == "__main__":
    unittest.main()
