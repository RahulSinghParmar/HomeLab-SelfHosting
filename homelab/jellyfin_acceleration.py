"""Native Jellyfin hardware-transcoding capability and proof contracts.

The module deliberately separates an observed capability from an activation
decision.  A backend is never selected until a fully synthetic, bounded proof
has passed; production media and Jellyfin configuration are outside scope.
"""
from __future__ import annotations

import json
import platform
import re
import subprocess
from pathlib import Path

from .config import canonical, keys, need
from .sandbox import digest


CONTRACT = "jellyfin-acceleration-v1"
AUDIT_KIND = "homelab-jellyfin-acceleration-audit"
PROOF_KIND = "homelab-jellyfin-acceleration-proof"
NVIDIA_MIN_WINDOWS_DRIVER = 522.25
REQUIRED_ROLES = (
    "cpu-baseline",
    "qsv-single",
    "qsv-concurrent-a",
    "qsv-concurrent-b",
)


def _version_number(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    match = re.match(r"^([0-9]+)(?:\.([0-9]+))?", value.strip())
    if not match:
        return None
    return float(f"{match.group(1)}.{match.group(2) or '0'}")


def _run(arguments: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        process = subprocess.run(
            arguments, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, check=False,
        )
        return process.returncode, (process.stdout + "\n" + process.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def _ffmpeg_capabilities(executable: Path, runner) -> dict:
    version_code, version_text = runner(
        [str(executable), "-hide_banner", "-version"])
    hw_code, hw_text = runner(
        [str(executable), "-hide_banner", "-hwaccels"])
    enc_code, enc_text = runner(
        [str(executable), "-hide_banner", "-encoders"])
    first = version_text.splitlines()[0] if version_code == 0 and version_text else ""
    version_match = re.search(r"ffmpeg version\s+([^\s]+)", first, re.IGNORECASE)
    lowered_hw = hw_text.casefold() if hw_code == 0 else ""
    lowered_enc = enc_text.casefold() if enc_code == 0 else ""
    return {
        "available": version_code == 0,
        "identity": executable.name,
        "version": version_match.group(1) if version_match else None,
        "jellyfin_build": "jellyfin" in first.casefold(),
        "libx264": "libx264" in lowered_enc,
        "qsv": "qsv" in lowered_hw and "h264_qsv" in lowered_enc,
        "nvenc": "cuda" in lowered_hw and "h264_nvenc" in lowered_enc,
    }


def _windows_adapters(runner) -> list[dict]:
    script = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,DriverVersion | ConvertTo-Json -Compress"
    )
    code, output = runner([
        "powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script,
    ])
    if code != 0 or not output:
        return []
    try:
        raw = json.loads(output)
    except json.JSONDecodeError:
        return []
    rows = raw if isinstance(raw, list) else [raw]
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("Name")
        driver = row.get("DriverVersion")
        if not isinstance(name, str) or not name.strip():
            continue
        folded = name.casefold()
        vendor = ("intel" if "intel" in folded else
                  "nvidia" if "nvidia" in folded or "geforce" in folded else
                  "amd" if "amd" in folded or "radeon" in folded else "other")
        result.append({"vendor": vendor, "name": name.strip(),
                       "driver": driver.strip() if isinstance(driver, str) else None})
    nvidia_code, nvidia_text = runner([
        "nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader",
    ])
    if nvidia_code == 0:
        observed = []
        for line in nvidia_text.splitlines():
            parts = [part.strip() for part in line.split(",", 1)]
            if len(parts) == 2 and parts[0] and re.fullmatch(
                    r"[0-9]+(?:\.[0-9]+){0,4}", parts[1]):
                observed.append((parts[0].casefold(), parts[1]))
        for adapter in result:
            if adapter["vendor"] != "nvidia":
                continue
            name = adapter["name"].casefold()
            for observed_name, driver in observed:
                if observed_name in name or name in observed_name:
                    adapter["driver"] = driver
                    break
    return sorted(result, key=lambda item: (item["vendor"], item["name"].casefold()))


def audit(ffmpeg: Path, *, runner=None, system: str | None = None) -> dict:
    """Return a sanitized, read-only host capability observation."""
    run = runner or _run
    host = (system or platform.system()).casefold()
    need(host in ("windows", "linux", "darwin"),
         "Unsupported Jellyfin acceleration host")
    adapters = _windows_adapters(run) if host == "windows" else []
    value = {
        "kind": AUDIT_KIND,
        "contract": CONTRACT,
        "host_platform": host,
        "ffmpeg": _ffmpeg_capabilities(Path(ffmpeg), run),
        "adapters": adapters,
        "mutations_performed": False,
        "production_media_read": False,
        "jellyfin_configuration_read": False,
    }
    value["decision"] = assess_backends(value)
    return value


def validate_audit(value: object) -> dict:
    keys(value, {"kind", "contract", "host_platform", "ffmpeg", "adapters",
                 "mutations_performed", "production_media_read",
                 "jellyfin_configuration_read", "decision"},
         "Jellyfin acceleration audit")
    need(value["kind"] == AUDIT_KIND and value["contract"] == CONTRACT,
         "Jellyfin acceleration audit contract mismatch")
    need(value["host_platform"] in ("windows", "linux", "darwin"),
         "Unsupported Jellyfin acceleration host")
    keys(value["ffmpeg"], {"available", "identity", "version", "jellyfin_build",
                           "libx264", "qsv", "nvenc"}, "FFmpeg capability")
    need(all(type(value["ffmpeg"][key]) is bool for key in
             ("available", "jellyfin_build", "libx264", "qsv", "nvenc")),
         "Invalid FFmpeg capability flags")
    need(isinstance(value["ffmpeg"]["identity"], str)
         and 1 <= len(value["ffmpeg"]["identity"]) <= 128
         and "/" not in value["ffmpeg"]["identity"]
         and "\\" not in value["ffmpeg"]["identity"],
         "FFmpeg identity must not expose a path")
    need(value["ffmpeg"]["version"] is None
         or (isinstance(value["ffmpeg"]["version"], str)
             and len(value["ffmpeg"]["version"]) <= 64),
         "Invalid FFmpeg version")
    need(isinstance(value["adapters"], list) and len(value["adapters"]) <= 16,
         "Invalid graphics-adapter list")
    for adapter in value["adapters"]:
        keys(adapter, {"vendor", "name", "driver"}, "graphics adapter")
        need(adapter["vendor"] in ("intel", "nvidia", "amd", "other"),
             "Invalid graphics-adapter vendor")
        need(isinstance(adapter["name"], str) and 1 <= len(adapter["name"]) <= 256,
             "Invalid graphics-adapter name")
        need(adapter["driver"] is None or
             (isinstance(adapter["driver"], str)
              and bool(re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,4}", adapter["driver"]))),
             "Invalid graphics-adapter driver")
    need(value["mutations_performed"] is False
         and value["production_media_read"] is False
         and value["jellyfin_configuration_read"] is False,
         "Jellyfin acceleration audit crossed its read-only boundary")
    expected = assess_backends({key: value[key] for key in value if key != "decision"})
    need(canonical(value["decision"]) == canonical(expected),
         "Jellyfin acceleration decision does not match the evidence")
    return json.loads(canonical(value))


def assess_backends(value: dict) -> dict:
    ffmpeg = value.get("ffmpeg") or {}
    adapters = value.get("adapters") or []
    host = value.get("host_platform")
    intel = [item for item in adapters if item.get("vendor") == "intel"]
    nvidia = [item for item in adapters if item.get("vendor") == "nvidia"]

    qsv_reasons = []
    if host != "windows":
        qsv_reasons.append("native-windows-proof-required")
    if not ffmpeg.get("available"):
        qsv_reasons.append("ffmpeg-unavailable")
    if not ffmpeg.get("jellyfin_build"):
        qsv_reasons.append("jellyfin-ffmpeg-build-unverified")
    if not ffmpeg.get("libx264"):
        qsv_reasons.append("cpu-baseline-encoder-unavailable")
    if not ffmpeg.get("qsv"):
        qsv_reasons.append("qsv-codec-support-unavailable")
    if not intel:
        qsv_reasons.append("intel-adapter-unavailable")

    nvenc_reasons = []
    if host != "windows":
        nvenc_reasons.append("native-windows-proof-required")
    if not ffmpeg.get("available"):
        nvenc_reasons.append("ffmpeg-unavailable")
    if not ffmpeg.get("nvenc"):
        nvenc_reasons.append("nvenc-codec-support-unavailable")
    if not nvidia:
        nvenc_reasons.append("nvidia-adapter-unavailable")
    for adapter in nvidia:
        version = _version_number(adapter.get("driver"))
        if version is None:
            nvenc_reasons.append("nvidia-driver-unverified")
        elif version < NVIDIA_MIN_WINDOWS_DRIVER:
            nvenc_reasons.append("nvidia-driver-below-522.25")

    qsv_reasons = sorted(set(qsv_reasons))
    nvenc_reasons = sorted(set(nvenc_reasons))
    return {
        "selected": "cpu",
        "gpu_enabled": False,
        "fallback": "cpu",
        "synthetic_proof_required": True,
        "qsv": {
            "status": "eligible-for-synthetic-test" if not qsv_reasons else "blocked",
            "blocking_reasons": qsv_reasons,
        },
        "nvenc": {
            "status": "eligible-for-synthetic-test" if not nvenc_reasons else "blocked",
            "minimum_windows_driver": NVIDIA_MIN_WINDOWS_DRIVER,
            "blocking_reasons": nvenc_reasons,
        },
    }


def _validate_run(item: object, fixture: dict) -> dict:
    keys(item, {"role", "backend", "codec", "status", "concurrency",
                "elapsed_seconds", "speed", "metrics", "output"},
         "Jellyfin acceleration run")
    need(item["role"] in (*REQUIRED_ROLES, "qsv-hevc"),
         "Unknown Jellyfin acceleration run role")
    expected_backend = "cpu" if item["role"] == "cpu-baseline" else "qsv"
    need(item["backend"] == expected_backend and item["status"] == "passed",
         "Every required synthetic transcode must pass")
    expected_codec = "hevc" if item["role"] == "qsv-hevc" else "h264"
    need(item["codec"] == expected_codec,
         "Synthetic transcode codec does not match its role")
    expected_concurrency = 2 if item["role"].startswith("qsv-concurrent-") else 1
    need(item["concurrency"] == expected_concurrency,
         "Synthetic transcode concurrency does not match its role")
    for field in ("elapsed_seconds", "speed"):
        need(type(item[field]) in (int, float)
             and not isinstance(item[field], bool) and 0 < item[field] < 3600,
             "Invalid synthetic transcode performance measurement")
    keys(item["metrics"], {"user_seconds", "system_seconds", "max_rss_kib"},
         "synthetic transcode metrics")
    for field in ("user_seconds", "system_seconds"):
        need(item["metrics"][field] is None or
             (type(item["metrics"][field]) in (int, float)
              and not isinstance(item["metrics"][field], bool)
              and item["metrics"][field] >= 0),
             "Invalid process timing metric")
    need(item["metrics"]["max_rss_kib"] is None or
         (type(item["metrics"]["max_rss_kib"]) is int
          and item["metrics"]["max_rss_kib"] >= 0),
         "Invalid process memory metric")
    output = item["output"]
    keys(output, {"duration_seconds", "width", "height", "frames",
                  "size_bytes", "sha256", "ssim"},
         "synthetic transcode output")
    need(type(output["duration_seconds"]) in (int, float)
         and not isinstance(output["duration_seconds"], bool)
         and abs(output["duration_seconds"] - fixture["duration_seconds"]) <= 0.35,
         "Synthetic transcode duration validation failed")
    need(output["width"] == 1280 and output["height"] == 720,
         "Synthetic transcode dimensions validation failed")
    expected_frames = fixture["duration_seconds"] * fixture["fps"]
    need(type(output["frames"]) is int and abs(output["frames"] - expected_frames) <= 2,
         "Synthetic transcode frame-count validation failed")
    need(type(output["size_bytes"]) is int and output["size_bytes"] > 1024,
         "Synthetic transcode output is unexpectedly small")
    need(isinstance(output["sha256"], str)
         and bool(re.fullmatch(r"[0-9a-f]{64}", output["sha256"])),
         "Synthetic transcode hash is invalid")
    need(type(output["ssim"]) in (int, float)
         and not isinstance(output["ssim"], bool)
         and 0.85 <= output["ssim"] <= 1.0,
         "Synthetic transcode quality validation failed")
    return json.loads(canonical(item))


def validate_proof(value: object) -> dict:
    """Validate a complete proof and return a canonical, fail-closed record."""
    keys(value, {"kind", "contract", "fixture", "audit_fingerprint", "runs",
                 "decision", "production_media_used", "jellyfin_configuration_changed",
                 "temporary_outputs_removed"}, "Jellyfin acceleration proof")
    need(value["kind"] == PROOF_KIND and value["contract"] == CONTRACT,
         "Jellyfin acceleration proof contract mismatch")
    fixture = value["fixture"]
    keys(fixture, {"synthetic", "duration_seconds", "width", "height", "fps",
                   "source_codec"}, "synthetic fixture")
    need(fixture["synthetic"] is True and fixture["source_codec"] == "h264"
         and fixture["width"] == 1920 and fixture["height"] == 1080
         and type(fixture["duration_seconds"]) is int
         and 10 <= fixture["duration_seconds"] <= 20
         and fixture["fps"] in (24, 25, 30),
         "Jellyfin acceleration proof requires a bounded synthetic 1080p fixture")
    need(isinstance(value["audit_fingerprint"], str)
         and bool(re.fullmatch(r"[0-9a-f]{64}", value["audit_fingerprint"])),
         "Invalid Jellyfin acceleration audit fingerprint")
    need(isinstance(value["runs"], list) and 4 <= len(value["runs"]) <= 5,
         "Jellyfin acceleration proof requires CPU, single-QSV and dual-QSV runs")
    roles = [item.get("role") if isinstance(item, dict) else None for item in value["runs"]]
    need(len(roles) == len(set(roles)) and set(REQUIRED_ROLES) <= set(roles),
         "Jellyfin acceleration proof is missing a required run")
    normalized = [_validate_run(item, fixture) for item in value["runs"]]
    by_role = {item["role"]: item for item in normalized}
    need(by_role["qsv-single"]["speed"] >= 1.0
         and by_role["qsv-concurrent-a"]["speed"] >= 1.0
         and by_role["qsv-concurrent-b"]["speed"] >= 1.0,
         "QSV proof did not maintain real-time throughput")
    keys(value["decision"], {"selected", "gpu_enabled", "fallback",
                             "activation_scope", "nvenc"},
         "Jellyfin acceleration proof decision")
    need(value["decision"] == {
        "selected": "qsv",
        "gpu_enabled": True,
        "fallback": "cpu",
        "activation_scope": "jellyfin-native-transcode-only",
        "nvenc": "blocked-or-not-selected",
    }, "Jellyfin acceleration proof decision must retain CPU fallback")
    need(value["production_media_used"] is False
         and value["jellyfin_configuration_changed"] is False
         and value["temporary_outputs_removed"] is True,
         "Jellyfin acceleration proof crossed its non-production boundary")
    result = json.loads(canonical(value))
    result["runs"] = normalized
    return result


def make_proof(audit_value: dict, fixture: dict, runs: list[dict], *,
               temporary_outputs_removed: bool) -> dict:
    audit_value = validate_audit(audit_value)
    need(audit_value["decision"]["qsv"]["status"] ==
         "eligible-for-synthetic-test", "QSV capability is not eligible for a proof")
    value = {
        "kind": PROOF_KIND,
        "contract": CONTRACT,
        "fixture": fixture,
        "audit_fingerprint": digest(audit_value),
        "runs": runs,
        "decision": {
            "selected": "qsv",
            "gpu_enabled": True,
            "fallback": "cpu",
            "activation_scope": "jellyfin-native-transcode-only",
            "nvenc": "blocked-or-not-selected",
        },
        "production_media_used": False,
        "jellyfin_configuration_changed": False,
        "temporary_outputs_removed": temporary_outputs_removed,
    }
    return validate_proof(value)
