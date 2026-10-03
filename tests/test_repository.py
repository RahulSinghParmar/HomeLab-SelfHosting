"""Regression checks for the foundation's actual executable capability."""

import copy
import tempfile
import unittest
from pathlib import Path

from tools.validate_repository import (
    ROOT, read_json, validate_catalog, validate_discovery, validate_example, validate_links, validate_repository,
)


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.catalog = read_json(ROOT / "catalog/services.json")
        self.ids = validate_catalog(self.catalog)
        self.plan = read_json(ROOT / "examples/windows.plan.example.json")

    def test_repository_passes(self):
        self.assertIn("PASS:", validate_repository())

    def test_discovery_coverage_reconciles(self):
        validate_discovery(read_json(ROOT / "catalog/discovery.json"), self.ids, ROOT)

    def test_discovery_missing_module_rejected(self):
        discovery = read_json(ROOT / "catalog/discovery.json")
        discovery["modules"].pop()
        with self.assertRaisesRegex(ValueError, "incomplete module"):
            validate_discovery(discovery, self.ids, ROOT)

    def test_discovery_wrong_total_rejected(self):
        discovery = read_json(ROOT / "catalog/discovery.json")
        discovery["container_count"] += 1
        with self.assertRaisesRegex(ValueError, "does not reconcile"):
            validate_discovery(discovery, self.ids, ROOT)

    def test_discovery_absolute_source_rejected(self):
        discovery = read_json(ROOT / "catalog/discovery.json")
        discovery["modules"][0]["sources"] = ["C:/private/compose.yml"]
        with self.assertRaisesRegex(ValueError, "logical private locator"):
            validate_discovery(discovery, self.ids, ROOT)

    def test_discovery_traversal_rejected(self):
        discovery = read_json(ROOT / "catalog/discovery.json")
        discovery["modules"][0]["sources"] = ["../private/compose.yml"]
        with self.assertRaisesRegex(ValueError, "logical private locator"):
            validate_discovery(discovery, self.ids, ROOT)

    def test_discovery_missing_mapping_rejected(self):
        discovery = read_json(ROOT / "catalog/discovery.json")
        discovery["modules"][0]["mapping"]["private"] = ""
        with self.assertRaisesRegex(ValueError, "incomplete configuration"):
            validate_discovery(discovery, self.ids, ROOT)

    def test_all_platform_examples_pass(self):
        for path in (ROOT / "examples").glob("*.plan.example.json"):
            with self.subTest(path=path.name):
                validate_example(read_json(path), self.ids)

    def test_duplicate_module_rejected(self):
        self.catalog["modules"].append(copy.deepcopy(self.catalog["modules"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate module"):
            validate_catalog(self.catalog)

    def test_unknown_dependency_rejected(self):
        self.catalog["modules"][0]["dependencies"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "unknown dependency"):
            validate_catalog(self.catalog)

    def test_dependency_cycle_rejected(self):
        first, second = self.catalog["modules"][:2]
        first["dependencies"] = [second["id"]]
        second["dependencies"] = [first["id"]]
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_catalog(self.catalog)

    def test_self_dependency_rejected(self):
        self.catalog["modules"][0]["dependencies"] = [self.catalog["modules"][0]["id"]]
        with self.assertRaisesRegex(ValueError, "self dependency"):
            validate_catalog(self.catalog)

    def test_false_support_claim_rejected(self):
        self.catalog["modules"][0]["status"] = "validated"
        with self.assertRaisesRegex(ValueError, "cannot claim"):
            validate_catalog(self.catalog)

    def test_credentialed_upstream_rejected(self):
        self.catalog["modules"][0]["upstream"] = "https://user:example@example.com/repo"
        with self.assertRaisesRegex(ValueError, "HTTPS upstream"):
            validate_catalog(self.catalog)

    def test_unknown_service_rejected(self):
        self.plan["services"].append("missing")
        with self.assertRaisesRegex(ValueError, "unknown selected"):
            validate_example(self.plan, self.ids)

    def test_duplicate_selection_rejected(self):
        self.plan["services"].append(self.plan["services"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_example(self.plan, self.ids)

    def test_examples_cannot_be_live_plans(self):
        self.plan["example_only"] = False
        with self.assertRaisesRegex(ValueError, "example only"):
            validate_example(self.plan, self.ids)

    def test_secret_value_field_rejected(self):
        self.plan["smtp_password"] = "example"
        with self.assertRaisesRegex(ValueError, "unexpected fields"):
            validate_example(self.plan, self.ids)

    def test_bad_paths_rejected(self):
        for path in ("relative", "D:\\", "D:\\data\\..\\backup"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.plan["paths"]["backup_root"] = path
                validate_example(self.plan, self.ids)

    def test_overlapping_paths_rejected(self):
        self.plan["paths"]["backup_root"] = self.plan["paths"]["media_root"] + "\\backups"
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_example(self.plan, self.ids)

    def test_windows_case_overlap_rejected(self):
        self.plan["paths"]["backup_root"] = self.plan["paths"]["media_root"].lower()
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_example(self.plan, self.ids)

    def test_public_exposure_rejected(self):
        self.plan["public_domain"] = "example.com"
        with self.assertRaisesRegex(ValueError, "public exposure"):
            validate_example(self.plan, self.ids)

    def test_boolean_budget_rejected(self):
        self.plan["resource_budget"]["cpu_limit"] = True
        with self.assertRaisesRegex(ValueError, "resource budget"):
            validate_example(self.plan, self.ids)

    def test_negative_retention_rejected(self):
        self.plan["retention"]["daily"] = -1
        with self.assertRaisesRegex(ValueError, "retention"):
            validate_example(self.plan, self.ids)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.json"
            path.write_text('{"key":1,"key":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                read_json(path)

    def test_broken_local_link_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("[missing](missing.md)", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "broken local link"):
                validate_links(root)

    def test_escaping_link_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("[outside](../outside.md)", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "leaves repository"):
                validate_links(root)


if __name__ == "__main__":
    unittest.main()
