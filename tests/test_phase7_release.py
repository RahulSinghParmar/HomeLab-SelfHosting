import unittest

from tools.validate_phase7 import ROOT, validate_phase7


class Phase7ReleaseTests(unittest.TestCase):
    def test_code_server_foundation_contract_passes(self):
        result = validate_phase7(ROOT)
        self.assertIn("0.8.0-alpha.1", result)
        self.assertIn("multiarchitecture code-server", result)
        self.assertIn("compile/recreation/recovery", result)


if __name__ == "__main__":
    unittest.main()
