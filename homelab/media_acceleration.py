"""Phase 6 media-safety policy and read-only acceleration capability audit."""
from __future__ import annotations

import json
import platform
import re
import subprocess
from pathlib import Path

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .sandbox import digest


CONTRACT = "phase6-media-acceleration-v1"
POLICY = ROOT / "modules/phase6/media-policy.example.json"
CUDA_MIN_COMPUTE = 5.2
CUDA_MIN_DRIVER = 545.0
STORAGE_CLASSES = {
    "authoritative": ("configuration", "database", "originals", "profile"),
    "derived": ("encoded-video", "thumbnails"),
    "cache": ("machine-learning-models", "search-index", "transcode-cache"),
}
HEAVY_JOBS = (
    "facial-recognition",
    "library-scan",
    "ocr",
    "smart-search",
    "thumbnail-generation",
    "video-transcoding",
)
RESOURCE_ROLES = ("cache", "database", "machine-learning", "server")


def validate_policy(value: object) -> dict:
    keys(value, {"kind", "contract", "execution", "storage", "jobs",
                 "acceleration", "resources"}, "Phase 6 media policy")
    need(value["kind"] == "homelab-phase6-media-policy"
         and value["contract"] == CONTRACT,
         "Unsupported Phase 6 media policy")
    need(value["execution"] == "disabled-review-only",
         "The foundation policy must not enable workloads")
    storage = value["storage"]
    keys(storage, {"classes", "rules"}, "media storage policy")
    keys(storage["classes"], set(STORAGE_CLASSES), "media storage classes")
    for name, expected in STORAGE_CLASSES.items():
        need(tuple(storage["classes"][name]) == expected,
             f"Media {name} classification changed")
    keys(storage["rules"], {"originals_backed_up", "derived_rebuildable",
                            "cache_excluded", "destructive_cleanup"},
         "media storage rules")
    need(storage["rules"]["originals_backed_up"] is True
         and storage["rules"]["derived_rebuildable"] is True
         and storage["rules"]["cache_excluded"] is True
         and storage["rules"]["destructive_cleanup"] ==
         "explicit-confirmation-required",
         "Media preservation rules cannot be weakened")
    keys(value["jobs"], set(HEAVY_JOBS), "heavy-job policy")
    need(all(value["jobs"][name] == "manual" for name in HEAVY_JOBS),
         "Heavy media jobs must remain manual")
    acceleration = value["acceleration"]
    keys(acceleration, {"default", "enablement", "fallback", "backends"},
         "acceleration policy")
    need(acceleration["default"] == "cpu" and acceleration["fallback"] == "cpu"
         and acceleration["enablement"] ==
         "capability-and-synthetic-test-required",
         "Acceleration must fail closed to CPU")
    need(acceleration["backends"] == ["cuda", "nvenc", "openvino",
                                      "quicksync", "rocm", "vaapi"],
         "Reviewed acceleration backend list changed")
    keys(value["resources"], set(RESOURCE_ROLES), "media resource policy")
    total = 0
    for role in RESOURCE_ROLES:
        item = value["resources"][role]
        keys(item, {"memory_mib", "cpus", "pids"}, f"{role} resource policy")
        need(type(item["memory_mib"]) is int and 64 <= item["memory_mib"] <= 4096,
             "Invalid bounded media memory policy")
        need(type(item["cpus"]) in (int, float) and not isinstance(item["cpus"], bool)
             and 0.1 <= item["cpus"] <= 4.0,
             "Invalid bounded media CPU policy")
        need(type(item["pids"]) is int and 32 <= item["pids"] <= 1024,
             "Invalid bounded media PID policy")
        total += item["memory_mib"]
    need(total <= 6144, "Media foundation exceeds its reviewed memory ceiling")
    return json.loads(canonical(value))


def load_policy(path: Path = POLICY) -> dict:
    return validate_policy(load_json(path))


def _command(arguments: list[str]) -> tuple[int, str]:
    try:
        process = subprocess.run(arguments, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=20,
                                 check=False)
        return process.returncode, process.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def _docker_probe(runner) -> dict:
    context_code, context = runner(["docker", "context", "show"])
    version_code, version_text = runner(
        ["docker", "version", "--format", "{{json .Server}}"])
    runtimes_code, runtimes_text = runner(
        ["docker", "info", "--format", "{{json .Runtimes}}"])
    version = {}
    runtime_names: list[str] = []
    try:
        if version_code == 0:
            raw = json.loads(version_text)
            version = {"version": raw.get("Version"), "os": raw.get("Os"),
                       "architecture": raw.get("Arch"),
                       "kernel": raw.get("KernelVersion")}
        if runtimes_code == 0:
            runtime_names = sorted(json.loads(runtimes_text))
    except (TypeError, json.JSONDecodeError):
        version = {}
        runtime_names = []
    available = context_code == version_code == runtimes_code == 0 and bool(version)
    return {"available": available,
            "context": context if context_code == 0 and context else None,
            "server": version if available else None,
            "runtimes": runtime_names if available else []}


def _nvidia_probe(runner) -> dict:
    code, output = runner([
        "nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"
    ])
    devices = []
    if code == 0:
        for line in output.splitlines():
            parts = [part.strip() for part in line.split(",", 1)]
            if len(parts) == 2 and parts[0] and re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", parts[1]):
                item = {"name": parts[0], "driver": parts[1],
                        "compute_capability": None}
                if parts[0].casefold() == "geforce gt 730":
                    # NVIDIA lists board variants at 2.1 and 3.5. The exact board
                    # is immaterial here because both are below Immich's 5.2 floor.
                    item["compute_capability"] = {"minimum": 2.1, "maximum": 3.5,
                                                  "source": "nvidia-legacy-table"}
                devices.append(item)
    return {"available": bool(devices), "devices": devices}


def audit(runner=None) -> dict:
    """Return a privacy-bounded, read-only host capability report."""
    run = runner or _command
    probe = {
        "kind": "homelab-phase6-capability-audit",
        "contract": CONTRACT,
        "host_platform": platform.system().lower(),
        "docker": _docker_probe(run),
        "nvidia": _nvidia_probe(run),
        "mutations_performed": False,
        "synthetic_gpu_test": "not-run",
    }
    probe["decision"] = assess_acceleration(probe)
    return probe


def _driver_major(value: str) -> float | None:
    match = re.match(r"([0-9]+)(?:\.([0-9]+))?", value)
    if not match:
        return None
    return float(match.group(1) + "." + (match.group(2) or "0"))


def assess_acceleration(probe: dict) -> dict:
    reasons = []
    docker = probe.get("docker") or {}
    nvidia = probe.get("nvidia") or {}
    if not docker.get("available"):
        reasons.append("docker-engine-unavailable")
    elif "nvidia" not in docker.get("runtimes", []):
        reasons.append("nvidia-container-runtime-unavailable")
    devices = nvidia.get("devices") or []
    if not devices:
        reasons.append("nvidia-device-unavailable")
    for device in devices:
        capability = device.get("compute_capability")
        if capability is None:
            reasons.append("compute-capability-unverified")
        elif capability["maximum"] < CUDA_MIN_COMPUTE:
            reasons.append("compute-capability-below-5.2")
        driver = _driver_major(device.get("driver", ""))
        if driver is None:
            reasons.append("driver-version-unverified")
        elif driver < CUDA_MIN_DRIVER:
            reasons.append("nvidia-driver-below-545")
    reasons = sorted(set(reasons))
    eligible = not reasons
    return {
        "selected": "cpu",
        "cuda_status": ("eligible-for-synthetic-test" if eligible else "blocked"),
        "cuda_requirements": {"minimum_compute_capability": CUDA_MIN_COMPUTE,
                              "minimum_driver": CUDA_MIN_DRIVER},
        "blocking_reasons": reasons,
        "synthetic_test_required": True,
        "gpu_enabled": False,
    }


def make_plan(policy: dict, capability_audit: dict) -> dict:
    policy = validate_policy(policy)
    need(capability_audit.get("kind") == "homelab-phase6-capability-audit"
         and capability_audit.get("contract") == CONTRACT,
         "Capability audit does not match the Phase 6 contract")
    decision = assess_acceleration(capability_audit)
    plan = {
        "kind": "homelab-phase6-media-plan",
        "contract": CONTRACT,
        "execution": "disabled-review-only",
        "policy_fingerprint": digest(policy),
        "storage": policy["storage"],
        "jobs": policy["jobs"],
        "resources": policy["resources"],
        "acceleration": decision,
        "host": {"platform": capability_audit["host_platform"],
                 "docker": capability_audit["docker"],
                 "nvidia": capability_audit["nvidia"]},
        "production_media_used": False,
        "deployment_performed": False,
    }
    plan["plan_id"] = digest(plan)
    return plan
