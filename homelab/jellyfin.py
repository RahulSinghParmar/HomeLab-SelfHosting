"""Jellyfin deployment selection and non-activating adoption planning."""
from __future__ import annotations

import json
import platform
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .sandbox import digest


CONTRACT = "jellyfin-explicit-deployment-v1"
MODULE = ROOT / "modules/jellyfin"
DEPLOYMENTS = ("native", "container")
LIMITS = {"memory_mib": 2048, "cpus": 2.0, "pids": 512}
PLATFORM_SUPPORT = {
    "windows": {"native": True, "container": False},
    "darwin": {"native": True, "container": False},
    "linux": {"native": True, "container": True},
}


def image() -> str:
    value = load_json(MODULE / "image.json")
    keys(value, {"server"}, "Jellyfin image manifest")
    reference = value["server"]
    need(isinstance(reference, str)
         and re.fullmatch(r"[^@\s]+:12\.4@sha256:[0-9a-f]{64}", reference),
         "Jellyfin image must be the reviewed immutable 12.4 reference")
    return reference


def _command(arguments: list[str]) -> tuple[int, str]:
    try:
        process = subprocess.run(arguments, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=15,
                                 check=False)
        return process.returncode, process.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def _public_info(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            value = json.loads(response.read().decode("utf-8"))
        return {
            "reachable": True,
            "version": value.get("Version"),
            "startup_complete": value.get("StartupWizardCompleted") is True,
        }
    except (OSError, ValueError, urllib.error.URLError):
        return {"reachable": False, "version": None, "startup_complete": None}


def _windows_native(runner) -> dict:
    query_code, query = runner(["sc.exe", "query", "JellyfinServer"])
    config_code, config = runner(["sc.exe", "qc", "JellyfinServer"])
    present = query_code == 0 or config_code == 0
    return {
        "present": present,
        "running": present and bool(re.search(r"STATE\s*:\s*4\s+RUNNING", query,
                                               re.IGNORECASE)),
        "autostart": present and bool(re.search(
            r"START_TYPE\s*:\s*2\s+AUTO_START", config, re.IGNORECASE)),
        "manager": "windows-service",
        "service": "JellyfinServer" if present else None,
    }


def _linux_native(runner) -> dict:
    active_code, active = runner(["systemctl", "is-active", "jellyfin"])
    enabled_code, enabled = runner(["systemctl", "is-enabled", "jellyfin"])
    present = active_code in (0, 3) or enabled_code in (0, 1)
    return {
        "present": present,
        "running": active_code == 0 and active.strip() == "active",
        "autostart": enabled_code == 0 and enabled.strip() == "enabled",
        "manager": "systemd",
        "service": "jellyfin" if present else None,
    }


def _darwin_native(runner) -> dict:
    code, output = runner(["pgrep", "-x", "jellyfin"])
    running = code == 0 and bool(output.strip())
    return {"present": running, "running": running, "autostart": None,
            "manager": "macos-application", "service": None}


def _container(runner) -> dict:
    version_code, version_text = runner(
        ["docker", "version", "--format", "{{json .Server}}"])
    list_code, rows_text = runner([
        "docker", "ps", "-a", "--filter", "name=jellyfin",
        "--format", "{{json .}}",
    ])
    engine_os = None
    if version_code == 0:
        try:
            engine_os = json.loads(version_text).get("Os")
        except (AttributeError, json.JSONDecodeError):
            pass
    rows = []
    if list_code == 0:
        for line in rows_text.splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            image_name = str(row.get("Image", "")).casefold()
            container_name = str(row.get("Names", "")).casefold()
            if "jellyfin" in image_name or "jellyfin" in container_name:
                rows.append({"running": str(row.get("State", "")).casefold() == "running"})
    return {
        "present": bool(rows),
        "running": any(row["running"] for row in rows),
        "engine_available": version_code == 0 and engine_os is not None,
        "engine_os": engine_os,
        "matching_containers": len(rows),
    }


def audit(runner=None, info_reader=None, system: str | None = None,
          port: int = 8096) -> dict:
    """Return a privacy-bounded, read-only Jellyfin deployment audit."""
    need(type(port) is int and 1024 <= port <= 65535,
         "Choose an unprivileged Jellyfin port")
    run = runner or _command
    host = (system or platform.system()).casefold()
    need(host in PLATFORM_SUPPORT, "Unsupported Jellyfin host platform")
    if host == "windows":
        native = _windows_native(run)
    elif host == "linux":
        native = _linux_native(run)
    else:
        native = _darwin_native(run)
    container = _container(run)
    info = (info_reader or _public_info)(
        f"http://127.0.0.1:{port}/System/Info/Public")
    active = [name for name, value in (("native", native), ("container", container))
              if value["present"]]
    detected = active[0] if len(active) == 1 else ("none" if not active else "conflict")
    return {
        "kind": "homelab-jellyfin-audit",
        "contract": CONTRACT,
        "host_platform": host,
        "native": native,
        "container": container,
        "public_api": info,
        "detected_deployment": detected,
        "mutations_performed": False,
        "production_media_read": False,
        "credentials_read": False,
    }


def validate_audit(value: object) -> dict:
    keys(value, {"kind", "contract", "host_platform", "native", "container",
                 "public_api", "detected_deployment", "mutations_performed",
                 "production_media_read", "credentials_read"}, "Jellyfin audit")
    need(value["kind"] == "homelab-jellyfin-audit"
         and value["contract"] == CONTRACT,
         "Jellyfin audit contract mismatch")
    need(value["host_platform"] in PLATFORM_SUPPORT,
         "Unsupported Jellyfin audit platform")
    need(value["detected_deployment"] in (*DEPLOYMENTS, "none", "conflict"),
         "Invalid Jellyfin deployment result")
    need(value["mutations_performed"] is False
         and value["production_media_read"] is False
         and value["credentials_read"] is False,
         "Jellyfin audit crossed its read-only boundary")
    return json.loads(canonical(value))


def make_plan(deployment: str, capability_audit: dict, port: int = 18096) -> dict:
    audit_value = validate_audit(capability_audit)
    need(deployment in DEPLOYMENTS,
         "Choose Jellyfin deployment explicitly: native or container")
    need(type(port) is int and 1024 <= port <= 65535,
         "Choose an unprivileged Jellyfin port")
    host = audit_value["host_platform"]
    need(PLATFORM_SUPPORT[host][deployment],
         f"Jellyfin {deployment} deployment is unsupported on {host}")
    detected = audit_value["detected_deployment"]
    need(detected != "conflict",
         "Both native and container Jellyfin were detected; resolve ownership first")
    need(detected in ("none", deployment),
         "Changing Jellyfin deployment type requires a separately reviewed migration")
    if deployment == "container":
        docker = audit_value["container"]
        need(docker["engine_available"] and docker["engine_os"] == "linux",
             "Container selection requires an available Linux container engine")
    plan = {
        "kind": "homelab-jellyfin-plan",
        "contract": CONTRACT,
        "execution": "disabled-review-only",
        "selected_deployment": deployment,
        "host_platform": host,
        "detected_deployment": detected,
        "adoption": "existing" if detected == deployment else "new",
        "port": port,
        "access": "loopback",
        "container_image": image() if deployment == "container" else None,
        "limits": LIMITS if deployment == "container" else None,
        "media": {"originals": "external-owner-managed",
                  "container_default": "read-only",
                  "automatic_scan": False},
        "backup": {
            "method": "jellyfin-built-in-archive",
            "application_consistent": True,
            "same_version_restore_required": True,
            "material": ["database", "configuration", "metadata", "subtitles",
                         "trickplay", "plugins", "media-path-mappings"],
            "media_originals_included": False,
        },
        "acceleration": {
            "selected": "cpu",
            "gpu_enabled": False,
            "device_access": False,
            "enablement": "codec-capability-and-synthetic-transcode-required",
        },
        "heavy_jobs": {"library_scan": "manual", "transcoding": "manual-test-only"},
        "dlna": "disabled-in-container-bridge" if deployment == "container"
                else "owner-configured-native",
        "deployment_performed": False,
        "production_media_used": False,
    }
    plan["plan_id"] = digest(plan)
    return plan


def validate_plan(value: object) -> dict:
    keys(value, {"kind", "contract", "execution", "selected_deployment",
                 "host_platform", "detected_deployment", "adoption", "port",
                 "access", "container_image", "limits", "media", "backup",
                 "acceleration", "heavy_jobs", "dlna", "deployment_performed",
                 "production_media_used", "plan_id"}, "Jellyfin plan")
    need(value["kind"] == "homelab-jellyfin-plan" and value["contract"] == CONTRACT,
         "Unsupported Jellyfin plan")
    deployment = value["selected_deployment"]
    host = value["host_platform"]
    need(deployment in DEPLOYMENTS and host in PLATFORM_SUPPORT
         and PLATFORM_SUPPORT[host][deployment],
         "Unsupported Jellyfin plan platform or deployment")
    need(value["detected_deployment"] in ("none", deployment)
         and value["adoption"] == (
             "existing" if value["detected_deployment"] == deployment else "new"),
         "Jellyfin plan ownership changed")
    need(type(value["port"]) is int and 1024 <= value["port"] <= 65535
         and value["access"] == "loopback",
         "Jellyfin plan access changed")
    need(value["container_image"] == (image() if deployment == "container" else None)
         and value["limits"] == (LIMITS if deployment == "container" else None),
         "Jellyfin image or resource policy changed")
    need(value["media"] == {
        "originals": "external-owner-managed",
        "container_default": "read-only", "automatic_scan": False,
    }, "Jellyfin media policy changed")
    need(value["backup"] == {
        "method": "jellyfin-built-in-archive", "application_consistent": True,
        "same_version_restore_required": True,
        "material": ["database", "configuration", "metadata", "subtitles",
                     "trickplay", "plugins", "media-path-mappings"],
        "media_originals_included": False,
    }, "Jellyfin recovery policy changed")
    need(value["execution"] == "disabled-review-only"
         and value["deployment_performed"] is False
         and value["production_media_used"] is False,
         "Jellyfin selection plan must remain non-activating")
    need(value["acceleration"] == {
        "selected": "cpu", "gpu_enabled": False, "device_access": False,
        "enablement": "codec-capability-and-synthetic-transcode-required",
    }, "Jellyfin acceleration gate changed")
    need(value["heavy_jobs"] == {
        "library_scan": "manual", "transcoding": "manual-test-only"},
        "Jellyfin heavy-job policy changed")
    need(value["dlna"] == ("disabled-in-container-bridge"
                           if deployment == "container"
                           else "owner-configured-native"),
         "Jellyfin DLNA boundary changed")
    need(digest({key: item for key, item in value.items() if key != "plan_id"})
         == value["plan_id"], "Jellyfin plan changed after review")
    return json.loads(canonical(value))


def validate_media(value: object) -> list[dict]:
    keys(value, {"kind", "contract", "mounts"}, "Jellyfin media map")
    need(value["kind"] == "homelab-jellyfin-media-map"
         and value["contract"] == CONTRACT,
         "Unsupported Jellyfin media map")
    need(isinstance(value["mounts"], list) and value["mounts"],
         "At least one Jellyfin media mount is required")
    result = []
    targets = set()
    for item in value["mounts"]:
        keys(item, {"source", "target", "read_only"}, "Jellyfin media mount")
        source = PurePosixPath(str(item["source"]))
        target = item["target"]
        need(source.is_absolute(), "Jellyfin media source must be absolute")
        need(isinstance(target, str) and re.fullmatch(r"/media/[a-z0-9][a-z0-9_-]*", target),
             "Jellyfin media target must be a unique /media/name path")
        need(item["read_only"] is True, "Jellyfin media mounts must be read-only")
        need(target not in targets, "Duplicate Jellyfin media target")
        targets.add(target)
        result.append({"source": str(source), "target": target, "read_only": True})
    return result


def compose(plan: dict, root: str | Path, media_map: dict, uid: int, gid: int) -> dict:
    plan = validate_plan(plan)
    need(plan["selected_deployment"] == "container",
         "Compose is available only for an explicit container plan")
    need(plan["host_platform"] == "linux",
         "Jellyfin containers are supported only on Linux by this module")
    need(type(uid) is int and uid >= 1 and type(gid) is int and gid >= 1,
         "Choose non-root numeric Jellyfin uid and gid")
    root = PurePosixPath(str(root))
    need(root.is_absolute(), "Jellyfin container root must be absolute")
    mounts = validate_media(media_map)
    volumes = [
        {"type": "bind", "source": str(root / "config"), "target": "/config"},
        {"type": "bind", "source": str(root / "cache"), "target": "/cache"},
        *({"type": "bind", **item} for item in mounts),
    ]
    service = {
        "image": plan["container_image"],
        "pull_policy": "never",
        "restart": "unless-stopped",
        "user": f"{uid}:{gid}",
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "pids_limit": plan["limits"]["pids"],
        "mem_limit": f'{plan["limits"]["memory_mib"]}m',
        "memswap_limit": f'{plan["limits"]["memory_mib"]}m',
        "cpus": plan["limits"]["cpus"],
        "ports": [{"target": 8096, "published": str(plan["port"]),
                   "host_ip": "127.0.0.1", "protocol": "tcp"}],
        "volumes": volumes,
        "tmpfs": ["/tmp:rw,noexec,nosuid,size=128m,mode=0700"],
        "labels": {"org.homelab.module": "jellyfin",
                   "org.homelab.plan": plan["plan_id"]},
        "networks": ["frontend"],
    }
    return {"name": "homelab-jellyfin", "services": {"jellyfin": service},
            "networks": {"frontend": {"driver": "bridge"}}}
