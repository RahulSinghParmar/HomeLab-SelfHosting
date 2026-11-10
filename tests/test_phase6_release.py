import unittest

from tools.validate_phase6 import ROOT, validate_phase6


class Phase6ReleaseTests(unittest.TestCase):
    def test_media_immich_and_jellyfin_contract_passes(self):
        result = validate_phase6(ROOT)
        self.assertIn("0.7.0-alpha.5", result)
        self.assertIn("Immich protected-original", result)
        self.assertIn("Jellyfin same-version", result)
        self.assertIn("exact synthetic direct play", result)


if __name__ == "__main__":
    unittest.main()
