import copy
import json
import tempfile
import unittest
from pathlib import Path

from homelab import coolify_adapter as adapter
from homelab.config import ConfigError
from homelab.sandbox import digest


def sample_audit():
    value = {
        "kind": "homelab-coolify-audit",
        "contract": adapter.CONTRACT,
        "platform": "windows-docker-desktop-existing-instance",
        "support": "experimental-existing-instance-only",
        "components": [{
            "name": name,
            "owner": adapter.OWNERS[name],
            "exists": True,
            "state": "running",
            "health": "healthy",
            "image": "example.invalid/image:1",
            "image_id": "sha256:" + "a" * 64,
            "privileged": False,
            "docker_socket": name in adapter.DOCKER_CONTROL,
            "compose_project": "coolify" if name not in
                ("coolify-proxy", "coolify-sentinel") else None,
            "published_bindings": [],
        } for name in adapter.COMPONENTS],
        "checks": {"root_compose_valid": True,
                   "proxy_compose_valid": True,
                   "dashboard_health": True},
        "backup": {"exists": True, "age_hours": 2.0, "fresh": True,
                   "database_dump": True, "manifest": True,
                   "encrypted_at_rest": False, "off_host_verified": False},
        "safety": {"secrets_read": False, "changes_made": False,
                   "generated_resources_adopted": False},
    }
    value["audit_id"] = digest(value)
    return value


class CoolifyAdapterTests(unittest.TestCase):
    def setUp(self):
        self.policy = adapter.load_policy()

    def test_example_policy_is_strict_and_owner_accurate(self):
        self.assertEqual(self.policy["components"]["coolify-proxy"]["owner"],
                         "coolify-generated-proxy-compose")
        self.assertFalse(self.policy["backup"]["managed_application_data_included"])

    def test_plan_is_non_owning_and_update_blocked(self):
        plan = adapter.make_plan(self.policy, sample_audit())
        self.assertTrue(plan["health_ready"])
        self.assertTrue(plan["local_control_plane_backup_ready"])
        self.assertFalse(plan["update_ready"])
        self.assertFalse(plan["production_state_adopted"])
        adapter.validate_plan(plan)

    def test_docker_control_drift_is_rejected(self):
        value = sample_audit()
        value["components"][0]["docker_socket"] = True
        copy_without_id = dict(value)
        copy_without_id.pop("audit_id")
        value["audit_id"] = digest(copy_without_id)
        with self.assertRaises(ConfigError):
            adapter.validate_audit(value)

    def test_privileged_component_is_rejected(self):
        value = sample_audit()
        value["components"][-1]["privileged"] = True
        copy_without_id = dict(value)
        copy_without_id.pop("audit_id")
        value["audit_id"] = digest(copy_without_id)
        with self.assertRaises(ConfigError):
            adapter.validate_audit(value)

    def test_audit_and_plan_ids_detect_tampering(self):
        value = sample_audit()
        value["checks"]["dashboard_health"] = False
        with self.assertRaises(ConfigError):
            adapter.validate_audit(value)
        plan = adapter.make_plan(self.policy, sample_audit())
        plan["health_ready"] = False
        with self.assertRaises(ConfigError):
            adapter.validate_plan(plan)

    def test_backup_inventory_never_claims_encryption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            backup = root / "backups-host" / "20261116-031502"
            backup.mkdir(parents=True)
            (backup / "coolify-postgres.dump").write_bytes(b"dump")
            (backup / "manifest.json").write_text("{}", encoding="utf-8")
            result = adapter._backup(root, 36)
            self.assertTrue(result["exists"])
            self.assertTrue(result["database_dump"])
            self.assertFalse(result["encrypted_at_rest"])
            self.assertFalse(result["off_host_verified"])

    def test_policy_rejects_automatic_updates(self):
        value = copy.deepcopy(self.policy)
        value["updates"]["automatic"] = True
        with self.assertRaises(ConfigError):
            adapter.validate_policy(value)

    def test_public_example_has_no_secret_fields(self):
        text = json.dumps(self.policy).casefold()
        for marker in ("app_key", "password", "token", "private_key"):
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
