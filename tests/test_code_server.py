"""Phase 7 code-server build, Compose and proof-contract tests."""
from __future__ import annotations

import copy
import json
import unittest

from homelab.config import ConfigError
from homelab import code_server as code


def evidence(plan: dict) -> dict:
    return {
        "kind": "homelab-code-server-evidence",
        "contract": code.CONTRACT,
        "plan_id": plan["plan_id"],
        "build": {
            "architecture": plan["architecture"],
            "code_server_version": plan["build"]["code_server_version"],
            "node_version": plan["build"]["node_version"],
            "node_archive_sha256": plan["build"]["node_archive"]["sha256"],
            "platform_digest": plan["build"]["platform_digest"],
            "extensions": [f"{item['id']}@{item['version']}"
                           for item in plan["build"]["extensions"]],
        },
        "exercise": {
            "synthetic_project": True,
            "server_side_compile": True,
            "compile_exit_code": 0,
            "source_sha256": "a" * 64,
            "artifact_sha256": "b" * 64,
            "http_health": True,
            "reconnect_after_restart": True,
        },
        "persistence": {
            "autosave": True,
            "settings": True,
            "extensions": True,
            "workspace": True,
            "terminal_policy": True,
            "container_recreated": True,
        },
        "recovery": {
            "services_stopped": True,
            "included": ["config", "local", "secure", "workspace"],
            "independent_root": True,
            "restored": True,
            "source_hash_match": True,
            "settings_hash_match": True,
        },
        "resources": {
            "idle_memory_mib": 180.0,
            "compile_peak_memory_mib": 512.0,
            "compile_peak_cpu_percent": 95.0,
        },
        "safety": {
            "production_paths_used": False,
            "production_credentials_used": False,
            "private_workspace_read": False,
            "docker_socket_mounted": False,
            "runtime_extension_network": False,
            "cleanup_completed": True,
        },
    }


class CodeServerBuildTests(unittest.TestCase):
    def test_manifest_has_multiarch_immutable_inputs(self):
        build = code.load_build()
        self.assertIn("@sha256:", build["code_server"]["image"])
        self.assertEqual(set(build["code_server"]["platform_digests"]),
                         {"amd64", "arm64"})
        self.assertEqual(set(build["node"]["archives"]), {"amd64", "arm64"})
        for archive in build["node"]["archives"].values():
            self.assertEqual(len(archive["sha256"]), 64)
        self.assertTrue(all(item["version"] for item in build["extensions"]))

    def test_extension_text_matches_reviewed_manifest(self):
        build = code.load_build()
        expected = [f"{item['id']}@{item['version']}"
                    for item in build["extensions"]]
        actual = [line for line in
                  (code.IMAGE_CONTEXT / "extensions.txt").read_text(
                      encoding="utf-8").splitlines() if line]
        self.assertEqual(actual, expected)

    def test_dockerfile_maps_both_architectures_and_checks_versions(self):
        text = (code.IMAGE_CONTEXT / "Dockerfile").read_text(encoding="utf-8")
        for marker in ("TARGETARCH", "amd64) node_arch=x64",
                       "arm64) node_arch=arm64", "sha256sum --check --strict",
                       "'/^[0-9][0-9]*\\.[0-9][0-9]*\\.[0-9][0-9]*/",
                       "test \"$actual\" = \"$CODE_SERVER_VERSION\""):
            self.assertIn(marker, text)
        self.assertNotIn("linux-x64.tar.xz\"", text)


class CodeServerPlanningTests(unittest.TestCase):
    def setUp(self):
        self.selection = code.load_selection()
        self.plan = code.make_plan(self.selection)

    def test_plan_is_deterministic_private_and_nonadopting(self):
        self.assertEqual(self.plan, code.make_plan(self.selection))
        self.assertFalse(self.plan["production_state_adopted"])
        self.assertFalse(self.plan["deployment_performed"])
        self.assertEqual(self.plan["authentication"],
                         "private-config-file-required")
        self.assertIn("ssh-keys", self.plan["private_material"])

    def test_architecture_selects_matching_node_and_platform_digest(self):
        for arch in ("amd64", "arm64"):
            value = copy.deepcopy(self.selection)
            value["architecture"] = arch
            plan = code.make_plan(value)
            self.assertIn(arch, plan["build"]["image"])
            self.assertEqual(plan["build"]["node_archive"],
                             code.load_build()["node"]["archives"][arch])

    def test_overlap_public_access_and_feature_drift_fail_closed(self):
        value = copy.deepcopy(self.selection)
        value["workspace_root"] = value["state_root"] + "\\workspace"
        with self.assertRaisesRegex(ConfigError, "must not overlap"):
            code.make_plan(value)
        value = copy.deepcopy(self.selection)
        value["access"] = "lan"
        with self.assertRaisesRegex(ConfigError, "loopback-only"):
            code.make_plan(value)
        value = copy.deepcopy(self.selection)
        value["features"]["runtime_extension_network"] = True
        with self.assertRaisesRegex(ConfigError, "policy changed"):
            code.make_plan(value)

    def test_plan_tamper_is_rejected(self):
        changed = copy.deepcopy(self.plan)
        changed["build"]["code_server_version"] = "0.0.0"
        with self.assertRaisesRegex(ConfigError, "changed"):
            code.validate_plan(changed)


class CodeServerComposeTests(unittest.TestCase):
    def setUp(self):
        self.plan = code.make_plan(code.load_selection())
        self.spec = code.compose(self.plan)
        self.service = self.spec["services"]["code-server"]

    def test_runtime_is_loopback_bounded_and_unprivileged(self):
        self.assertEqual(self.service["ports"], [{
            "target": 8080, "published": "18443",
            "host_ip": "127.0.0.1", "protocol": "tcp"}])
        self.assertEqual(self.service["cap_drop"], ["ALL"])
        self.assertEqual(self.service["security_opt"],
                         ["no-new-privileges:true"])
        self.assertEqual(self.service["restart"], "unless-stopped")
        self.assertTrue(self.service["init"])

    def test_all_state_scopes_persist_without_docker_control(self):
        targets = {item["target"] for item in self.service["volumes"]}
        self.assertEqual(targets, set(code.MOUNTS.values()))
        text = json.dumps(self.spec).casefold()
        self.assertNotIn("docker.sock", text)
        self.assertNotIn("privileged", text)
        self.assertNotIn("password", text)
        self.assertEqual(self.service["pull_policy"], "never")

    def test_resource_and_health_contract_is_present(self):
        self.assertEqual(self.service["mem_limit"], "6144m")
        self.assertEqual(self.service["mem_reservation"], "512m")
        self.assertEqual(self.service["cpus"], 6.0)
        self.assertEqual(self.service["pids_limit"], 2048)
        self.assertIn("/healthz", " ".join(self.service["healthcheck"]["test"]))
        args = self.service["build"]["args"]
        self.assertEqual(args["CODE_SERVER_PLATFORM_DIGEST"],
                         self.plan["build"]["platform_digest"])
        self.assertEqual(args["NODE_ARCHIVE_SHA256"],
                         self.plan["build"]["node_archive"]["sha256"])


class CodeServerEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.plan = code.make_plan(code.load_selection())
        self.value = evidence(self.plan)

    def test_complete_evidence_passes(self):
        self.assertEqual(code.validate_evidence(self.value, self.plan), self.value)

    def test_version_compile_persistence_recovery_and_safety_fail_closed(self):
        changes = [
            lambda value: value["build"].__setitem__("code_server_version", "0.0.0"),
            lambda value: value["exercise"].__setitem__("compile_exit_code", 1),
            lambda value: value["persistence"].__setitem__("settings", False),
            lambda value: value["recovery"].__setitem__("independent_root", False),
            lambda value: value["safety"].__setitem__("private_workspace_read", True),
        ]
        for change in changes:
            value = copy.deepcopy(self.value)
            change(value)
            with self.subTest(change=change), self.assertRaises(ConfigError):
                code.validate_evidence(value, self.plan)

    def test_memory_above_limit_is_rejected(self):
        value = copy.deepcopy(self.value)
        value["resources"]["compile_peak_memory_mib"] = 999999
        with self.assertRaisesRegex(ConfigError, "exceeds"):
            code.validate_evidence(value, self.plan)


if __name__ == "__main__":
    unittest.main()
