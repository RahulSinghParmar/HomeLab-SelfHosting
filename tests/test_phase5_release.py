import unittest

from tools.validate_phase5 import ROOT, validate_phase5


class Phase5ReleaseTests(unittest.TestCase):
    def test_paperless_prerelease_contract_passes(self):
        self.assertIn('off-host recovery contract', validate_phase5(ROOT))


if __name__ == '__main__':
    unittest.main()
