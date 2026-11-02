"""Phase 6 media preservation and acceleration decision tests."""
from __future__ import annotations

import copy
import json
import unittest

from homelab.config import ConfigError
from homelab.media_acceleration import (
    CONTRACT, assess_acceleration, audit, load_policy, make_plan, validate_policy,
)


def probe(*, device="GeForce GT 730", driver="391.35", capability=(2.1, 3.5),
          docker=True, nvidia_runtime=True):
    devices = []
    if device:
        devices.append({
            "name": device,
            "driver": driver,
            "compute_capability": ({"minimum": capability[0], "maximum": capability[1],
                                    "source": "test"} if capability else None),
        })
    return {
        "kind": "homelab-phase6-capability-audit",
        "contract": CONTRACT,
        "host_platform": "windows",
        "docker": {"available": docker, "context": "desktop-linux" if docker else None,
                   "server": {"version": "test", "os": "linux",
                              "architecture": "amd64", "kernel": "test"} if docker else None,
                   "runtimes": (["nvidia", "runc"] if nvidia_runtime else ["runc"])},
        "nvidia": {"available": bool(devices), "devices": devices},
        "mutations_performed": False,
        "synthetic_gpu_test": "not-run",
    }


class MediaAccelerationTests(unittest.TestCase):
    def test_reviewed_policy_passes(self):
        policy = load_policy()
        self.assertEqual(policy["contract"], CONTRACT)
        self.assertEqual(policy["acceleration"]["default"], "cpu")
        self.assertTrue(policy["storage"]["rules"]["originals_backed_up"])
        self.assertTrue(all(value == "manual" for value in policy["jobs"].values()))

    def test_automatic_heavy_job_is_rejected(self):
        policy = copy.deepcopy(load_policy())
        policy["jobs"]["thumbnail-generation"] = "automatic"
        with self.assertRaisesRegex(ConfigError, "must remain manual"):
            validate_policy(policy)

    def test_originals_cannot_be_reclassified_as_derived(self):
        policy = copy.deepcopy(load_policy())
        policy["storage"]["classes"]["authoritative"].remove("originals")
        policy["storage"]["classes"]["derived"].append("originals")
        with self.assertRaisesRegex(ConfigError, "classification changed"):
            validate_policy(policy)

    def test_resource_ceiling_is_enforced(self):
        policy = copy.deepcopy(load_policy())
        policy["resources"]["server"]["memory_mib"] = 4096
        policy["resources"]["machine-learning"]["memory_mib"] = 4096
        with self.assertRaisesRegex(ConfigError, "memory ceiling"):
            validate_policy(policy)

    def test_gt730_is_blocked_and_cpu_selected(self):
        decision = assess_acceleration(probe())
        self.assertEqual(decision["selected"], "cpu")
        self.assertEqual(decision["cuda_status"], "blocked")
        self.assertIn("compute-capability-below-5.2", decision["blocking_reasons"])
        self.assertIn("nvidia-driver-below-545", decision["blocking_reasons"])
        self.assertFalse(decision["gpu_enabled"])

    def test_supported_candidate_still_requires_synthetic_test(self):
        decision = assess_acceleration(
            probe(device="Modern test GPU", driver="560.10", capability=(8.6, 8.6)))
        self.assertEqual(decision["cuda_status"], "eligible-for-synthetic-test")
        self.assertEqual(decision["selected"], "cpu")
        self.assertTrue(decision["synthetic_test_required"])
        self.assertFalse(decision["gpu_enabled"])

    def test_missing_runtime_and_device_fail_closed(self):
        decision = assess_acceleration(
            probe(device=None, driver="", capability=None, nvidia_runtime=False))
        self.assertEqual(decision["selected"], "cpu")
        self.assertIn("nvidia-container-runtime-unavailable", decision["blocking_reasons"])
        self.assertIn("nvidia-device-unavailable", decision["blocking_reasons"])

    def test_audit_filters_docker_details_and_maps_legacy_gpu(self):
        responses = {
            ("docker", "context", "show"): (0, "desktop-linux"),
            ("docker", "version", "--format", "{{json .Server}}"): (
                0, json.dumps({"Version": "29.9.2", "Os": "linux", "Arch": "amd64",
                               "KernelVersion": "6.18-test", "Private": "discard"})),
            ("docker", "info", "--format", "{{json .Runtimes}}"): (
                0, json.dumps({"runc": {"private": "discard"}, "nvidia": {}})),
            ("nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"): (
                0, "GeForce GT 730, 391.35"),
        }
        result = audit(lambda arguments: responses[tuple(arguments)])
        self.assertFalse(result["mutations_performed"])
        self.assertEqual(result["docker"]["runtimes"], ["nvidia", "runc"])
        self.assertNotIn("Private", result["docker"]["server"])
        self.assertEqual(result["nvidia"]["devices"][0]["compute_capability"]["maximum"], 3.5)
        self.assertEqual(result["decision"]["cuda_status"], "blocked")

    def test_plan_is_deterministic_and_non_activating(self):
        first = make_plan(load_policy(), probe())
        second = make_plan(load_policy(), probe())
        self.assertEqual(first, second)
        self.assertEqual(first["execution"], "disabled-review-only")
        self.assertEqual(first["acceleration"]["selected"], "cpu")
        self.assertFalse(first["production_media_used"])
        self.assertFalse(first["deployment_performed"])

    def test_foreign_audit_is_rejected(self):
        value = probe()
        value["contract"] = "foreign"
        with self.assertRaisesRegex(ConfigError, "does not match"):
            make_plan(load_policy(), value)


if __name__ == "__main__":
    unittest.main()
