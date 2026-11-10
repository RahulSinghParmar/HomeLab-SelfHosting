"""Jellyfin explicit deployment-selection contracts."""
import copy
import json
import unittest

from homelab import jellyfin as j
from homelab.config import ConfigError


def native_windows_audit():
    return {
        "kind": "homelab-jellyfin-audit", "contract": j.CONTRACT,
        "host_platform": "windows",
        "native": {"present": True, "running": True, "autostart": True,
                   "manager": "windows-service", "service": "JellyfinServer"},
        "container": {"present": False, "running": False,
                      "engine_available": True, "engine_os": "linux",
                      "matching_containers": 0},
        "public_api": {"reachable": True, "version": "12.4.0",
                       "startup_complete": True},
        "detected_deployment": "native", "mutations_performed": False,
        "production_media_read": False, "credentials_read": False,
    }


def empty_linux_audit():
    value = native_windows_audit()
    value["host_platform"] = "linux"
    value["native"] = {"present": False, "running": False, "autostart": False,
                       "manager": "systemd", "service": None}
    value["public_api"] = {"reachable": False, "version": None,
                           "startup_complete": None}
    value["detected_deployment"] = "none"
    return value


def recovery_evidence():
    fixture_hash = "a" * 64
    play = {
        "item_id": "fixture-item", "media_source_id": "fixture-source",
        "status": 200, "content_type": "video/mp4", "bytes": 11323,
        "sha256": fixture_hash, "exact": True,
    }
    return {
        "kind": "homelab-jellyfin-native-recovery-evidence",
        "contract": j.RECOVERY_CONTRACT,
        "created_utc": "2026-11-10T00:57:57+00:00",
        "jellyfin_version": "12.4.0",
        "deployment": "native-windows-isolated",
        "fixture": {"name": "phase6-jellyfin-direct-play.mp4",
                    "bytes": 11323, "sha256": fixture_hash},
        "source_direct_play": copy.deepcopy(play),
        "backup": {
            "server_version": "12.4.0.0", "backup_engine_version": "0.2.0",
            "date_created": "2026-11-10T00:57:33+00:00",
            "options": {"Database": True, "Metadata": True,
                        "Subtitles": True, "Trickplay": True},
            "bytes": 30274, "sha256": "b" * 64, "zip_entries": 46,
            "zip_integrity": True, "database_present": True,
            "database_format": "json-table-export",
        },
        "source_state_removed_before_restore": True,
        "restore_target_initialized_same_version": True,
        "restore_same_version": True,
        "restored_direct_play": copy.deepcopy(play),
        "restart_direct_play": copy.deepcopy(play),
        "restart_persistence_verified": True,
        "production_service_changed": False,
        "production_media_used": False,
        "production_credentials_used": False,
        "synthetic_credentials_retained": False,
        "gpu_used": False,
        "transcode_requested": False,
        "direct_play_exact": True,
        "trial_id": "e857fbdb-43b2-489b-b618-27cc071da0ac",
    }


class JellyfinTests(unittest.TestCase):
    def test_windows_native_selection_adopts_without_mutation(self):
        plan = j.make_plan("native", native_windows_audit())
        self.assertEqual(plan["selected_deployment"], "native")
        self.assertEqual(plan["adoption"], "existing")
        self.assertIsNone(plan["container_image"])
        self.assertEqual(plan["execution"], "disabled-review-only")
        self.assertFalse(plan["deployment_performed"])
        self.assertFalse(plan["production_media_used"])
        self.assertFalse(plan["acceleration"]["gpu_enabled"])

    def test_selection_is_explicit_and_platform_support_fails_closed(self):
        with self.assertRaisesRegex(ConfigError, "explicitly"):
            j.make_plan("auto", native_windows_audit())
        with self.assertRaisesRegex(ConfigError, "unsupported on windows"):
            j.make_plan("container", native_windows_audit())
        conflict = native_windows_audit()
        conflict["container"]["present"] = True
        conflict["container"]["running"] = True
        conflict["container"]["matching_containers"] = 1
        conflict["detected_deployment"] = "conflict"
        with self.assertRaisesRegex(ConfigError, "resolve ownership"):
            j.make_plan("native", conflict)

    def test_linux_container_plan_uses_reviewed_image_and_cpu(self):
        plan = j.make_plan("container", empty_linux_audit(), 18096)
        self.assertEqual(plan["selected_deployment"], "container")
        self.assertIn(":12.4@sha256:", plan["container_image"])
        self.assertEqual(plan["limits"], j.LIMITS)
        self.assertEqual(plan["access"], "loopback")
        self.assertEqual(plan["dlna"], "disabled-in-container-bridge")
        self.assertEqual(j.validate_plan(plan), plan)

    def test_container_compose_is_bounded_and_media_is_read_only(self):
        plan = j.make_plan("container", empty_linux_audit(), 18096)
        media = {"kind": "homelab-jellyfin-media-map", "contract": j.CONTRACT,
                 "mounts": [{"source": "/srv/media/video",
                              "target": "/media/video", "read_only": True}]}
        spec = j.compose(plan, "/srv/homelab/jellyfin", media, 1000, 1000)
        service = spec["services"]["jellyfin"]
        self.assertEqual(service["image"], j.image())
        self.assertEqual(service["pull_policy"], "never")
        self.assertEqual(service["ports"], [{"target": 8096, "published": "18096",
                                              "host_ip": "127.0.0.1",
                                              "protocol": "tcp"}])
        self.assertTrue(service["read_only"])
        self.assertEqual(service["cap_drop"], ["ALL"])
        self.assertEqual(service["mem_limit"], "2048m")
        media_mount = next(item for item in service["volumes"]
                           if item["target"] == "/media/video")
        self.assertTrue(media_mount["read_only"])
        rendered = json.dumps(spec).casefold()
        self.assertNotIn("docker.sock", rendered)
        self.assertNotIn("privileged", rendered)
        self.assertNotIn("device", rendered)

    def test_invalid_media_or_tampered_plan_is_rejected(self):
        plan = j.make_plan("container", empty_linux_audit())
        changed = copy.deepcopy(plan)
        changed["acceleration"]["gpu_enabled"] = True
        with self.assertRaises(ConfigError):
            j.validate_plan(changed)
        changed = copy.deepcopy(plan)
        changed["container_image"] = "example.invalid/jellyfin@sha256:" + "0" * 64
        changed["plan_id"] = j.digest(
            {key: value for key, value in changed.items() if key != "plan_id"})
        with self.assertRaisesRegex(ConfigError, "image or resource"):
            j.validate_plan(changed)
        for media in (
            {"kind": "homelab-jellyfin-media-map", "contract": j.CONTRACT,
             "mounts": []},
            {"kind": "homelab-jellyfin-media-map", "contract": j.CONTRACT,
             "mounts": [{"source": "/srv/media", "target": "/media/video",
                          "read_only": False}]},
        ):
            with self.subTest(media=media), self.assertRaises(ConfigError):
                j.compose(plan, "/srv/homelab/jellyfin", media, 1000, 1000)

    def test_audit_is_sanitized_read_only_and_detects_native(self):
        responses = {
            ("sc.exe", "query", "JellyfinServer"):
                (0, "STATE              : 4  RUNNING"),
            ("sc.exe", "qc", "JellyfinServer"):
                (0, "START_TYPE         : 2  AUTO_START"),
            ("docker", "version", "--format", "{{json .Server}}"):
                (0, '{"Os":"linux","Private":"discard"}'),
            ("docker", "ps", "-a", "--filter", "name=jellyfin", "--format",
             "{{json .}}"):
                (0, ""),
        }
        result = j.audit(lambda command: responses[tuple(command)],
                         lambda _url: {"reachable": True, "version": "12.4.0",
                                       "startup_complete": True},
                         system="Windows")
        self.assertEqual(result["detected_deployment"], "native")
        self.assertTrue(result["native"]["running"])
        self.assertTrue(result["native"]["autostart"])
        self.assertNotIn("Private", json.dumps(result))
        self.assertFalse(result["mutations_performed"])
        self.assertFalse(result["production_media_read"])
        self.assertFalse(result["credentials_read"])

    def test_native_recovery_evidence_requires_exact_restore_and_restart_playback(self):
        evidence = recovery_evidence()
        self.assertEqual(j.validate_recovery_evidence(evidence), evidence)

    def test_recovery_evidence_rejects_changed_playback_bytes(self):
        evidence = recovery_evidence()
        evidence["restored_direct_play"]["sha256"] = "c" * 64
        with self.assertRaisesRegex(ConfigError, "restored_direct_play"):
            j.validate_recovery_evidence(evidence)

    def test_recovery_evidence_rejects_production_or_acceleration_claims(self):
        for field in ("production_service_changed", "production_media_used",
                      "production_credentials_used", "gpu_used",
                      "transcode_requested"):
            with self.subTest(field=field):
                evidence = recovery_evidence()
                evidence[field] = True
                with self.assertRaisesRegex(ConfigError, "safety boundary"):
                    j.validate_recovery_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
