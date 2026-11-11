"""Encrypted Jellyfin recovery-set contract tests."""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from homelab import jellyfin_vault as v
from homelab.config import ConfigError
from homelab.sandbox import digest


class JellyfinVaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="homelab jellyfin vault ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.archive = self.root / "backup.zip"
        entries = {
            "manifest.json": b"{}",
            "config/system.xml": b"<ServerConfiguration />",
            "database/users.json": b"[]",
            "database/baseitems.json": b"[]",
            "database/userdata.json": b"[]",
        }
        with zipfile.ZipFile(self.archive, "w", zipfile.ZIP_DEFLATED) as output:
            for name, content in entries.items():
                output.writestr(name, content)
        self.media = self.root / "fixture.mp4"
        self.media.write_bytes(b"synthetic-mp4" * 200)
        self.backup = {
            "server_version": "12.4.0.0",
            "backup_engine_version": "0.2.0",
            "options": {"Database": True, "Metadata": True,
                        "Subtitles": True, "Trickplay": True},
            "zip_entries": len(entries),
        }
        self.destination = self.root / "set"
        self.manifest = v.write_recovery_set(
            self.archive, self.media, self.destination, self.backup,
            "2026-11-11T00:00:00+00:00")

    def portable(self):
        return v.make_portable_manifest(
            "a" * 64, "b" * 64, self.manifest,
            "2026-11-11T00:01:00+00:00")

    def proof(self):
        portable = self.portable()
        value = {
            "kind": "homelab-jellyfin-off-host-recovery-proof",
            "contract": v.PROOF_CONTRACT,
            "repository_id": portable["repository_id"],
            "snapshot_id": portable["snapshot_id"],
            "recovery_manifest_id": portable["recovery_manifest_id"],
            "recovery_set_id": portable["recovery_set_id"],
            "summary_id": portable["summary_id"],
            "restic_version": "0.19.1",
            "full_repository_data_check": True,
            "encrypted_repository": True,
            "transport_contains_recovery_key": False,
            "source_machine_state_used": False,
            "clean_target": True,
            "application_restore_verified": True,
            "media_replica_restored": True,
            "source_direct_play_exact": True,
            "restored_direct_play_exact": True,
            "restart_direct_play_exact": True,
            "restart_persistence_verified": True,
            "production_data_used": False,
            "production_service_changed": False,
            "gpu_used": False,
            "transcode_requested": False,
            "trial_id": "a225a57e-8193-42b8-a288-2b98d466f751",
        }
        value["proof_id"] = digest(value)
        return value

    def test_recovery_set_binds_application_and_owner_media(self):
        value = v.validate_recovery_set(self.destination)
        self.assertEqual(value, self.manifest)
        self.assertTrue(value["media"]["owner_managed"])
        self.assertFalse(value["media"]["included_in_application_archive"])

    def test_recovery_set_rejects_tampered_media_and_extra_files(self):
        (self.destination / v.MEDIA_PATH).write_bytes(b"changed")
        with self.assertRaises(ConfigError):
            v.validate_recovery_set(self.destination)
        (self.destination / v.MEDIA_PATH).write_bytes(self.media.read_bytes())
        (self.destination / "unexpected.txt").write_text("x", encoding="ascii")
        with self.assertRaises(ConfigError):
            v.validate_recovery_set(self.destination)

    def test_portable_manifest_binds_repository_snapshot_and_summary(self):
        portable = self.portable()
        self.assertEqual(v.validate_portable_manifest(portable), portable)
        self.assertFalse(portable["transport_contains_recovery_key"])
        changed = json.loads(json.dumps(portable))
        changed["summary"]["media_bytes"] += 1
        with self.assertRaises(ConfigError):
            v.validate_portable_manifest(changed)

    def test_offhost_proof_requires_exact_recovery_and_safe_boundaries(self):
        proof = self.proof()
        self.assertEqual(v.validate_offhost_proof(proof), proof)
        for field in ("restored_direct_play_exact", "media_replica_restored"):
            changed = dict(proof)
            changed[field] = False
            changed["proof_id"] = digest({k: item for k, item in changed.items()
                                          if k != "proof_id"})
            with self.assertRaises(ConfigError):
                v.validate_offhost_proof(changed)
        changed = dict(proof)
        changed["production_service_changed"] = True
        changed["proof_id"] = digest({k: item for k, item in changed.items()
                                      if k != "proof_id"})
        with self.assertRaises(ConfigError):
            v.validate_offhost_proof(changed)

    def test_reviewed_restic_release_is_exactly_pinned(self):
        spec = v.specification()
        self.assertEqual(spec["version"], "0.19.1")
        self.assertEqual(spec["windows_amd64"]["executable_sha256"],
                         "b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830")
        self.assertEqual(spec["linux_amd64"]["executable_sha256"],
                         "20d4142678d0d95ec11a4759def1b73fd9190abc9ca19e4b62d067c0b387e639")


if __name__ == "__main__":
    unittest.main()
