"""Phase 6 opt-in media-management planning and recovery tests."""
from __future__ import annotations

import copy
import json
import unittest

from homelab.config import ConfigError
from homelab import media_management as media


def selection(*selected: str) -> dict:
    value = copy.deepcopy(media.load_selection(require_selected=False))
    value["selected"] = list(selected)
    return value


def complete_selection() -> dict:
    return selection(*media.COMPONENTS)


def evidence(plan: dict) -> dict:
    memory = {name: min(100, plan["limits"][name]["memory_mib"])
              for name in plan["selected"]}
    return {
        "kind": "homelab-media-management-recovery-evidence",
        "contract": media.CONTRACT,
        "plan_id": plan["plan_id"],
        "selected": plan["selected"],
        "backup": {
            "services_stopped": True,
            "config_components": sorted(set(plan["selected"]) & set(media.CONFIG_TARGETS)),
            "manifest_sha256": "a" * 64,
        },
        "sqlite": {"checked": 7, "all_ok": True},
        "shared_storage": {
            "applicable": bool(plan["shared_data"]),
            "hardlink": True,
            "atomic_move": True,
            "content_restored": True,
        },
        "restore": {
            "independent_root": True,
            "started": plan["selected"],
            "healthy": plan["selected"],
            "sentinel_match": True,
        },
        "resources": {
            "memory_mib": memory,
            "peak_cpu_percent": {name: 1.0 for name in plan["selected"]},
            "total_memory_mib": sum(memory.values()),
        },
        "safety": {
            "production_paths_used": False,
            "production_credentials_used": False,
            "external_requests_enabled": False,
            "automatic_actions_enabled": False,
            "cleanup_completed": True,
        },
    }


class MediaManagementPlanningTests(unittest.TestCase):
    def test_image_manifest_covers_all_components_with_digests(self):
        manifest = media.load_images()
        self.assertEqual(set(manifest["components"]), set(media.COMPONENTS))
        for item in manifest["components"].values():
            self.assertIn("@sha256:", item["image"])
            self.assertNotIn(":latest", item["image"])

    def test_example_is_deliberately_unselected(self):
        template = media.load_selection(require_selected=False)
        self.assertEqual(template["selected"], [])
        with self.assertRaisesRegex(ConfigError, "Select at least one"):
            media.make_plan(template)

    def test_components_are_never_implicitly_added(self):
        plan = media.make_plan(selection("sonarr"))
        self.assertEqual(plan["selected"], ["sonarr"])
        self.assertEqual(set(media.compose(plan)["services"]), {"sonarr"})

    def test_dependencies_require_explicit_selection(self):
        for selected in (("bazarr",), ("prowlarr",), ("flaresolverr",)):
            with self.subTest(selected=selected), self.assertRaises(ConfigError):
                media.make_plan(selection(*selected))
        media.make_plan(selection("sonarr", "bazarr"))
        media.make_plan(selection("sonarr", "prowlarr", "flaresolverr"))

    def test_duplicate_unknown_and_automatic_actions_are_refused(self):
        for selected in (("sonarr", "sonarr"), ("unknown",)):
            with self.subTest(selected=selected), self.assertRaises(ConfigError):
                media.make_plan(selection(*selected))
        value = selection("sonarr")
        value["automatic_actions"]["downloads"] = True
        with self.assertRaisesRegex(ConfigError, "automation must remain disabled"):
            media.make_plan(value)

    def test_plan_is_deterministic_and_does_not_adopt_production(self):
        first = media.make_plan(complete_selection())
        second = media.make_plan(complete_selection())
        self.assertEqual(first, second)
        self.assertFalse(first["production_state_adopted"])
        self.assertEqual(first["credentials"], "operator-supplied-after-deployment")
        self.assertEqual(first["access"]["ui"], "loopback-only")

    def test_image_or_plan_tamper_is_refused(self):
        plan = media.make_plan(selection("sonarr"))
        changed = copy.deepcopy(plan)
        changed["images"]["sonarr"]["image"] = (
            "example.invalid/sonarr@sha256:" + "f" * 64)
        with self.assertRaisesRegex(ConfigError, "changed"):
            media.validate_plan(changed)
        changed = copy.deepcopy(plan)
        changed["plan_id"] = "0" * 64
        with self.assertRaisesRegex(ConfigError, "changed"):
            media.validate_plan(changed)

    def test_paths_overlap_and_ports_collide_fail_closed(self):
        value = selection("sonarr")
        value["data_root"] = value["config_root"] + "\\data"
        with self.assertRaisesRegex(ConfigError, "must not overlap"):
            media.make_plan(value)
        value = selection("sonarr")
        value["ports"]["radarr"] = value["ports"]["sonarr"]
        with self.assertRaisesRegex(ConfigError, "unique"):
            media.make_plan(value)


class MediaManagementComposeTests(unittest.TestCase):
    def setUp(self):
        self.plan = media.make_plan(complete_selection())
        self.spec = media.compose(self.plan)

    def test_all_selected_components_are_rendered_with_limits_and_pinned_images(self):
        self.assertEqual(set(self.spec["services"]), set(media.COMPONENTS))
        for name, service in self.spec["services"].items():
            self.assertIn("@sha256:", service["image"])
            self.assertEqual(service["pull_policy"], "never")
            self.assertGreater(service["pids_limit"], 0)
            self.assertTrue(service["mem_limit"].endswith("m"))
            self.assertGreater(service["cpus"], 0)
            self.assertEqual(service["security_opt"], ["no-new-privileges:true"])
            self.assertIn("healthcheck", service)
            self.assertEqual(service["logging"]["options"]["max-size"], "10m")

    def test_ui_ports_are_loopback_and_torrent_peer_port_is_not_published(self):
        published = []
        for service in self.spec["services"].values():
            for port in service.get("ports", []):
                self.assertEqual(port["host_ip"], "127.0.0.1")
                published.append(port["target"])
        self.assertNotIn(6881, published)
        self.assertNotIn("ports", self.spec["services"]["flaresolverr"])

    def test_shared_data_mapping_is_identical_and_flaresolverr_tmpfs_is_bounded(self):
        sources = set()
        for name in media.DATA_COMPONENTS:
            mounts = self.spec["services"][name]["volumes"]
            data = [item for item in mounts if item["target"] == "/data"]
            self.assertEqual(len(data), 1)
            sources.add(data[0]["source"])
        self.assertEqual(sources, {self.plan["roots"]["data"]})
        flare = self.spec["services"]["flaresolverr"]
        self.assertEqual(flare["tmpfs"], ["/tmp:rw,noexec,nosuid,size=512m"])

    def test_no_socket_device_secret_or_automatic_action_is_rendered(self):
        text = json.dumps(self.spec).lower()
        self.assertNotIn("docker.sock", text)
        self.assertNotIn("api_key", text)
        self.assertNotIn("apikey", text)
        self.assertNotIn("password", text)
        self.assertNotIn("devices", text)
        self.assertNotIn("6881:6881", text)

    def test_trial_network_can_be_made_internal_without_changing_services(self):
        trial = media.compose(self.plan, trial_internal_network=True)
        self.assertTrue(trial["networks"]["media-management"]["internal"])
        self.assertEqual(trial["services"], self.spec["services"])


class MediaManagementRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.plan = media.make_plan(complete_selection())
        self.value = evidence(self.plan)

    def test_complete_synthetic_evidence_passes(self):
        self.assertEqual(media.validate_recovery_evidence(self.value, self.plan), self.value)

    def test_running_backup_bad_sqlite_missing_health_and_production_access_fail(self):
        changes = [
            lambda value: value["backup"].__setitem__("services_stopped", False),
            lambda value: value["sqlite"].__setitem__("all_ok", False),
            lambda value: value["restore"].__setitem__("healthy", ["sonarr"]),
            lambda value: value["safety"].__setitem__("production_paths_used", True),
            lambda value: value["safety"].__setitem__("external_requests_enabled", True),
            lambda value: value["shared_storage"].__setitem__("hardlink", False),
        ]
        for change in changes:
            value = copy.deepcopy(self.value)
            change(value)
            with self.subTest(change=change), self.assertRaises(ConfigError):
                media.validate_recovery_evidence(value, self.plan)

    def test_measured_memory_must_fit_each_component_limit(self):
        value = copy.deepcopy(self.value)
        value["resources"]["memory_mib"]["sonarr"] = 9999
        value["resources"]["total_memory_mib"] = sum(value["resources"]["memory_mib"].values())
        with self.assertRaisesRegex(ConfigError, "memory exceeds"):
            media.validate_recovery_evidence(value, self.plan)


if __name__ == "__main__":
    unittest.main()
