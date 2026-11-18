"""Docker update manager contracts; no Docker daemon is used."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from homelab.config import ConfigError
from homelab import docker_updates as updates


COMPOSE = """services:
  seerr:
    image: ghcr.io/seerr-team/seerr:latest
    restart: unless-stopped
  db:
    image: postgres:18-alpine
"""
REMOTE = {"status": "checked", "digest": "sha256:" + "b" * 64}


class DockerUpdateManagerTests(unittest.TestCase):
    def policy(self, root: Path) -> dict:
        return {
            "schema_version": 1,
            "state_root": str(root / "state"),
            "defaults": {"mode": "audit-only"},
            "projects": {
                "arr-stack": {
                    "mode": "manual",
                    "services": {
                        "seerr": {
                            "enabled": True,
                            "backup_required": True,
                            "backup_paths": [str(root / "seerr-config")],
                        }
                    },
                }
            },
        }

    def audit(self, compose: Path) -> dict:
        return {
            "kind": "homelab-docker-update-audit",
            "contract": 1,
            "projects": [{
                "name": "arr-stack", "owner": "operator", "mode": "manual",
                "config_files": [str(compose)],
                "services": [{
                    "service": "seerr", "image": "ghcr.io/seerr-team/seerr:latest",
                    "image_id": "sha256:" + "a" * 64,
                }],
            }],
        }

    def test_plan_requires_exact_target_and_explicit_service_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            compose = root / "docker-compose.yml"
            compose.write_text(COMPOSE, encoding="utf-8")
            (root / "seerr-config").mkdir()
            policy = self.policy(root)
            with self.assertRaisesRegex(ConfigError, "exact version"):
                updates.make_plan(self.audit(compose), policy, "arr-stack", "seerr",
                                  "ghcr.io/seerr-team/seerr:latest", REMOTE)
            plan = updates.make_plan(self.audit(compose), policy, "arr-stack", "seerr",
                                     "ghcr.io/seerr-team/seerr:v3.5.2", REMOTE)
            self.assertFalse(plan["automatic"])
            self.assertEqual(plan["target_remote_digest"], REMOTE["digest"])
            self.assertEqual(updates.validate_plan(plan), plan)

    def test_plan_rejects_repository_switch_and_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            compose = root / "docker-compose.yml"
            compose.write_text(COMPOSE, encoding="utf-8")
            (root / "seerr-config").mkdir()
            with self.assertRaisesRegex(ConfigError, "repository differs"):
                updates.make_plan(self.audit(compose), self.policy(root), "arr-stack", "seerr",
                                  "example.invalid/seerr:v3.5.2", REMOTE)
            plan = updates.make_plan(self.audit(compose), self.policy(root), "arr-stack", "seerr",
                                     "ghcr.io/seerr-team/seerr:v3.5.2", REMOTE)
            changed = copy.deepcopy(plan)
            changed["target_image"] = "ghcr.io/seerr-team/seerr:v9.9.9"
            with self.assertRaisesRegex(ConfigError, "changed after review"):
                updates.validate_plan(changed)

    def test_plan_rejects_scaled_or_duplicate_service_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            compose = root / "docker-compose.yml"
            compose.write_text(COMPOSE, encoding="utf-8")
            (root / "seerr-config").mkdir()
            audit = self.audit(compose)
            audit["projects"][0]["services"].append(
                copy.deepcopy(audit["projects"][0]["services"][0]))
            with self.assertRaisesRegex(ConfigError, "exactly one container"):
                updates.make_plan(audit, self.policy(root), "arr-stack", "seerr",
                                  "ghcr.io/seerr-team/seerr:v3.5.2", REMOTE)

    def test_image_replacement_is_bounded_to_selected_service(self):
        changed = updates.replace_service_image(
            COMPOSE, "seerr", "ghcr.io/seerr-team/seerr:v3.5.2")
        self.assertIn("image: ghcr.io/seerr-team/seerr:v3.5.2", changed)
        self.assertIn("image: postgres:18-alpine", changed)

    def test_image_replacement_rejects_missing_or_complex_image(self):
        with self.assertRaisesRegex(ConfigError, "not found"):
            updates.replace_service_image(COMPOSE, "sonarr", "x/y:v1")
        complex_compose = "services:\n  app:\n    build: .\n"
        with self.assertRaisesRegex(ConfigError, "exactly one"):
            updates.replace_service_image(complex_compose, "app", "x/y:v1")

    def test_controller_and_unknown_projects_are_not_operator_managed(self):
        policy = {"projects": {}, "defaults": {"mode": "audit-only"},
                  "controller_path_patterns": [r"(?i)[/\\]artifacts[/\\]"]}
        controller = updates._project_rule(policy, "random", ["/artifacts/app/compose.yaml"])
        unknown = updates._project_rule(policy, "unknown", ["C:/Docker/unknown/compose.yml"])
        self.assertEqual(controller["mode"], "controller-managed")
        self.assertEqual(unknown["owner"], "unreviewed")

    def test_policy_accepts_platform_absolute_examples_and_rejects_relative_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            policy_file = root / "policy.json"
            policy_file.write_text(
                '{"schema_version":1,"state_root":"C:/Docker/maintenance/state",'
                '"projects":{}}', encoding="utf-8")
            self.assertEqual(updates.load_policy(policy_file)["schema_version"], 1)
            policy_file.write_text(
                '{"schema_version":1,"state_root":"relative/state","projects":{}}',
                encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "absolute"):
                updates.load_policy(policy_file)


if __name__ == "__main__":
    unittest.main()
