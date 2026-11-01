import unittest

from tools.validate_phase5 import ROOT, validate_phase5


class Phase5ReleaseTests(unittest.TestCase):
    def test_personal_data_prerelease_contract_passes(self):
        result = validate_phase5(ROOT)
        self.assertIn('0.6.0-rc.2', result)
        self.assertIn('six application-aware encrypted', result)
        self.assertIn('integrated reusable-workflow gate', result)
        self.assertIn('disabled owner storage/schedule/key-custody policy', result)
        self.assertIn('production adoption remain separate', result)


if __name__ == '__main__':
    unittest.main()
