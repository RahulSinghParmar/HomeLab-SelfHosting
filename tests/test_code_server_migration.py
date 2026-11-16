import copy
import unittest

from homelab import code_server_migration as migration
from homelab.config import ConfigError
from homelab.sandbox import digest


def evidence(plan):
    value = {
        "kind": "homelab-code-server-production-migration-evidence",
        "contract": migration.CONTRACT,
        "plan_id": plan["plan_id"],
        "backup": {
            "restic_version": "0.19.1",
            "restic_sha256": plan["backup"]["tool"]["executable_sha256"],
            "snapshot_id": "a" * 64,
            "services_stopped": True,
            "included": migration.BACKUP_INCLUDED,
            "encrypted": True,
            "repository_check_read_data": True,
            "repository_separate_physical_disk": True,
            "recovery_key_separate_physical_disk": True,
            "plaintext_staging_removed": True,
        },
        "restore": {
            "independent_root": True,
            "archive_hashes_match": True,
            "code_server_version": "4.145.0",
            "node_version": "24.19.0",
            "extension_count": 20,
            "server_side_compile": True,
            "http_health": True,
            "restart_persistence": True,
        },
        "production": {
            "source_code_server_version": "4.131.0",
            "target_code_server_version": "4.145.0",
            "node_version": "24.19.0",
            "image_id": "sha256:" + "b" * 64,
            "loopback_only": True,
            "published_port": 8443,
            "limits": plan["limits"],
            "mount_targets": migration.MOUNT_TARGETS,
            "server_side_compile": True,
            "local_health": True,
            "public_health": True,
            "compose_restart": True,
            "rollback_compose_backup": True,
            "encrypted_state_recovery": True,
        },
        "safety": {
            "credentials_read": False,
            "workspace_content_read": False,
            "production_workspace_modified": False,
            "docker_socket_mounted": False,
            "old_image_retained": True,
        },
    }
    value["evidence_id"] = digest(value)
    return value


class CodeServerMigrationTests(unittest.TestCase):
    def setUp(self):
        self.policy = migration.load_policy()
        self.plan = migration.make_plan(self.policy)

    def refresh(self, value):
        clone = dict(value)
        clone.pop("evidence_id", None)
        value["evidence_id"] = digest(clone)

    def test_reviewed_restic_release_is_checksum_locked(self):
        restic = migration.load_restic()
        self.assertEqual(restic["version"], "0.19.1")
        self.assertEqual(len(restic["windows_amd64"]["executable_sha256"]), 64)

    def test_plan_is_deterministic_and_nonexecuting(self):
        self.assertEqual(self.plan, migration.make_plan(self.policy))
        self.assertFalse(self.plan["production_change_authorized"])
        self.assertFalse(self.plan["execution_performed"])
        migration.validate_plan(self.plan)

    def test_complete_migration_evidence_passes(self):
        migration.validate_evidence(evidence(self.plan), self.plan)

    def test_backup_requires_stopped_encrypted_full_check(self):
        for field in ("services_stopped", "encrypted",
                      "repository_check_read_data", "plaintext_staging_removed"):
            value = evidence(self.plan)
            value["backup"][field] = False
            self.refresh(value)
            with self.assertRaises(ConfigError):
                migration.validate_evidence(value, self.plan)

    def test_restore_requires_real_runtime_compile_and_restart(self):
        for field in ("independent_root", "archive_hashes_match",
                      "server_side_compile", "http_health", "restart_persistence"):
            value = evidence(self.plan)
            value["restore"][field] = False
            self.refresh(value)
            with self.assertRaises(ConfigError):
                migration.validate_evidence(value, self.plan)

    def test_production_requires_loopback_public_health_and_rollback(self):
        for field in ("loopback_only", "local_health", "public_health",
                      "compose_restart", "rollback_compose_backup",
                      "encrypted_state_recovery"):
            value = evidence(self.plan)
            value["production"][field] = False
            self.refresh(value)
            with self.assertRaises(ConfigError):
                migration.validate_evidence(value, self.plan)

    def test_safety_drift_is_rejected(self):
        value = evidence(self.plan)
        value["safety"]["credentials_read"] = True
        self.refresh(value)
        with self.assertRaises(ConfigError):
            migration.validate_evidence(value, self.plan)

    def test_tampering_is_rejected(self):
        value = evidence(self.plan)
        value["production"]["published_port"] = 18443
        with self.assertRaises(ConfigError):
            migration.validate_evidence(value, self.plan)
        changed = copy.deepcopy(self.plan)
        changed["limits"]["cpus"] = 7.0
        with self.assertRaises(ConfigError):
            migration.validate_plan(changed)


if __name__ == "__main__":
    unittest.main()
