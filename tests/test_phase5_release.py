import unittest

from tools.validate_phase5 import ROOT, validate_phase5


class Phase5ReleaseTests(unittest.TestCase):
    def test_personal_data_prerelease_contract_passes(self):
        result = validate_phase5(ROOT)
        self.assertIn('Paperless off-host recovery', result)
        self.assertIn('AFFiNE sync', result)


if __name__ == '__main__':
    unittest.main()
