import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from homelab import coolify_adapter as adapter
from homelab import coolify_controller as controller
from homelab.config import ConfigError
from homelab.sandbox import digest


def base_audit():
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
            "health": "healthy" if name != "coolify-testing-host" else "running",
            "image": {
                "coolify": "docker.io/coollabsio/coolify:4.5.3",
                "coolify-realtime": "docker.io/coollabsio/coolify-realtime:1.0.19",
                "coolify-sentinel": "docker.io/coollabsio/sentinel:1.1.5",
                "coolify-proxy": "traefik:v3.7",
            }.get(name, "example.invalid/component:1.0.0"),
            "image_id": "sha256:" + "a" * 64,
            "privileged": False,
            "docker_socket": name in adapter.DOCKER_CONTROL,
            "compose_project": "coolify",
            "published_bindings": [],
        } for name in adapter.COMPONENTS],
        "checks": {"root_compose_valid": True, "proxy_compose_valid": True,
                   "dashboard_health": True},
        "backup": {"exists": True, "age_hours": 2.0, "fresh": True,
                   "database_dump": True, "manifest": True,
                   "encrypted_at_rest": False, "off_host_verified": False},
        "safety": {"secrets_read": False, "changes_made": False,
                   "generated_resources_adopted": False},
    }
    value["audit_id"] = digest(value)
    return value


def versions():
    return {
        "status": "checked",
        "source": "https://cdn.coollabs.io/coolify/versions.json",
        "sha256": "b" * 64,
        "channel": "stable",
        "coolify": "4.7.5",
        "helper": "1.0.19",
        "sentinel": "1.1.5",
        "traefik": {"v3.7": "3.7.16"},
    }


def host():
    return {
        "host_os": "windows",
        "docker_context": "desktop-linux",
        "docker_server_version": "29.9.3",
        "docker_server_os": "linux",
        "docker_server_arch": "amd64",
        "compose_version": "5.7.0",
        "wsl_distribution": "docker-desktop",
        "wsl_host_mount_accessible": True,
        "root_exists": True,
    }


def tasks():
    return [{"name": name, "exists": True, "state": "Ready",
             "last_result": 0, "action_matches": True}
            for name in controller.TASKS]


def migration():
    return {"sha256": "c" * 64, "legacy_soketi_override": True,
            "reverb_ports_on_coolify": False,
            "crosses_reverb_boundary": True, "review_required": True}


def updater():
    return {"status": "checked", "local_exists": True, "local_markers": True,
            "remote_sha256": "d" * 64, "mount_anchor_count": 1,
            "completion_anchor_count": 1, "compatible": True}


def api(active=None):
    return {"configured": active is not None,
            "status": "checked" if active is not None else "not-configured",
            "http_status": 200 if active is not None else None,
            "active_deployments": active, "secret_persisted": False}


def limits(compliant=True):
    actual = dict(controller.EXPECTED_SENTINEL_LIMITS)
    if not compliant:
        actual["memory_bytes"] = 0
    return {"status": "checked", "expected": controller.EXPECTED_SENTINEL_LIMITS,
            "actual": actual, "compliant": compliant}


class CoolifyControllerTests(unittest.TestCase):
    def setUp(self):
        self.policy = controller.load_policy()

    def build(self, *, active=None, compliant=True):
        with mock.patch.object(controller, "_local_image_version",
                               return_value="3.7.12"):
            return controller.build_audit(
                self.policy, base_audit(), versions(), host(), tasks(), migration(),
                updater(), api(active), limits(compliant),
                generated_at="2026-11-18T00:00:00+00:00")

    def test_policy_keeps_update_ownership_with_coolify(self):
        self.assertEqual(self.policy["updates"]["owner"], "coolify-dashboard")
        self.assertFalse(self.policy["updates"]["generic_updater_allowed"])
        self.assertFalse(self.policy["updates"]["automatic"])

    def test_versions_feed_is_bounded_and_semantic(self):
        payload = {"stable": {"coolify": {"version": "4.7.5"},
                              "helper": {"version": "1.0.19"},
                              "sentinel": {"version": "1.1.5"},
                              "traefik": {"v3.7": "3.7.16"}}}
        self.assertEqual(controller.normalize_versions(payload)["coolify"], "4.7.5")
        payload["stable"]["coolify"]["version"] = "latest"
        with self.assertRaises(ConfigError):
            controller.normalize_versions(payload)

    def test_plan_detects_update_and_fails_closed_on_recovery_and_migration(self):
        observed = self.build()
        controller.validate_audit(observed)
        plan = controller.make_plan(self.policy, observed)
        self.assertTrue(plan["update_available"])
        self.assertEqual(plan["installed_version"], "4.5.3")
        self.assertEqual(plan["target_version"], "4.7.5")
        self.assertFalse(plan["update_ready"])
        self.assertIn("read-only-controller-api-token-is-not-configured",
                      plan["blockers"])
        self.assertIn("soketi-to-reverb-migration-requires-windows-rehearsal",
                      plan["blockers"])
        self.assertIn("encrypted-off-host-control-plane-restore-not-yet-proven",
                      plan["blockers"])
        controller.validate_plan(plan)

    def test_active_deployment_is_a_controller_blocker(self):
        plan = controller.make_plan(self.policy, self.build(active=1))
        self.assertIn("active-deployments-must-finish-before-update", plan["blockers"])
        self.assertFalse(plan["controller_api_ready"])
        clear = controller.make_plan(self.policy, self.build(active=0))
        self.assertNotIn("active-deployments-must-finish-before-update",
                         clear["blockers"])
        self.assertTrue(clear["controller_api_ready"])

    def test_sentinel_resource_drift_is_reported(self):
        plan = controller.make_plan(self.policy, self.build(active=0, compliant=False))
        self.assertIn("sentinel-resource-limits-drifted", plan["blockers"])
        self.assertFalse(plan["sentinel_limits_ready"])

    def test_controller_audit_and_plan_ids_detect_tampering(self):
        observed = self.build()
        changed = copy.deepcopy(observed)
        changed["host"]["docker_context"] = "default"
        with self.assertRaises(ConfigError):
            controller.validate_audit(changed)
        plan = controller.make_plan(self.policy, observed)
        plan["generic_update_manager_allowed"] = True
        with self.assertRaises(ConfigError):
            controller.validate_plan(plan)

    def test_custom_compose_detects_reverb_boundary_without_exposing_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            compose = source / "docker-compose.custom.yml"
            compose.write_text(
                "services:\n  coolify:\n    ports:\n      - '8000:8080'\n"
                "  soketi:\n    ports:\n      - '6001:6001'\n      - '6002:6002'\n",
                encoding="utf-8")
            policy = copy.deepcopy(self.policy)
            policy["root"] = str(root)
            result = controller.inspect_custom_compose(
                policy, "4.5.3", "4.7.5")
            self.assertTrue(result["legacy_soketi_override"])
            self.assertTrue(result["crosses_reverb_boundary"])
            self.assertTrue(result["review_required"])
            self.assertNotIn("content", json.dumps(result).lower())

    def test_api_without_token_is_secret_free_and_non_authoritative(self):
        result = controller.inspect_api(self.policy)
        self.assertFalse(result["configured"])
        self.assertIsNone(result["active_deployments"])
        self.assertFalse(result["secret_persisted"])


if __name__ == "__main__":
    unittest.main()
