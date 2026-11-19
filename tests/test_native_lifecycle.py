"""Phase 7 native lifecycle, Glances, scheduled-task and reboot contracts."""
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from homelab import native_lifecycle as module
from homelab.config import ConfigError


NOW = "2026-11-19T00:00:00+00:00"
BOOT = "2026-11-18T00:00:00+00:00"


def host(policy):
    services = [{"name": row["name"], "exists": True, "state": "Running",
                 "start_mode": row["start_mode"]}
                for row in policy["services"]]
    startup = [{"name": row["name"], "entry_present": True,
                "process_running": True} for row in policy["startup"]]
    tasks = []
    for index, spec in enumerate(policy["tasks"]):
        tasks.append({
            "name": spec["name"], "exists": True, "enabled": True,
            "state": spec["state_mode"],
            "last_result": (module.TASK_RESULT_RUNNING
                            if spec["result_mode"] == "running" else 0),
            "result_class": spec["result_mode"],
            "last_run": "2026-11-18T00:05:00+00:00",
            "last_run_after_boot": True,
            "action_matches": True, "triggers": list(spec["triggers"]),
            "logon_type": "Interactive", "run_level": "Limited",
            "start_when_available": spec["start_when_available"],
            "restart_count": spec["restart_count_min"],
            "definition_fingerprint": f"{index + 1:064x}",
            "first_day_gate": True if spec["first_day_gate"] else None,
        })
    return {
        "boot_utc": BOOT, "uptime_seconds": 86400, "user_signed_in": True,
        "services": services, "startup": startup, "tasks": tasks,
        "listener": {"loopback_only": True, "listening": True},
        "glances_process": {"present": True,
                            "required_flags": {flag: True for flag in
                                               policy["glances"]["required_flags"]}},
        "docker": {"context": "desktop-linux", "server_version": "29.9.3",
                   "ready": True},
        "secrets_read": False, "changes_made": False,
    }


def glances(policy):
    return {
        "status": "checked", "status_http": 200, "ui_http": 200,
        "all_http": 200, "version": policy["glances"]["version"],
        "required_plugins": {name: True for name in
                             ("cpu", "mem", "load", "processcount",
                              "diskio", "network")},
        "ui_nonempty": True, "raw_values_persisted": False,
    }


def samples(policy):
    return [{"name": row["name"], "exists": True, "valid_json": True,
             "age_seconds": 5.0, "fresh": True, "source_statuses_ready": True}
            for row in policy["samples"]]


CONFIG = {"start_script_sha256": "a" * 64,
          "configuration_sha256": "b" * 64}


class NativeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.policy = module.load_policy()

    def build(self, observed_host=None, observed_glances=None,
              observed_samples=None, generated_at=NOW):
        return module.build_audit(
            self.policy, observed_host or host(self.policy),
            observed_glances or glances(self.policy),
            observed_samples or samples(self.policy),
            generated_at=generated_at, configuration=CONFIG)

    def test_policy_preserves_interactive_boundary_and_never_reboots(self):
        self.assertTrue(self.policy["recovery"]["requires_user_logon"])
        self.assertFalse(self.policy["recovery"]["unattended_boot_supported"])
        self.assertFalse(self.policy["recovery"]["automatic_reboot_allowed"])
        glances_task = next(row for row in self.policy["tasks"]
                            if row["name"] == "Parmar Home - Glances Monitor")
        self.assertEqual(glances_task["action_marker"],
                         "glance\\glances\\.venv\\Scripts\\python.exe")

    def test_healthy_current_boot_is_ready_and_secret_free(self):
        audit = self.build()
        self.assertTrue(audit["readiness"]["observed_reboot_recovery"])
        self.assertEqual(audit["blockers"], [])
        self.assertNotIn("C:\\", module.canonical(audit))
        self.assertNotIn("HOMESERVER", module.canonical(audit))
        module.validate_audit(audit)

    def test_first_day_monthly_tasks_keep_daily_trigger_and_wrapper_gate(self):
        monthly = [row for row in self.policy["tasks"]
                   if row["first_day_gate"] is not None]
        self.assertEqual(len(monthly), 2)
        self.assertTrue(all(row["triggers"] == ["daily"] for row in monthly))
        audit = self.build()
        by_name = {row["name"]: row for row in audit["tasks"]}
        self.assertTrue(all(by_name[row["name"]]["ready"] for row in monthly))

    def test_task_action_or_start_when_available_drift_blocks_readiness(self):
        observed = host(self.policy)
        observed["tasks"][0]["action_matches"] = False
        audit = self.build(observed_host=observed)
        self.assertFalse(audit["readiness"]["tasks"])
        self.assertIn("scheduled-tasks-not-ready", audit["blockers"])

    def test_non_loopback_or_missing_privacy_flag_blocks_glances(self):
        observed = host(self.policy)
        observed["listener"]["loopback_only"] = False
        first = self.policy["glances"]["required_flags"][0]
        observed["glances_process"]["required_flags"][first] = False
        audit = self.build(observed_host=observed)
        self.assertFalse(audit["readiness"]["glances"])

    def test_stale_or_error_sample_blocks_recovery(self):
        rows = samples(self.policy)
        rows[0]["fresh"] = False
        rows[0]["source_statuses_ready"] = False
        audit = self.build(observed_samples=rows)
        self.assertFalse(audit["readiness"]["samples"])
        self.assertFalse(audit["readiness"]["observed_reboot_recovery"])

    def test_reported_physical_health_is_an_accepted_collector_status(self):
        with tempfile.TemporaryDirectory() as temp:
            sample_root = Path(temp) / "glance" / "resource-data"
            sample_root.mkdir(parents=True)
            now = dt.datetime.now(dt.timezone.utc)
            for row in self.policy["samples"]:
                value = {"generated_at": now.isoformat()}
                status = "reported" if row["name"] == "storage.json" else "ok"
                value["collector"] = {"status": status}
                (sample_root / row["name"]).write_text(
                    json.dumps(value), encoding="utf-8")
            policy = copy.deepcopy(self.policy)
            policy["root"] = str(Path(temp))
            rows = module.collect_samples(policy, now=now)
            self.assertTrue(all(row["source_statuses_ready"] for row in rows))

    def test_missing_native_service_or_user_startup_blocks_recovery(self):
        observed = host(self.policy)
        observed["services"][0]["state"] = "Stopped"
        observed["startup"][0]["process_running"] = False
        audit = self.build(observed_host=observed)
        self.assertFalse(audit["readiness"]["services"])
        self.assertFalse(audit["readiness"]["startup"])

    def test_checkpoint_is_secret_free_and_hash_bound(self):
        checkpoint = module.checkpoint(self.build())
        module.validate_checkpoint(checkpoint)
        self.assertFalse(checkpoint["automatic_reboot_allowed"])
        changed = copy.deepcopy(checkpoint)
        changed["boot_utc"] = "2026-11-17T00:00:00+00:00"
        with self.assertRaisesRegex(ConfigError, "identifier"):
            module.validate_checkpoint(changed)

    def test_checkpoint_rejects_an_unready_current_boot(self):
        rows = samples(self.policy)
        rows[0]["fresh"] = False
        with self.assertRaisesRegex(ConfigError, "ready current-boot"):
            module.checkpoint(self.build(observed_samples=rows))

    def test_two_snapshot_reboot_passes_only_after_new_boot(self):
        before = module.checkpoint(self.build())
        after_host = host(self.policy)
        after_host["boot_utc"] = "2026-11-19T01:00:00+00:00"
        after = self.build(observed_host=after_host,
                           generated_at="2026-11-19T02:00:00+00:00")
        evidence = module.reboot_evidence(before, after)
        self.assertTrue(evidence["passed"])
        self.assertTrue(evidence["actual_reboot_observed"])
        module.validate_reboot_evidence(evidence)

    def test_same_boot_is_not_certified_as_controlled_reboot(self):
        audit = self.build()
        evidence = module.reboot_evidence(module.checkpoint(audit), audit)
        self.assertFalse(evidence["passed"])
        self.assertIn("windows-boot-identifier-did-not-change", evidence["blockers"])

    def test_task_definition_drift_after_reboot_is_detected(self):
        before_audit = self.build()
        before = module.checkpoint(before_audit)
        after_host = host(self.policy)
        after_host["boot_utc"] = "2026-11-19T01:00:00+00:00"
        after_host["tasks"][0]["definition_fingerprint"] = "f" * 64
        after = self.build(observed_host=after_host)
        evidence = module.reboot_evidence(before, after)
        self.assertIn("scheduled-task-definitions-changed", evidence["blockers"])

    def test_audit_and_reboot_evidence_tampering_is_rejected(self):
        audit = self.build()
        audit["readiness"]["tasks"] = False
        with self.assertRaisesRegex(ConfigError, "identifier"):
            module.validate_audit(audit)
        clean = self.build()
        evidence = module.reboot_evidence(module.checkpoint(clean), clean)
        evidence["passed"] = True
        with self.assertRaisesRegex(ConfigError, "identifier"):
            module.validate_reboot_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
