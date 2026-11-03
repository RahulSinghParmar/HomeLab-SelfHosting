"""Encrypted Immich Restic vault contracts."""
import json
import os
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch

from homelab import immich_vault as v
from homelab.config import ConfigError
from homelab.privatefs import atomic_json, read_private, windows_acl


TOOL = {"path": "<restic>", "version": "0.19.1", "sha256": "a" * 64,
        "archive_sha256": "b" * 64}


class ImmichVaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="homelab immich vault ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        first, second = self.base / "operational", self.base / "recovery"
        first.mkdir()
        second.mkdir()
        self.password = first / "password.txt"
        self.recovery = second / "password.txt"
        for path in (self.password, self.recovery):
            path.write_text("x" * 64 + "\n", encoding="ascii")
            if os.name == "nt":
                windows_acl(path, create=True)
            else:
                path.chmod(0o600)
        self.binary = self.base / ("restic.exe" if os.name == "nt" else "restic")
        self.binary.write_bytes(b"x")
        self.tool = {**TOOL, "path": str(self.binary)}
        self.patch_tool = patch.object(v, "validate_tool", return_value=self.tool)
        self.patch_tool.start()
        self.addCleanup(self.patch_tool.stop)
        self.plan = v.make_plan(self.base / "state", self.base / "repository",
                                self.password, self.recovery, self.binary)
        self.summary = {"original_files": 1, "original_bytes": 70,
                        "fixture_sha256": "f" * 64, "derived_included": False,
                        "ml_cache_included": False}
        self.manifest = {"kind": "immich-consistent-backup-v1",
                         "summary": self.summary}

    def portable_manifest(self, snapshot="d" * 64):
        value = {
            "kind": "homelab-immich-portable-recovery",
            "contract": v.RECOVERY_CONTRACT,
            "repository_id": "c" * 64,
            "snapshot_id": snapshot,
            "manifest_id": v.digest(self.manifest),
            "summary_id": v.digest(self.summary),
            "original_files": 1,
            "original_bytes": 70,
            "fixture_sha256": "f" * 64,
            "derived_included": False,
            "ml_cache_included": False,
            "restic_version": "0.19.1",
            "required_tags": sorted({*v.TAGS, v.VERIFIED_TAG,
                                     "manifest-" + v.digest(self.manifest)[:16]}),
            "full_data_check_utc": "2026-11-03T00:00:00+00:00",
        }
        value["recovery_manifest_id"] = v.digest(value)
        return value

    def initialize(self):
        with patch.object(v, "_restic", return_value=""), \
                patch.object(v, "_repository_id", return_value="c" * 64):
            return v.initialize(self.plan, self.plan["plan_id"])

    def test_plan_is_deterministic_and_contains_no_key_material(self):
        same = v.make_plan(self.base / "state", self.base / "repository",
                           self.password, self.recovery, self.binary)
        self.assertEqual(self.plan, same)
        self.assertEqual(self.plan["retention"], {"daily": 7, "weekly": 4, "monthly": 3})
        self.assertFalse(self.plan["off_host_verified"])
        self.assertNotIn("x" * 32, json.dumps(self.plan))

    def test_reviewed_linux_amd64_tool_is_checksum_pinned(self):
        candidate = self.base / "restic"
        candidate.write_bytes(b"x" * 1_000_000)
        candidate.chmod(0o700)
        reviewed = {"version": "0.19.1",
                    "linux_amd64": {"archive_sha256": "b" * 64,
                                    "executable_sha256": "a" * 64}}
        completed = CompletedProcess([str(candidate), "version"], 0,
                                     "restic 0.19.1 compiled with go on linux/amd64\n", "")
        with patch.object(v, "host_platform", return_value="linux"), \
                patch.object(v, "host_architecture", return_value="amd64"), \
                patch.object(v, "specification", return_value=reviewed), \
                patch.object(v, "file_sha256", return_value="a" * 64), \
                patch.object(v.os, "access", return_value=True), \
                patch.object(v.subprocess, "run", return_value=completed):
            result = v.validate_tool(candidate)
        self.assertEqual(result["sha256"], "a" * 64)

    def test_key_generation_is_gated_and_never_returns_secret(self):
        first, second = self.base / "generated-operational", self.base / "generated-recovery"
        first.mkdir()
        second.mkdir()
        operational, recovery = first / "key.txt", second / "key.txt"
        with self.assertRaises(ConfigError):
            v.create_keys(operational, recovery, "wrong")
        result = v.create_keys(operational, recovery, "CREATE-IMMICH-RECOVERY-KEY")
        self.assertFalse(result["secret_displayed"])
        self.assertEqual(operational.read_bytes(), recovery.read_bytes())
        self.assertNotIn(operational.read_text(encoding="ascii").strip(), json.dumps(result))

    def test_key_files_must_match_and_be_separated(self):
        same_directory = self.password.parent / "copy.txt"
        same_directory.write_text("x" * 64 + "\n", encoding="ascii")
        if os.name == "nt":
            windows_acl(same_directory, create=True)
        else:
            same_directory.chmod(0o600)
        with self.assertRaises(ConfigError):
            v.validate_key_custody(self.password, same_directory)
        self.recovery.write_text("y" * 64 + "\n", encoding="ascii")
        if os.name == "nt":
            windows_acl(self.recovery, create=True)
        with self.assertRaises(ConfigError):
            v.validate_key_custody(self.password, self.recovery)

    def test_snapshot_store_binds_verified_manifest(self):
        self.initialize()
        source = self.base / "application-backup"
        source.mkdir()
        with patch.object(v, "_repository_id", return_value="c" * 64), \
                patch.object(v, "verify_backup", return_value=self.manifest), \
                patch.object(v, "backup_summary", return_value=self.summary):
            snapshot = v.make_snapshot_plan(self.plan, source)
            output = json.dumps({"message_type": "summary", "snapshot_id": "d" * 64})
            with patch.object(v, "_restic", return_value=output):
                result = v.store(self.plan, snapshot, snapshot["snapshot_plan_id"])
        self.assertEqual(result["snapshot_id"], "d" * 64)
        self.assertEqual(read_private(Path(self.plan["state_root"]) / "state.json")
                         ["last_snapshot"], "d" * 64)

    def test_restore_verifies_manifest_and_protects_snapshot(self):
        self.initialize()
        source = self.base / "application-backup"
        source.mkdir()
        with patch.object(v, "_repository_id", return_value="c" * 64), \
                patch.object(v, "verify_backup", return_value=self.manifest), \
                patch.object(v, "backup_summary", return_value=self.summary):
            snapshot = v.make_snapshot_plan(self.plan, source)
        state_path = Path(self.plan["state_root"]) / "state.json"
        state = read_private(state_path)
        state.update({"last_snapshot": "d" * 64,
                      "last_checked_snapshot": "d" * 64,
                      "last_check_utc": "2026-11-03T00:00:00+00:00"})
        atomic_json(state_path, state, replace=True)
        target = self.base / "restored"
        calls = []

        def command(_plan, arguments, **_kwargs):
            calls.append(arguments)
            if arguments[:4] == ["tag", "--json", "--add", v.VERIFIED_TAG]:
                return "\n".join((
                    json.dumps({"message_type": "changed", "old_snapshot_id": "d" * 64,
                                "new_snapshot_id": "e" * 64}),
                    json.dumps({"message_type": "summary", "changed_snapshots": 1}),
                ))
            return ""

        with patch.object(v, "_repository_id", return_value="c" * 64), \
                patch.object(v, "_restic", side_effect=command), \
                patch.object(v, "_snapshots", return_value=[{"id": "d" * 64}]), \
                patch.object(v, "_locate_backup", return_value=target), \
                patch.object(v, "verify_backup", return_value=self.manifest), \
                patch.object(v, "backup_summary", return_value=self.summary):
            result = v.restore(self.plan, snapshot, "d" * 64, target,
                               snapshot["snapshot_plan_id"])
        self.assertTrue(result["recovery_verified"])
        self.assertEqual(result["snapshot_id"], "e" * 64)
        self.assertTrue(any(args[:4] == ["tag", "--json", "--add", v.VERIFIED_TAG]
                            for args in calls))

    def test_retention_requires_checked_restore_verified_snapshot(self):
        self.initialize()
        with patch.object(v, "_repository_id", return_value="c" * 64), \
                self.assertRaises(ConfigError):
            v.retention(self.plan)
        state_path = Path(self.plan["state_root"]) / "state.json"
        state = read_private(state_path)
        state.update({"last_snapshot": "d" * 64, "last_verified": "d" * 64,
                      "last_checked_snapshot": "d" * 64})
        atomic_json(state_path, state, replace=True)
        with patch.object(v, "_repository_id", return_value="c" * 64), \
                patch.object(v, "_snapshots", return_value=[{
                    "id": "d" * 64, "tags": [v.VERIFIED_TAG]}]), \
                patch.object(v, "_restic", return_value="") as restic:
            result = v.retention(self.plan)
        self.assertEqual(result["mode"], "preview")
        self.assertIn("--dry-run", restic.call_args.args[1])
        self.assertNotIn("--prune", restic.call_args.args[1])

    def test_portable_manifest_binds_exclusions_and_exact_original(self):
        self.initialize()
        source = self.base / "application-backup"
        source.mkdir()
        with patch.object(v, "_repository_id", return_value="c" * 64), \
                patch.object(v, "verify_backup", return_value=self.manifest), \
                patch.object(v, "backup_summary", return_value=self.summary):
            snapshot_plan = v.make_snapshot_plan(self.plan, source)
        state_path = Path(self.plan["state_root"]) / "state.json"
        state = read_private(state_path)
        state.update({"last_snapshot": "d" * 64, "last_verified": "d" * 64,
                      "last_checked_snapshot": "d" * 64,
                      "last_check_utc": "2026-11-03T00:00:00+00:00"})
        atomic_json(state_path, state, replace=True)
        tags = [*v.TAGS, v.VERIFIED_TAG,
                "manifest-" + snapshot_plan["manifest_id"][:16]]
        with patch.object(v, "_repository_id", return_value="c" * 64), \
                patch.object(v, "_snapshots", return_value=[{"id": "d" * 64,
                                                              "tags": tags}]):
            result = v.make_recovery_manifest(self.plan, snapshot_plan, "d" * 64)
        self.assertEqual(result["fixture_sha256"], "f" * 64)
        self.assertFalse(result["derived_included"])
        self.assertFalse(result["ml_cache_included"])
        self.assertEqual(v.validate_recovery_manifest(result), result)

    def test_off_host_recovery_checks_all_data_and_exact_backup(self):
        evidence = self.portable_manifest()
        Path(self.plan["repository"]).mkdir()
        with patch.object(v, "_repository_id", return_value="c" * 64):
            plan = v.make_recovery_plan(self.plan["repository"], self.recovery,
                                        self.binary, evidence)
        target = self.base / "off-host-restore"
        calls = []

        def command(_plan, arguments, **_kwargs):
            calls.append(arguments)
            return ""

        snapshot = {"id": "d" * 64, "tags": evidence["required_tags"]}
        with patch.object(v, "_repository_id", return_value="c" * 64), \
                patch.object(v, "_restic", side_effect=command), \
                patch.object(v, "_snapshots", return_value=[snapshot]), \
                patch.object(v, "_locate_backup", return_value=target), \
                patch.object(v, "verify_backup", return_value=self.manifest), \
                patch.object(v, "backup_summary", return_value=self.summary):
            result = v.recover_off_host(plan, target, plan["plan_id"])
        self.assertTrue(result["full_data_check"])
        self.assertFalse(result["source_machine_state_used"])
        self.assertEqual(result["fixture_sha256"], "f" * 64)
        self.assertIn(["check", "--read-data"], calls)

    def test_tampered_portable_manifest_is_refused_before_repository_use(self):
        evidence = self.portable_manifest()
        evidence["original_bytes"] = 71
        Path(self.plan["repository"]).mkdir()
        with patch.object(v, "_repository_id") as repository, \
                self.assertRaises(ConfigError):
            v.make_recovery_plan(self.plan["repository"], self.recovery,
                                 self.binary, evidence)
        repository.assert_not_called()


if __name__ == "__main__":
    unittest.main()
