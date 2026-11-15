"""Opt-in, credential-free media-management planning and recovery evidence."""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

from .config import ROOT, canonical, keys, load_json, logical_path, need
from .sandbox import digest


CONTRACT = "phase6-media-management-v1"
MODULE = ROOT / "modules/media-management"
IMAGES = MODULE / "images.json"
SELECTION = MODULE / "selection.example.json"

COMPONENTS = (
    "bazarr", "flaresolverr", "lidarr", "prowlarr",
    "qbittorrent", "radarr", "seerr", "sonarr",
)
PUBLISHED = {
    "bazarr": 6767,
    "lidarr": 8686,
    "prowlarr": 9696,
    "qbittorrent": 8080,
    "radarr": 7878,
    "seerr": 5055,
    "sonarr": 8989,
}
CONFIG_TARGETS = {
    "bazarr": "/config",
    "lidarr": "/config",
    "prowlarr": "/config",
    "qbittorrent": "/config",
    "radarr": "/config",
    "seerr": "/app/config",
    "sonarr": "/config",
}
DATA_COMPONENTS = frozenset({"bazarr", "lidarr", "qbittorrent", "radarr", "sonarr"})
ALL_OF = {"flaresolverr": frozenset({"prowlarr"})}
ONE_OF = {
    "bazarr": frozenset({"radarr", "sonarr"}),
    "prowlarr": frozenset({"lidarr", "radarr", "sonarr"}),
}
LIMITS = {
    "bazarr": {"memory_mib": 512, "cpus": 1.0, "pids": 256},
    "flaresolverr": {"memory_mib": 768, "cpus": 1.0, "pids": 256},
    "lidarr": {"memory_mib": 512, "cpus": 1.0, "pids": 256},
    "prowlarr": {"memory_mib": 512, "cpus": 1.0, "pids": 256},
    "qbittorrent": {"memory_mib": 512, "cpus": 1.0, "pids": 256},
    "radarr": {"memory_mib": 768, "cpus": 1.5, "pids": 256},
    "seerr": {"memory_mib": 512, "cpus": 1.0, "pids": 256},
    "sonarr": {"memory_mib": 512, "cpus": 1.0, "pids": 256},
}
AUTOMATIC_ACTIONS = {
    "automatic_search": False,
    "downloads": False,
    "real_library_scan": False,
    "rss": False,
}


def _platform_path(root: str, name: str, system: str) -> str:
    path_type = PureWindowsPath if system == "windows" else PurePosixPath
    return str(path_type(root) / name)


def validate_images(value: object) -> dict:
    keys(value, {"kind", "contract", "components"}, "media-management images")
    need(value["kind"] == "homelab-media-management-images"
         and value["contract"] == CONTRACT,
         "Unsupported media-management image manifest")
    keys(value["components"], set(COMPONENTS), "media-management image components")
    for name, item in value["components"].items():
        keys(item, {"image", "version"}, f"{name} image")
        need(isinstance(item["version"], str) and bool(item["version"]),
             "Media-management image version required")
        need(isinstance(item["image"], str)
             and re.fullmatch(r"[a-z0-9./_-]+@sha256:[0-9a-f]{64}", item["image"]) is not None,
             "Media-management images must be immutable SHA-256 digest references")
    return json.loads(canonical(value))


def load_images(path: Path = IMAGES) -> dict:
    return validate_images(load_json(path))


def validate_selection(value: object, *, require_selected: bool = True) -> dict:
    keys(value, {"kind", "contract", "target_platform", "selected", "config_root",
                 "data_root", "timezone", "uid", "gid", "ports",
                 "automatic_actions"}, "media-management selection")
    need(value["kind"] == "homelab-media-management-selection"
         and value["contract"] == CONTRACT,
         "Unsupported media-management selection")
    system = value["target_platform"]
    need(system in ("windows", "linux", "macos"), "Unsupported media-management target platform")
    selected = value["selected"]
    need(isinstance(selected, list) and all(isinstance(item, str) for item in selected),
         "Media-management selection must be a list")
    need(len(selected) == len(set(selected)) and set(selected) <= set(COMPONENTS),
         "Media-management selection contains duplicates or unknown components")
    need(bool(selected) or not require_selected,
         "Select at least one media-management component explicitly")
    active = set(selected)
    for name in selected:
        required = ALL_OF.get(name, frozenset())
        need(required <= active,
             f"{name} requires explicit selection of: {', '.join(sorted(required))}")
        alternatives = ONE_OF.get(name)
        need(alternatives is None or bool(alternatives & active),
             f"{name} requires at least one explicitly selected library manager")
    config_root = logical_path(value["config_root"], system)
    data_root = logical_path(value["data_root"], system)
    need(not config_root.is_relative_to(data_root) and not data_root.is_relative_to(config_root),
         "Media-management configuration and data roots must not overlap")
    need(isinstance(value["timezone"], str)
         and re.fullmatch(r"[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)*", value["timezone"]),
         "Invalid media-management timezone")
    for field in ("uid", "gid"):
        need(type(value[field]) is int and 1 <= value[field] <= 65535,
             f"Invalid media-management {field}")
    keys(value["ports"], set(PUBLISHED), "media-management loopback ports")
    ports = list(value["ports"].values())
    need(all(type(port) is int and 1024 <= port <= 65535 for port in ports)
         and len(ports) == len(set(ports)),
         "Media-management loopback ports must be unique and unprivileged")
    keys(value["automatic_actions"], set(AUTOMATIC_ACTIONS),
         "media-management automatic actions")
    need(value["automatic_actions"] == AUTOMATIC_ACTIONS,
         "Reusable media-management automation must remain disabled")
    result = json.loads(canonical(value))
    result["selected"] = sorted(selected)
    result["config_root"] = str(config_root)
    result["data_root"] = str(data_root)
    return result


def load_selection(path: Path = SELECTION, *, require_selected: bool = True) -> dict:
    return validate_selection(load_json(path), require_selected=require_selected)


def make_plan(selection: dict, images: dict | None = None) -> dict:
    selection = validate_selection(selection)
    images = validate_images(images if images is not None else load_images())
    selected = selection["selected"]
    plan = {
        "kind": "homelab-media-management-plan",
        "contract": CONTRACT,
        "target_platform": selection["target_platform"],
        "selected": selected,
        "images": {name: images["components"][name] for name in selected},
        "roots": {"config": selection["config_root"], "data": selection["data_root"]},
        "identity": {"uid": selection["uid"], "gid": selection["gid"]},
        "timezone": selection["timezone"],
        "ports": {name: selection["ports"][name] for name in selected if name in PUBLISHED},
        "limits": {name: LIMITS[name] for name in selected},
        "access": {
            "ui": "loopback-only",
            "flaresolverr": "internal-only",
            "torrent_peer_ports": "not-published",
        },
        "automation": dict(AUTOMATIC_ACTIONS),
        "credentials": "operator-supplied-after-deployment",
        "shared_data": sorted(DATA_COMPONENTS & set(selected)),
        "production_state_adopted": False,
    }
    plan["plan_id"] = digest(plan)
    return plan


def validate_plan(plan: object) -> dict:
    keys(plan, {"kind", "contract", "target_platform", "selected", "images", "roots",
                "identity", "timezone", "ports", "limits", "access", "automation",
                "credentials", "shared_data", "production_state_adopted", "plan_id"},
         "media-management plan")
    selection = {
        "kind": "homelab-media-management-selection",
        "contract": CONTRACT,
        "target_platform": plan["target_platform"],
        "selected": plan["selected"],
        "config_root": plan["roots"]["config"],
        "data_root": plan["roots"]["data"],
        "timezone": plan["timezone"],
        "uid": plan["identity"]["uid"],
        "gid": plan["identity"]["gid"],
        "ports": {**{name: 10000 + index for index, name in enumerate(PUBLISHED)},
                  **plan["ports"]},
        "automatic_actions": plan["automation"],
    }
    # Preserve unselected port values only for validation; selected values are authoritative.
    used = set(plan["ports"].values())
    next_port = 30000
    for name in PUBLISHED:
        if name in plan["ports"]:
            selection["ports"][name] = plan["ports"][name]
            continue
        while next_port in used:
            next_port += 1
        selection["ports"][name] = next_port
        used.add(next_port)
        next_port += 1
    expected = make_plan(validate_selection(selection), load_images())
    need(canonical(plan) == canonical(expected),
         "Media-management plan or immutable image set changed; review a new plan")
    return plan


def _environment(name: str, plan: dict) -> dict[str, str]:
    common = {"TZ": plan["timezone"]}
    if name in {"bazarr", "lidarr", "prowlarr", "qbittorrent", "radarr", "sonarr"}:
        common.update({"PUID": str(plan["identity"]["uid"]),
                       "PGID": str(plan["identity"]["gid"]), "UMASK": "027"})
    if name == "qbittorrent":
        common.update({"WEBUI_PORT": "8080", "TORRENTING_PORT": "6881"})
    elif name == "seerr":
        common.update({"HOST": "0.0.0.0", "PORT": "5055", "LOG_LEVEL": "info"})
    elif name == "flaresolverr":
        common.update({"LOG_LEVEL": "info", "LOG_HTML": "false",
                       "CAPTCHA_SOLVER": "none"})
    return common


def _healthcheck(name: str) -> dict:
    port = 8191 if name == "flaresolverr" else PUBLISHED[name]
    route = {
        "bazarr": "/",
        "flaresolverr": "/health",
        "lidarr": "/ping",
        "prowlarr": "/ping",
        "qbittorrent": "/",
        "radarr": "/ping",
        "seerr": "/api/v1/status",
        "sonarr": "/ping",
    }[name]
    # These reviewed images include wget or curl. No credential is embedded.
    command = (f"wget -q --spider http://127.0.0.1:{port}{route}"
               if name == "seerr" else
               f"curl -fsS --max-time 5 http://127.0.0.1:{port}{route} >/dev/null")
    return {"test": ["CMD-SHELL", command], "interval": "30s", "timeout": "10s",
            "start_period": "120s", "retries": 5}


def compose(plan: dict, *, trial_internal_network: bool = False) -> dict:
    validate_plan(plan)
    services = {}
    active = set(plan["selected"])
    for name in plan["selected"]:
        limits = plan["limits"][name]
        service = {
            "image": plan["images"][name]["image"],
            "pull_policy": "never",
            "restart": "unless-stopped",
            "security_opt": ["no-new-privileges:true"],
            "pids_limit": limits["pids"],
            "mem_limit": f"{limits['memory_mib']}m",
            "cpus": limits["cpus"],
            "environment": _environment(name, plan),
            "healthcheck": _healthcheck(name),
            "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "2"}},
            "labels": {"org.homelab.contract": CONTRACT,
                       "org.homelab.plan": plan["plan_id"],
                       "org.homelab.component": name},
            "networks": ["media-management"],
        }
        volumes = []
        if name in CONFIG_TARGETS:
            volumes.append({"type": "bind",
                            "source": _platform_path(plan["roots"]["config"], name,
                                                     plan["target_platform"]),
                            "target": CONFIG_TARGETS[name],
                            "bind": {"create_host_path": False}})
        if name in DATA_COMPONENTS:
            volumes.append({"type": "bind", "source": plan["roots"]["data"],
                            "target": "/data", "bind": {"create_host_path": False}})
        if volumes:
            service["volumes"] = volumes
        if name in PUBLISHED:
            service["ports"] = [{"target": PUBLISHED[name],
                                 "published": str(plan["ports"][name]),
                                 "host_ip": "127.0.0.1", "protocol": "tcp"}]
        if name == "flaresolverr":
            service["tmpfs"] = ["/tmp:rw,noexec,nosuid,size=512m"]
        required = set(ALL_OF.get(name, ()))
        if name in ONE_OF:
            required |= ONE_OF[name] & active
        if required:
            service["depends_on"] = {
                dependency: {"condition": "service_healthy"}
                for dependency in sorted(required)
            }
        services[name] = service
    return {
        "name": "homelab-media-management-" + plan["plan_id"][:12],
        "services": services,
        "networks": {"media-management": {
            "driver": "bridge", "internal": bool(trial_internal_network),
            "labels": {"org.homelab.contract": CONTRACT,
                       "org.homelab.plan": plan["plan_id"]},
        }},
    }


def validate_recovery_evidence(value: object, plan: dict) -> dict:
    validate_plan(plan)
    keys(value, {"kind", "contract", "plan_id", "selected", "backup", "sqlite",
                 "shared_storage", "restore", "resources", "safety"},
         "media-management recovery evidence")
    need(value["kind"] == "homelab-media-management-recovery-evidence"
         and value["contract"] == CONTRACT and value["plan_id"] == plan["plan_id"],
         "Recovery evidence does not match the reviewed media-management plan")
    need(value["selected"] == plan["selected"], "Recovery component coverage changed")
    backup = value["backup"]
    keys(backup, {"services_stopped", "config_components", "manifest_sha256"},
         "media-management stopped backup")
    need(backup["services_stopped"] is True
         and backup["config_components"] == sorted(set(plan["selected"]) & set(CONFIG_TARGETS))
         and re.fullmatch(r"[0-9a-f]{64}", backup["manifest_sha256"] or "") is not None,
         "Recovery requires a stopped, integrity-manifested configuration backup")
    sqlite = value["sqlite"]
    keys(sqlite, {"checked", "all_ok"}, "media-management SQLite evidence")
    need(type(sqlite["checked"]) is int and sqlite["checked"] >= 0 and sqlite["all_ok"] is True,
         "SQLite integrity validation failed")
    shared = value["shared_storage"]
    keys(shared, {"applicable", "hardlink", "atomic_move", "content_restored"},
         "media-management shared-storage evidence")
    applicable = bool(plan["shared_data"])
    need(shared["applicable"] is applicable and shared["content_restored"] is True
         and (not applicable or (shared["hardlink"] is True and shared["atomic_move"] is True)),
         "Shared /data hardlink, atomic-move, or restore proof failed")
    restore = value["restore"]
    keys(restore, {"independent_root", "started", "healthy", "sentinel_match"},
         "media-management restore evidence")
    need(restore["independent_root"] is True
         and restore["started"] == plan["selected"]
         and restore["healthy"] == plan["selected"]
         and restore["sentinel_match"] is True,
         "Independent recovery did not restore every selected healthy component")
    resources = value["resources"]
    keys(resources, {"memory_mib", "peak_cpu_percent", "total_memory_mib"},
         "media-management resource evidence")
    keys(resources["memory_mib"], set(plan["selected"]), "component memory evidence")
    keys(resources["peak_cpu_percent"], set(plan["selected"]), "component CPU evidence")
    for name in plan["selected"]:
        need(type(resources["memory_mib"][name]) in (int, float)
             and not isinstance(resources["memory_mib"][name], bool)
             and 0 <= resources["memory_mib"][name] <= plan["limits"][name]["memory_mib"],
             "Measured media-management memory exceeds its reviewed ceiling")
        need(type(resources["peak_cpu_percent"][name]) in (int, float)
             and not isinstance(resources["peak_cpu_percent"][name], bool)
             and 0 <= resources["peak_cpu_percent"][name] <= 800,
             "Invalid media-management CPU measurement")
    need(type(resources["total_memory_mib"]) in (int, float)
         and abs(resources["total_memory_mib"] - sum(resources["memory_mib"].values())) < 0.01,
         "Media-management total-memory evidence is inconsistent")
    safety = value["safety"]
    keys(safety, {"production_paths_used", "production_credentials_used",
                  "external_requests_enabled", "automatic_actions_enabled", "cleanup_completed"},
         "media-management recovery safety evidence")
    need(safety == {"production_paths_used": False, "production_credentials_used": False,
                    "external_requests_enabled": False, "automatic_actions_enabled": False,
                    "cleanup_completed": True},
         "Recovery trial crossed a production, credential, network, automation, or cleanup boundary")
    return json.loads(canonical(value))
