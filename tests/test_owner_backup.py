import copy
import json
import unittest
from pathlib import Path

from homelab.config import ConfigError
from homelab.owner_backup import make_plan, public_plan, validate_policy


ROOT = Path(__file__).resolve().parents[1]


def example():
    return json.loads((ROOT / "modules/phase5/owner-backup-policy.example.json").read_text())


class OwnerBackupPolicyTests(unittest.TestCase):
    def test_example_is_valid_but_not_activation_ready(self):
        policy = validate_policy(example())
        plan = make_plan(policy)
        self.assertEqual(plan["execution"], "disabled-design-only")
        self.assertEqual(plan["readiness"]["status"], "blocked")
        self.assertFalse(plan["readiness"]["activation_included"])
        self.assertEqual(plan["capacity"]["minimum_per_repository_gib"], 640.0)
        self.assertEqual(len(plan["readiness"]["blockers"]), 6)

    def test_ready_policy_still_requires_separate_activation(self):
        policy = example()
        for repository in policy["storage"]["repositories"]:
            repository["owner_confirmed"] = True
        for key_copy in policy["storage"]["key_custody"]["recovery_copies"]:
            key_copy["owner_confirmed"] = True
        policy["notifications"]["configured"] = True
        policy["recovery_drill"] = {
            "production_data_completed": True,
            "last_completed_utc": "2026-11-01T00:00:00Z",
            "evidence_reference": "private-evidence-record",
        }
        plan = make_plan(policy)
        self.assertEqual(plan["readiness"]["status"], "ready-for-separate-activation-review")
        self.assertFalse(plan["readiness"]["activation_included"])
        self.assertEqual(plan["readiness"]["blockers"], [])

    def test_repository_on_host_is_rejected(self):
        policy = example()
        policy["storage"]["repositories"][0]["device_id"] = "homelab-host"
        with self.assertRaisesRegex(ConfigError, "away from the host"):
            validate_policy(policy)

    def test_recovery_key_on_repository_device_is_rejected(self):
        policy = example()
        policy["storage"]["key_custody"]["recovery_copies"][0]["device_id"] = (
            "backup-appliance-one")
        with self.assertRaisesRegex(ConfigError, "separate from host and repositories"):
            validate_policy(policy)

    def test_overlapping_paths_are_rejected(self):
        policy = example()
        policy["storage"]["key_custody"]["operational"]["path"] = (
            "C:\\HomeLabBackup\\staging\\keys")
        with self.assertRaisesRegex(ConfigError, "storage paths overlap"):
            validate_policy(policy)

    def test_relative_paths_are_rejected(self):
        policy = example()
        policy["storage"]["staging"]["path"] = "relative\\staging"
        with self.assertRaisesRegex(ConfigError, "path must be absolute"):
            validate_policy(policy)

    def test_secret_value_fields_are_rejected(self):
        policy = example()
        policy["notifications"]["token"] = "must-never-enter-policy"
        with self.assertRaisesRegex(ConfigError, "secret references only"):
            validate_policy(policy)

    def test_schedule_must_be_disabled_and_hidden(self):
        policy = example()
        policy["schedule"]["activation"] = "enabled"
        with self.assertRaisesRegex(ConfigError, "keep scheduling disabled"):
            validate_policy(policy)
        policy = example()
        policy["schedule"]["task_settings"]["hidden"] = False
        with self.assertRaisesRegex(ConfigError, "hidden, non-overlapping"):
            validate_policy(policy)

    def test_retention_policy_cannot_drift(self):
        policy = example()
        policy["schedule"]["retention"]["daily"] = 6
        with self.assertRaisesRegex(ConfigError, "7/4/3"):
            validate_policy(policy)

    def test_capacity_shortfall_is_a_readiness_blocker(self):
        policy = example()
        policy["storage"]["repositories"][0]["capacity_gib"] = 500
        plan = make_plan(policy)
        self.assertTrue(any("capacity" in item for item in plan["readiness"]["blockers"]))

    def test_plan_is_deterministic_and_public_copy_redacts_storage(self):
        first = make_plan(example())
        second = make_plan(copy.deepcopy(example()))
        self.assertEqual(first, second)
        public = public_plan(first)
        rendered = json.dumps(public)
        self.assertNotIn("C:\\\\HomeLabBackup", rendered)
        self.assertNotIn("backup-appliance-one", rendered)
        self.assertNotIn("owner-private-notification-profile", rendered)
        self.assertIn("<primary-repository-path>", rendered)
        self.assertEqual(first["policy"]["storage"]["repositories"][0]["path"],
                         "X:\\HomeLabBackup\\repositories")


if __name__ == "__main__":
    unittest.main()
