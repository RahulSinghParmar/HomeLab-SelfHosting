import unittest

from tools.validate_phase4 import ROOT, validate_digest, validate_phase4


class Phase4ReleaseTests(unittest.TestCase):
    def test_current_release_contract_passes(self):
        self.assertIn("5 isolated modules", validate_phase4(ROOT))

    def test_tag_only_image_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exact sha256"):
            validate_digest("example/image:latest", "fixture")

    def test_malformed_digest_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exact sha256"):
            validate_digest("example/image@sha256:not-a-digest", "fixture")


if __name__ == "__main__":
    unittest.main()
