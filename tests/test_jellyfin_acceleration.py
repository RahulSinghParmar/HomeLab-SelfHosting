"""Jellyfin native acceleration decision and synthetic-proof tests."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from homelab.config import ConfigError
from homelab.jellyfin_acceleration import (
    AUDIT_KIND,
    CONTRACT,
    NVIDIA_MIN_WINDOWS_DRIVER,
    assess_backends,
    audit,
    make_proof,
    validate_audit,
    validate_proof,
)


def capability(*, nvidia_driver="391.35", qsv=True, nvenc=True,
               jellyfin_build=True):
    value = {
        "kind": AUDIT_KIND,
        "contract": CONTRACT,
        "host_platform": "windows",
        "ffmpeg": {
            "available": True,
            "identity": "ffmpeg.exe",
            "version": "8.1.3-Jellyfin" if jellyfin_build else "8.1",
            "jellyfin_build": jellyfin_build,
            "libx264": True,
            "qsv": qsv,
            "nvenc": nvenc,
        },
        "adapters": [
            {"vendor": "intel", "name": "Intel UHD Graphics 730",
             "driver": "32.0.101.7092"},
            {"vendor": "nvidia", "name": "NVIDIA GeForce GT 730",
             "driver": nvidia_driver},
        ],
        "mutations_performed": False,
        "production_media_read": False,
        "jellyfin_configuration_read": False,
    }
    value["decision"] = assess_backends(value)
    return value


def run(role, *, speed=2.0):
    is_cpu = role == "cpu-baseline"
    hevc = role == "qsv-hevc"
    return {
        "role": role,
        "backend": "cpu" if is_cpu else "qsv",
        "codec": "hevc" if hevc else "h264",
        "status": "passed",
        "concurrency": 2 if role.startswith("qsv-concurrent-") else 1,
        "elapsed_seconds": 5.0,
        "speed": speed,
        "metrics": {"user_seconds": 1.2, "system_seconds": 0.3,
                    "max_rss_kib": 123456},
        "output": {
            "duration_seconds": 10.0,
            "width": 1280,
            "height": 720,
            "frames": 300,
            "size_bytes": 1_000_000,
            "sha256": ("a" if role.endswith("a") else "b") * 64,
            "ssim": 0.97,
        },
    }


def fixture():
    return {"synthetic": True, "duration_seconds": 10, "width": 1920,
            "height": 1080, "fps": 30, "source_codec": "h264"}


def complete_runs():
    return [run("cpu-baseline"), run("qsv-single"),
            run("qsv-concurrent-a"), run("qsv-concurrent-b")]


class JellyfinAccelerationTests(unittest.TestCase):
    def test_intel_qsv_candidate_and_legacy_nvidia_block(self):
        value = validate_audit(capability())
        self.assertEqual(value["decision"]["selected"], "cpu")
        self.assertFalse(value["decision"]["gpu_enabled"])
        self.assertEqual(value["decision"]["qsv"]["status"],
                         "eligible-for-synthetic-test")
        self.assertEqual(value["decision"]["nvenc"]["status"], "blocked")
        self.assertIn("nvidia-driver-below-522.25",
                      value["decision"]["nvenc"]["blocking_reasons"])
        self.assertEqual(value["decision"]["nvenc"]["minimum_windows_driver"],
                         NVIDIA_MIN_WINDOWS_DRIVER)

    def test_modern_nvidia_is_only_eligible_not_automatically_selected(self):
        value = capability(nvidia_driver="560.10")
        self.assertEqual(value["decision"]["nvenc"]["status"],
                         "eligible-for-synthetic-test")
        self.assertEqual(value["decision"]["selected"], "cpu")
        self.assertTrue(value["decision"]["synthetic_proof_required"])

    def test_non_jellyfin_ffmpeg_blocks_qsv(self):
        value = capability(jellyfin_build=False)
        self.assertEqual(value["decision"]["qsv"]["status"], "blocked")
        self.assertIn("jellyfin-ffmpeg-build-unverified",
                      value["decision"]["qsv"]["blocking_reasons"])

    def test_audit_sanitizes_executable_and_queries_read_only_evidence(self):
        def runner(arguments):
            joined = " ".join(arguments)
            if arguments[0] == "nvidia-smi":
                return 0, "NVIDIA GeForce GT 730, 391.35"
            if "Win32_VideoController" in joined:
                return 0, json.dumps([
                    {"Name": "Intel UHD Graphics 730",
                     "DriverVersion": "32.0.101.7092"},
                    {"Name": "NVIDIA GeForce GT 730",
                     "DriverVersion": "391.35"},
                ])
            if arguments[-1] == "-version":
                return 0, "ffmpeg version 8.1.3-Jellyfin test"
            if arguments[-1] == "-hwaccels":
                return 0, "Hardware acceleration methods:\nqsv\ncuda"
            if arguments[-1] == "-encoders":
                return 0, "libx264 h264_qsv h264_nvenc"
            return 127, ""

        value = audit(Path("/private/build/ffmpeg.exe"), runner=runner,
                      system="windows")
        self.assertEqual(value["ffmpeg"]["identity"], "ffmpeg.exe")
        self.assertNotIn("/private", json.dumps(value))
        self.assertFalse(value["mutations_performed"])
        self.assertFalse(value["production_media_read"])
        self.assertEqual(value["decision"]["qsv"]["status"],
                         "eligible-for-synthetic-test")

    def test_changed_decision_is_rejected(self):
        value = capability()
        value["decision"]["selected"] = "qsv"
        with self.assertRaisesRegex(ConfigError, "does not match"):
            validate_audit(value)

    def test_complete_synthetic_proof_selects_qsv_with_cpu_fallback(self):
        value = make_proof(capability(), fixture(), complete_runs(),
                           temporary_outputs_removed=True)
        self.assertEqual(value["decision"]["selected"], "qsv")
        self.assertEqual(value["decision"]["fallback"], "cpu")
        self.assertFalse(value["production_media_used"])
        self.assertFalse(value["jellyfin_configuration_changed"])
        self.assertTrue(value["temporary_outputs_removed"])

    def test_proof_requires_two_real_time_concurrent_qsv_runs(self):
        runs = complete_runs()
        runs[-1]["speed"] = 0.99
        with self.assertRaisesRegex(ConfigError, "real-time"):
            make_proof(capability(), fixture(), runs,
                       temporary_outputs_removed=True)

    def test_proof_rejects_missing_cpu_baseline(self):
        value = {
            "kind": "homelab-jellyfin-acceleration-proof",
            "contract": CONTRACT,
            "fixture": fixture(),
            "audit_fingerprint": "a" * 64,
            "runs": [run("qsv-single"), run("qsv-concurrent-a"),
                     run("qsv-concurrent-b"), run("qsv-hevc")],
            "decision": {"selected": "qsv", "gpu_enabled": True,
                         "fallback": "cpu",
                         "activation_scope": "jellyfin-native-transcode-only",
                         "nvenc": "blocked-or-not-selected"},
            "production_media_used": False,
            "jellyfin_configuration_changed": False,
            "temporary_outputs_removed": True,
        }
        with self.assertRaisesRegex(ConfigError, "missing"):
            validate_proof(value)

    def test_proof_rejects_low_quality_or_unremoved_output(self):
        low_quality = complete_runs()
        low_quality[1]["output"]["ssim"] = 0.70
        with self.assertRaisesRegex(ConfigError, "quality"):
            make_proof(capability(), fixture(), low_quality,
                       temporary_outputs_removed=True)
        with self.assertRaisesRegex(ConfigError, "non-production boundary"):
            make_proof(capability(), fixture(), complete_runs(),
                       temporary_outputs_removed=False)

    def test_foreign_and_ineligible_audits_fail_closed(self):
        foreign = capability()
        foreign["contract"] = "foreign"
        with self.assertRaisesRegex(ConfigError, "contract mismatch"):
            make_proof(foreign, fixture(), complete_runs(),
                       temporary_outputs_removed=True)
        ineligible = capability(qsv=False)
        with self.assertRaisesRegex(ConfigError, "not eligible"):
            make_proof(ineligible, fixture(), complete_runs(),
                       temporary_outputs_removed=True)


if __name__ == "__main__":
    unittest.main()
