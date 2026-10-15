"""Contracts for the Windows Beszel host adapter without changing a service."""

import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from homelab import beszel_windows as module
from homelab.config import ConfigError


def write_pe(path: Path, payload=b"candidate") -> None:
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, 0x8664)
    data.extend(payload)
    path.write_bytes(data)


class BeszelWindowsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="homelab beszel windows ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.candidate = self.root / "beszel-agent.exe"
        self.backups = self.root / "backups"
        self.backups.mkdir()
        write_pe(self.candidate)
        self.snapshot = {
            "service": "BeszelAgent",
            "wrapper": r"C:\Tools\nssm.exe",
            "application": r"C:\Program Files\BeszelAgent\beszel-agent.exe",
            "application_directory": r"C:\Program Files\BeszelAgent",
            "start_mode": "automatic",
            "account": "LocalSystem",
            "environment_names": ["KEY", "TOKEN"],
            "environment_hash": "a" * 64,
            "binary_sha256": "b" * 64,
            "binary_architecture": "amd64",
        }
        self.snapshot["fingerprint"] = module.digest(self.snapshot)
        self.plan = module.make_plan(self.candidate, self.backups, snapshot=self.snapshot)

    def test_plan_is_deterministic_and_contains_no_environment_values(self):
        again = module.make_plan(self.candidate, self.backups, snapshot=self.snapshot)
        self.assertEqual(self.plan, again)
        text = module.canonical(self.plan)
        self.assertNotIn("ssh-ed25519", text)
        self.assertEqual(self.plan["configuration_values"], "preserved-not-recorded")

    def test_public_snapshot_redacts_paths_and_environment_hash(self):
        report = module.public_snapshot(self.snapshot)
        self.assertEqual(report["paths"], "redacted")
        self.assertNotIn("environment_hash", report)
        self.assertNotIn("application", report)

    def test_candidate_tampering_is_refused(self):
        self.candidate.write_bytes(self.candidate.read_bytes() + b"changed")
        with self.assertRaisesRegex(ConfigError, "drift"):
            module.validate_plan(self.plan)

    def test_plan_tampering_is_refused(self):
        plan = copy.deepcopy(self.plan)
        plan["service"] = "Other"
        with self.assertRaisesRegex(ConfigError, "modified"):
            module.validate_plan(plan)

    def test_non_amd64_candidate_is_refused(self):
        other = self.root / "arm.exe"
        write_pe(other)
        data = bytearray(other.read_bytes())
        struct.pack_into("<H", data, 0x84, 0xAA64)
        other.write_bytes(data)
        with self.assertRaisesRegex(ConfigError, "amd64"):
            module.make_plan(other, self.backups, snapshot=self.snapshot)

    def test_environment_names_are_reported_but_values_are_only_hashed(self):
        names, fingerprint = module._environment(["KEY=public-key", "TOKEN=private-token", "LHM=true"])
        self.assertEqual(names, ["KEY", "LHM", "TOKEN"])
        self.assertNotIn("private-token", fingerprint)
        self.assertEqual(len(fingerprint), 64)

    def test_duplicate_environment_entry_is_refused(self):
        with self.assertRaisesRegex(ConfigError, "Duplicate"):
            module._environment(["KEY=one", "key=two"])

    def test_status_detects_configuration_drift(self):
        current = copy.deepcopy(self.snapshot)
        current["environment_hash"] = "c" * 64
        report = module.status(self.plan, current)
        self.assertEqual(report["service_configuration"], "drifted")
        self.assertEqual(report["changed_fields"], ["environment_hash"])

    def test_status_recognizes_installed_candidate(self):
        current = copy.deepcopy(self.snapshot)
        current["binary_sha256"] = self.plan["candidate"]["sha256"]
        report = module.status(self.plan, current)
        self.assertEqual(report["binary"], "candidate-installed")

    def test_apply_requires_confirmation_before_admin_or_service_access(self):
        with patch.object(module, "_admin") as admin, patch.object(module, "read_service") as service:
            with self.assertRaisesRegex(ConfigError, "Confirm"):
                module.apply(self.plan, "wrong")
        admin.assert_not_called()
        service.assert_not_called()

    def test_apply_requires_elevation(self):
        with patch.object(module, "_admin", return_value=False), patch.object(module, "read_service") as service:
            with self.assertRaisesRegex(ConfigError, "elevated"):
                module.apply(self.plan, self.plan["plan_id"])
        service.assert_not_called()

    def test_rollback_refuses_service_configuration_drift(self):
        backup = Path(self.plan["backup_directory"])
        backup.mkdir()
        original = backup / "beszel-agent.exe"
        write_pe(original, b"original")
        (backup / "manifest.json").write_text(json.dumps({
            "kind": "beszel-windows-backup-v1", "plan_id": self.plan["plan_id"],
            "service_fingerprint": self.snapshot["fingerprint"],
            "binary_sha256": module.file_sha256(original),
        }), encoding="utf-8")
        current = copy.deepcopy(self.snapshot)
        current["binary_sha256"] = self.plan["candidate"]["sha256"]
        current["environment_hash"] = "d" * 64
        with patch.object(module, "_admin", return_value=True), patch.object(module, "read_service", return_value=current), \
                self.assertRaisesRegex(ConfigError, "configuration drift"):
            module.rollback(self.plan, self.plan["plan_id"])


if __name__ == "__main__":
    unittest.main()
