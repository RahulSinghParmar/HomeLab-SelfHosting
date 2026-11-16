"""Phase 7 Matrix identity, Compose and recovery-contract tests."""
from __future__ import annotations

import copy
import unittest

from homelab import matrix
from homelab.config import ConfigError


def evidence(plan):
    key_hash = "a" * 64
    return {
        "kind": "homelab-matrix-evidence",
        "contract": matrix.CONTRACT,
        "plan_id": plan["plan_id"],
        "images": {
            role: {"version": plan["images"][role]["version"],
                   "platform_digest": plan["images"][role]["platform_digest"]}
            for role in matrix.ROLES
        },
        "identity": {
            "server_name": plan["identity"]["server_name"],
            "signing_key_sha256_before": key_hash,
            "signing_key_sha256_after": key_hash,
            "unchanged": True,
        },
        "exercise": {
            "login": True, "room_created": True, "text_event": True,
            "media_upload": True, "media_download": True,
            "element_http": True, "independent_sessions": True,
        },
        "backup": {
            "synapse_quiesced": True, "postgres_custom_dump": True,
            "config": True, "signing_key": True, "media": True,
            "element_config": True, "manifest_sha256": "b" * 64,
            "source_removed": True,
        },
        "restore": {
            "independent_root": True, "same_versions": True,
            "database_restored": True, "login": True, "room": True,
            "text_event": True, "media": True, "element_http": True,
        },
        "client_e2ee": {
            "server_backup_claimed": False,
            "client_key_backup_tested": False,
            "owner_validation_required": True,
        },
        "network": {
            "federation_enabled": False, "turn_tested": False,
            "bridges_tested": False, "outbound_integrations_enabled": False,
        },
        "resources": {"idle_memory_mib": 256.0, "peak_memory_mib": 512.0},
        "safety": {
            "production_paths_used": False,
            "production_credentials_used": False,
            "production_messages_read": False,
            "docker_socket_mounted": False,
            "cleanup_completed": True,
        },
    }


class MatrixModuleTests(unittest.TestCase):
    def setUp(self):
        self.images = matrix.load_images()
        self.selection = matrix.load_selection()
        self.plan = matrix.make_plan(self.selection, self.images)

    def test_images_are_immutable_multiarchitecture_inputs(self):
        for role in matrix.ROLES:
            item = self.images[role]
            self.assertIn("@sha256:", item["image"])
            self.assertEqual({"amd64", "arm64"},
                             set(item["platform_digests"]))

    def test_plan_preserves_identity_and_separates_e2ee(self):
        self.assertFalse(self.plan["identity"]["renamable_after_restore"])
        self.assertTrue(self.plan["identity"]["signing_key_required"])
        self.assertEqual("separate-owner-validated-key-backup",
                         self.plan["client_e2ee_recovery"])
        self.assertFalse(self.plan["production_state_adopted"])

    def test_compose_is_loopback_restricted_and_secret_file_backed(self):
        spec = matrix.compose(self.plan)
        synapse = spec["services"]["synapse"]
        element = spec["services"]["element"]
        database = spec["services"]["database"]
        self.assertEqual("127.0.0.1", synapse["ports"][0]["host_ip"])
        self.assertEqual("127.0.0.1", element["ports"][0]["host_ip"])
        self.assertEqual("/run/secrets/postgres_password",
                         database["environment"]["POSTGRES_PASSWORD_FILE"])
        self.assertNotIn("POSTGRES_PASSWORD", database["environment"])
        self.assertTrue(spec["networks"]["backend"]["internal"])
        self.assertNotIn("privileged", str(spec).casefold())
        self.assertNotIn("docker.sock", str(spec).casefold())

    def test_optional_integrations_default_off(self):
        self.assertEqual(matrix.FEATURES, self.plan["features"])
        self.assertFalse(self.plan["features"]["federation"])
        self.assertFalse(self.plan["features"]["turn"])
        self.assertFalse(self.plan["features"]["bridges"])
        self.assertFalse(self.plan["features"]["admin_ui"])

    def test_rejects_identity_rename(self):
        changed = copy.deepcopy(self.selection)
        changed["server_name"] = "new.example.invalid"
        changed["public_base_url"] = "https://new.example.invalid/"
        changed_plan = matrix.make_plan(changed, self.images)
        self.assertNotEqual(self.plan["plan_id"], changed_plan["plan_id"])
        invalid = copy.deepcopy(self.plan)
        invalid["identity"]["server_name"] = "new.example.invalid"
        with self.assertRaises(ConfigError):
            matrix.validate_plan(invalid)

    def test_rejects_public_bind_and_enabled_bridge(self):
        changed = copy.deepcopy(self.selection)
        changed["access"] = "public"
        with self.assertRaises(ConfigError):
            matrix.validate_selection(changed)
        changed = copy.deepcopy(self.selection)
        changed["features"]["bridges"] = True
        with self.assertRaises(ConfigError):
            matrix.validate_selection(changed)

    def test_rejects_overlapping_state_and_media(self):
        changed = copy.deepcopy(self.selection)
        changed["media_root"] = changed["state_root"] + "\\media"
        with self.assertRaises(ConfigError):
            matrix.validate_selection(changed)

    def test_validates_complete_recovery_evidence(self):
        proof = evidence(self.plan)
        self.assertEqual(proof, matrix.validate_evidence(proof, self.plan))

    def test_rejects_changed_signing_key(self):
        proof = evidence(self.plan)
        proof["identity"]["signing_key_sha256_after"] = "c" * 64
        with self.assertRaises(ConfigError):
            matrix.validate_evidence(proof, self.plan)

    def test_rejects_false_e2ee_recovery_claim(self):
        proof = evidence(self.plan)
        proof["client_e2ee"]["server_backup_claimed"] = True
        with self.assertRaises(ConfigError):
            matrix.validate_evidence(proof, self.plan)

    def test_rejects_missing_restored_media(self):
        proof = evidence(self.plan)
        proof["restore"]["media"] = False
        with self.assertRaises(ConfigError):
            matrix.validate_evidence(proof, self.plan)


if __name__ == "__main__":
    unittest.main()
