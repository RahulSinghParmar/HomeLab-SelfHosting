"""Coolify-owned update discovery and Windows Docker Desktop compatibility checks."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path, PureWindowsPath
from typing import Any

from . import coolify_adapter
from .config import ROOT, canonical, keys, load_json, need
from .sandbox import digest


CONTRACT = "phase7-coolify-controller-v1"
MODULE = ROOT / "modules/coolify"
POLICY = MODULE / "controller.example.json"
TASKS = (
    "Coolify-Daily-Backup",
    "Coolify-Startup-Reconcile",
    "Coolify-Weekly-Optimize",
)
VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
IMAGE_TAG = re.compile(r"(?:^|/)[^/@]+:([^/@]+)$")
EXPECTED_SENTINEL_LIMITS = {
    "nano_cpus": 500_000_000,
    "memory_bytes": 256 * 1024 * 1024,
    "memory_swap_bytes": 512 * 1024 * 1024,
    "pids_limit": 128,
}


def validate_policy(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "root", "channel",
                 "versions_url", "upgrade_script_url", "api", "windows",
                 "updates"}, "Coolify controller policy")
    need(value["kind"] == "homelab-coolify-controller-policy"
         and value["contract"] == CONTRACT,
         "Unsupported Coolify controller policy")
    need(value["platform"] == "windows-docker-desktop-existing-instance",
         "Controller integration supports only the reviewed Windows instance")
    need(isinstance(value["root"], str)
         and bool(re.fullmatch(r"[A-Za-z]:\\[^\x00]+", value["root"])),
         "Coolify controller root must be an absolute Windows path")
    need(value["channel"] == "stable", "Only the Coolify stable channel is reviewed")
    need(value["versions_url"] == "https://cdn.coollabs.io/coolify/versions.json"
         and value["upgrade_script_url"] == "https://cdn.coollabs.io/coolify/upgrade.sh",
         "Coolify controller source URLs changed")

    api = value["api"]
    keys(api, {"base_url", "deployments_endpoint", "token_required_for_update"},
         "Coolify controller API")
    need(api == {
        "base_url": "http://127.0.0.1:8000/api/v1",
        "deployments_endpoint": "/deployments",
        "token_required_for_update": True,
    }, "Coolify controller API boundary changed")

    windows = value["windows"]
    keys(windows, {"docker_context", "server_os", "server_arch",
                   "wsl_distribution", "host_mount", "custom_compose",
                   "scheduled_tasks"}, "Coolify Windows policy")
    need(windows["docker_context"] == "desktop-linux"
         and windows["server_os"] == "linux"
         and windows["server_arch"] == "amd64"
         and windows["wsl_distribution"] == "docker-desktop"
         and windows["host_mount"] == "/mnt/host/c/Docker/coolify"
         and windows["custom_compose"] == "source\\docker-compose.custom.yml"
         and windows["scheduled_tasks"] == list(TASKS),
         "Coolify Windows compatibility boundary changed")

    updates = value["updates"]
    keys(updates, {"owner", "automatic", "generic_updater_allowed",
                   "fresh_backup_required", "active_deployments_required",
                   "off_host_restore_required", "reverb_review_required"},
         "Coolify controller update policy")
    need(updates == {
        "owner": "coolify-dashboard",
        "automatic": False,
        "generic_updater_allowed": False,
        "fresh_backup_required": True,
        "active_deployments_required": True,
        "off_host_restore_required": True,
        "reverb_review_required": True,
    }, "Coolify controller ownership or update gates changed")
    return json.loads(canonical(value))


def load_policy(path: Path = POLICY) -> dict:
    return validate_policy(load_json(path))


def _run(arguments: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            arguments, text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(arguments, 127, "", "unavailable")


def _output(arguments: list[str], *, timeout: int = 30) -> str | None:
    result = _run(arguments, timeout=timeout)
    if result.returncode:
        return None
    return result.stdout.strip()


def _read_url(url: str, *, headers: dict[str, str] | None = None,
              timeout: int = 20, maximum: int = 1_000_000) -> bytes:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        need(response.status == 200, "Coolify controller endpoint did not return HTTP 200")
        body = response.read(maximum + 1)
    need(len(body) <= maximum, "Coolify controller response is too large")
    return body


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = VERSION.fullmatch(value)
    need(match is not None, "Coolify version is not a reviewed semantic version")
    return tuple(int(part) for part in match.groups())


def _image_version(reference: str | None) -> str | None:
    if not reference or "@" in reference:
        return None
    match = IMAGE_TAG.search(reference)
    return match.group(1) if match else None


def normalize_versions(payload: object, channel: str = "stable") -> dict:
    need(isinstance(payload, dict), "Coolify versions response must be an object")
    selected = payload.get(channel)
    need(isinstance(selected, dict), "Coolify update channel is absent")
    coolify = selected.get("coolify")
    sentinel = selected.get("sentinel")
    helper = selected.get("helper")
    traefik = selected.get("traefik")
    need(all(isinstance(item, dict) for item in (coolify, sentinel, helper, traefik)),
         "Coolify versions response is incomplete")
    coolify_version = coolify.get("version")
    sentinel_version = sentinel.get("version")
    helper_version = helper.get("version")
    need(all(isinstance(item, str) for item in
             (coolify_version, sentinel_version, helper_version)),
         "Coolify versions response contains invalid component versions")
    _version_tuple(coolify_version)
    need(bool(re.fullmatch(r"\d+\.\d+\.\d+(?:[-+].*)?", sentinel_version))
         and bool(re.fullmatch(r"\d+\.\d+\.\d+(?:[-+].*)?", helper_version)),
         "Coolify component version is invalid")
    filtered_traefik = {}
    for major, version in traefik.items():
        need(isinstance(major, str) and bool(re.fullmatch(r"v\d+\.\d+", major))
             and isinstance(version, str)
             and bool(re.fullmatch(r"\d+\.\d+\.\d+", version)),
             "Coolify Traefik version map is invalid")
        filtered_traefik[major] = version
    return {
        "channel": channel,
        "coolify": coolify_version,
        "helper": helper_version,
        "sentinel": sentinel_version,
        "traefik": filtered_traefik,
    }


def fetch_versions(policy: dict) -> dict:
    try:
        body = _read_url(policy["versions_url"])
        value = json.loads(body)
        result = normalize_versions(value, policy["channel"])
        return {
            "status": "checked",
            "source": policy["versions_url"],
            "sha256": hashlib.sha256(body).hexdigest(),
            **result,
        }
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
        return {
            "status": "unavailable",
            "source": policy["versions_url"],
            "sha256": None,
            "channel": policy["channel"],
            "coolify": None,
            "helper": None,
            "sentinel": None,
            "traefik": {},
        }


def inspect_updater_shim(policy: dict) -> dict:
    root = Path(policy["root"])
    shim = root / "maintenance" / "curl-windows-updater"
    local_exists = shim.is_file() and not shim.is_symlink()
    local_text = ""
    if local_exists and shim.stat().st_size <= 100_000:
        local_text = shim.read_text(encoding="utf-8", errors="replace")
    local_markers = all(marker in local_text for marker in (
        "/mnt/host/c/Docker/coolify",
        "/data/coolify/source/upgrade.sh",
        "COOLIFY_DAEMON_ROOT",
    ))
    try:
        remote = _read_url(policy["upgrade_script_url"], maximum=200_000)
        text = remote.decode("utf-8")
        mount_anchor = text.count("-v /data/coolify/source:/data/coolify/source")
        completion_anchor = text.count("log 'Docker compose up completed'")
        return {
            "status": "checked",
            "local_exists": local_exists,
            "local_markers": local_markers,
            "remote_sha256": hashlib.sha256(remote).hexdigest(),
            "mount_anchor_count": mount_anchor,
            "completion_anchor_count": completion_anchor,
            "compatible": bool(local_exists and local_markers
                               and mount_anchor == 1 and completion_anchor == 1),
        }
    except (OSError, urllib.error.URLError, UnicodeError, ValueError):
        return {
            "status": "unavailable",
            "local_exists": local_exists,
            "local_markers": local_markers,
            "remote_sha256": None,
            "mount_anchor_count": None,
            "completion_anchor_count": None,
            "compatible": False,
        }


def inspect_custom_compose(policy: dict, installed: str | None,
                           target: str | None) -> dict:
    relative = Path(*PureWindowsPath(policy["windows"]["custom_compose"]).parts)
    path = Path(policy["root"]) / relative
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 1_000_000,
         "Coolify custom Compose file is unavailable or unsafe")
    body = path.read_bytes()
    text = body.decode("utf-8")
    legacy_override = bool(re.search(r"(?m)^\s{2}soketi:\s*(?:#.*)?$", text))
    coolify_match = re.search(
        r"(?ms)^\s{2}coolify:\s*(?:#.*)?$\n(?P<body>.*?)(?=^\s{2}[A-Za-z0-9_.-]+:\s*(?:#.*)?$|\Z)",
        text,
    )
    coolify_block = coolify_match.group("body") if coolify_match else ""
    ports_on_coolify = "6001" in coolify_block and "6002" in coolify_block
    crosses = False
    if installed and target:
        crosses = (_version_tuple(installed) < (4, 6, 0)
                   and _version_tuple(target) >= (4, 6, 0))
    return {
        "sha256": hashlib.sha256(body).hexdigest(),
        "legacy_soketi_override": legacy_override,
        "reverb_ports_on_coolify": ports_on_coolify,
        "crosses_reverb_boundary": crosses,
        "review_required": bool(crosses and legacy_override),
    }


def collect_host(policy: dict) -> dict:
    windows = policy["windows"]
    distribution = windows["wsl_distribution"]
    mount = windows["host_mount"]
    wsl = _run([
        "wsl.exe", "-d", distribution, "-e", "sh", "-lc",
        f"test -d {mount}",
    ])
    return {
        "host_os": platform.system().lower(),
        "docker_context": _output(["docker", "context", "show"]),
        "docker_server_version": _output([
            "docker", "version", "--format", "{{.Server.Version}}",
        ]),
        "docker_server_os": _output([
            "docker", "version", "--format", "{{.Server.Os}}",
        ]),
        "docker_server_arch": _output([
            "docker", "version", "--format", "{{.Server.Arch}}",
        ]),
        "compose_version": _output(["docker", "compose", "version", "--short"]),
        "wsl_distribution": distribution,
        "wsl_host_mount_accessible": wsl.returncode == 0,
        "root_exists": Path(policy["root"]).is_dir(),
    }


def collect_tasks(policy: dict) -> list[dict]:
    if os.name != "nt":
        return [{"name": name, "exists": False, "state": "unsupported",
                 "last_result": None, "action_matches": False}
                for name in policy["windows"]["scheduled_tasks"]]
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        return [{"name": name, "exists": False, "state": "unavailable",
                 "last_result": None, "action_matches": False}
                for name in policy["windows"]["scheduled_tasks"]]
    names = ",".join(f"'{name}'" for name in policy["windows"]["scheduled_tasks"])
    script = (
        f"$names=@({names});$rows=@(foreach($n in $names){{"
        "$t=Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue;"
        "if(-not $t){[pscustomobject]@{name=$n;exists=$false;state='missing';"
        "last_result=$null;action_matches=$false};continue};"
        "$i=Get-ScheduledTaskInfo -TaskName $n;"
        "$a=($t.Actions.Execute+' '+$t.Actions.Arguments);"
        "[pscustomobject]@{name=$n;exists=$true;state=[string]$t.State;"
        "last_result=[int64]$i.LastTaskResult;"
        "action_matches=($a -match 'C:\\\\Docker\\\\coolify\\\\maintenance')}});"
        "$rows|ConvertTo-Json -Compress"
    )
    result = _run([shell, "-NoProfile", "-Command", script])
    if result.returncode:
        return [{"name": name, "exists": False, "state": "unavailable",
                 "last_result": None, "action_matches": False}
                for name in policy["windows"]["scheduled_tasks"]]
    try:
        value = json.loads(result.stdout)
        rows = value if isinstance(value, list) else [value]
    except json.JSONDecodeError:
        rows = []
    by_name = {row.get("name"): row for row in rows if isinstance(row, dict)}
    return [by_name.get(name, {"name": name, "exists": False, "state": "unavailable",
                               "last_result": None, "action_matches": False})
            for name in policy["windows"]["scheduled_tasks"]]


def collect_sentinel_limits() -> dict:
    raw = _output(["docker", "inspect", "--format", "{{json .HostConfig}}",
                   "coolify-sentinel"])
    if not raw:
        return {"status": "unavailable", "expected": EXPECTED_SENTINEL_LIMITS,
                "actual": None, "compliant": False}
    try:
        host = json.loads(raw)
        actual = {
            "nano_cpus": int(host.get("NanoCpus") or 0),
            "memory_bytes": int(host.get("Memory") or 0),
            "memory_swap_bytes": int(host.get("MemorySwap") or 0),
            "pids_limit": int(host.get("PidsLimit") or 0),
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return {"status": "unavailable", "expected": EXPECTED_SENTINEL_LIMITS,
                "actual": None, "compliant": False}
    return {
        "status": "checked",
        "expected": EXPECTED_SENTINEL_LIMITS,
        "actual": actual,
        "compliant": actual == EXPECTED_SENTINEL_LIMITS,
    }


def inspect_api(policy: dict, token_file: Path | None = None) -> dict:
    if token_file is None:
        return {"configured": False, "status": "not-configured",
                "http_status": None, "active_deployments": None,
                "secret_persisted": False}
    need(token_file.is_file() and not token_file.is_symlink()
         and token_file.stat().st_size <= 8192,
         "Coolify API token file is unavailable or unsafe")
    token = token_file.read_text(encoding="utf-8").strip()
    need(bool(token) and "\n" not in token and "\r" not in token,
         "Coolify API token file must contain exactly one token")
    endpoint = policy["api"]["base_url"] + policy["api"]["deployments_endpoint"]
    request = urllib.request.Request(endpoint, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(1_000_001)
            status = response.status
        need(len(body) <= 1_000_000, "Coolify deployments response is too large")
        value = json.loads(body)
        need(isinstance(value, list), "Coolify deployments response must be a list")
        return {"configured": True, "status": "checked", "http_status": status,
                "active_deployments": len(value), "secret_persisted": False}
    except urllib.error.HTTPError as error:
        return {"configured": True, "status": "unavailable",
                "http_status": error.code, "active_deployments": None,
                "secret_persisted": False}
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
        return {"configured": True, "status": "unavailable",
                "http_status": None, "active_deployments": None,
                "secret_persisted": False}


def _local_image_version(image_id: str | None) -> str | None:
    if not image_id:
        return None
    raw = _output(["docker", "image", "inspect", "--format",
                   '{{index .Config.Labels "org.opencontainers.image.version"}}', image_id])
    return None if raw in (None, "", "<no value>") else raw.lstrip("v")


def build_audit(policy: dict, base: dict, versions: dict, host: dict,
                tasks: list[dict], migration: dict, updater_shim: dict,
                api: dict, sentinel_limits: dict,
                generated_at: str | None = None) -> dict:
    policy = validate_policy(policy)
    coolify_adapter.validate_audit(base)
    components = {row["name"]: row for row in base["components"]}
    installed_coolify = _image_version(components["coolify"]["image"])
    installed = {
        "coolify": installed_coolify,
        "realtime": _image_version(components["coolify-realtime"]["image"]),
        "sentinel": _image_version(components["coolify-sentinel"]["image"]),
        "traefik": _local_image_version(components["coolify-proxy"]["image_id"]),
        "legacy_realtime_container": components["coolify-realtime"]["exists"],
    }
    result = {
        "kind": "homelab-coolify-controller-audit",
        "contract": CONTRACT,
        "platform": policy["platform"],
        "support": "experimental-existing-instance-only",
        "generated_at": generated_at or dt.datetime.now(dt.timezone.utc).isoformat(),
        "base_audit_id": base["audit_id"],
        "base_health_ready": (
            all(row["exists"] and row["health"] in ("healthy", "running")
                for row in base["components"])
            and all(base["checks"].values())
        ),
        "local_backup_ready": (
            base["backup"]["fresh"] and base["backup"]["database_dump"]
            and base["backup"]["manifest"]
        ),
        "installed": installed,
        "available": versions,
        "host": host,
        "scheduled_tasks": tasks,
        "migration": migration,
        "updater_shim": updater_shim,
        "controller_api": api,
        "sentinel_limits": sentinel_limits,
        "ownership": {
            "controller": "coolify",
            "update_owner": policy["updates"]["owner"],
            "generic_update_manager_allowed": False,
        },
        "safety": {
            "secrets_persisted": False,
            "changes_made": False,
            "generated_resources_adopted": False,
            "update_started": False,
        },
    }
    result["audit_id"] = digest(result)
    return result


def audit(policy: dict, *, token_file: Path | None = None) -> dict:
    policy = validate_policy(policy)
    base_policy = coolify_adapter.load_policy()
    need(base_policy["root"] == policy["root"],
         "Coolify adapter and controller roots differ")
    base = coolify_adapter.audit(base_policy)
    versions = fetch_versions(policy)
    installed = _image_version(next(
        row["image"] for row in base["components"] if row["name"] == "coolify"))
    target = versions.get("coolify") if versions["status"] == "checked" else None
    migration = inspect_custom_compose(policy, installed, target)
    return build_audit(
        policy, base, versions, collect_host(policy), collect_tasks(policy),
        migration, inspect_updater_shim(policy), inspect_api(policy, token_file),
        collect_sentinel_limits(),
    )


def validate_audit(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "support", "generated_at",
                 "base_audit_id", "base_health_ready", "local_backup_ready",
                 "installed", "available", "host", "scheduled_tasks",
                 "migration", "updater_shim", "controller_api",
                 "sentinel_limits", "ownership", "safety", "audit_id"},
         "Coolify controller audit")
    need(value["kind"] == "homelab-coolify-controller-audit"
         and value["contract"] == CONTRACT
         and value["platform"] == "windows-docker-desktop-existing-instance"
         and value["support"] == "experimental-existing-instance-only",
         "Unsupported Coolify controller audit")
    keys(value["installed"], {"coolify", "realtime", "sentinel", "traefik",
                              "legacy_realtime_container"}, "Installed Coolify versions")
    keys(value["available"], {"status", "source", "sha256", "channel", "coolify",
                              "helper", "sentinel", "traefik"},
         "Available Coolify versions")
    keys(value["host"], {"host_os", "docker_context", "docker_server_version",
                         "docker_server_os", "docker_server_arch", "compose_version",
                         "wsl_distribution", "wsl_host_mount_accessible", "root_exists"},
         "Coolify Windows host")
    need([row.get("name") for row in value["scheduled_tasks"]] == list(TASKS),
         "Coolify scheduled task order changed")
    for row in value["scheduled_tasks"]:
        keys(row, {"name", "exists", "state", "last_result", "action_matches"},
             f"Coolify scheduled task {row.get('name')}")
    keys(value["migration"], {"sha256", "legacy_soketi_override",
                              "reverb_ports_on_coolify", "crosses_reverb_boundary",
                              "review_required"}, "Coolify Reverb migration")
    keys(value["updater_shim"], {"status", "local_exists", "local_markers",
                                 "remote_sha256", "mount_anchor_count",
                                 "completion_anchor_count", "compatible"},
         "Coolify updater shim")
    keys(value["controller_api"], {"configured", "status", "http_status",
                                   "active_deployments", "secret_persisted"},
         "Coolify controller API")
    need(value["controller_api"]["secret_persisted"] is False,
         "Coolify API token must not be persisted in evidence")
    keys(value["sentinel_limits"], {"status", "expected", "actual", "compliant"},
         "Coolify Sentinel limits")
    need(value["sentinel_limits"]["expected"] == EXPECTED_SENTINEL_LIMITS,
         "Coolify Sentinel resource policy changed")
    need(value["ownership"] == {"controller": "coolify",
                                 "update_owner": "coolify-dashboard",
                                 "generic_update_manager_allowed": False},
         "Coolify controller ownership changed")
    need(value["safety"] == {"secrets_persisted": False, "changes_made": False,
                              "generated_resources_adopted": False,
                              "update_started": False},
         "Coolify controller audit crossed its read-only boundary")
    copy = dict(value)
    identifier = copy.pop("audit_id")
    need(identifier == digest(copy), "Coolify controller audit identifier is invalid")
    return value


def make_plan(policy: dict, observed: dict) -> dict:
    policy = validate_policy(policy)
    observed = validate_audit(observed)
    available = observed["available"]
    installed = observed["installed"]["coolify"]
    target = available["coolify"] if available["status"] == "checked" else None
    update_available = bool(installed and target
                            and _version_tuple(target) > _version_tuple(installed))
    host = observed["host"]
    host_ready = (
        host["host_os"] == "windows"
        and host["docker_context"] == policy["windows"]["docker_context"]
        and host["docker_server_os"] == policy["windows"]["server_os"]
        and host["docker_server_arch"] == policy["windows"]["server_arch"]
        and host["wsl_host_mount_accessible"] is True
        and host["root_exists"] is True
    )
    tasks_ready = all(row["exists"] and row["last_result"] == 0
                      and row["action_matches"] for row in observed["scheduled_tasks"])
    active_clear = observed["controller_api"]["active_deployments"] == 0
    blockers = ["windows-docker-desktop-is-not-an-upstream-supported-coolify-host"]
    if not observed["local_backup_ready"]:
        blockers.append("fresh-local-control-plane-backup-is-missing")
    blockers.append("encrypted-off-host-control-plane-restore-not-yet-proven")
    if not host_ready:
        blockers.append("windows-docker-desktop-compatibility-check-failed")
    if not tasks_ready:
        blockers.append("windows-scheduled-task-check-failed")
    if not observed["updater_shim"]["compatible"]:
        blockers.append("windows-updater-shim-does-not-match-current-upgrade-script")
    if not observed["sentinel_limits"]["compliant"]:
        blockers.append("sentinel-resource-limits-drifted")
    if observed["controller_api"]["status"] != "checked":
        blockers.append("read-only-controller-api-token-is-not-configured")
    elif not active_clear:
        blockers.append("active-deployments-must-finish-before-update")
    if observed["migration"]["review_required"]:
        blockers.append("soketi-to-reverb-migration-requires-windows-rehearsal")
    result = {
        "kind": "homelab-coolify-controller-plan",
        "contract": CONTRACT,
        "platform": policy["platform"],
        "audit_id": observed["audit_id"],
        "installed_version": installed,
        "target_channel": policy["channel"],
        "target_version": target,
        "update_available": update_available,
        "controller_api_ready": active_clear,
        "windows_compatibility_ready": host_ready and tasks_ready,
        "reverb_migration_review_required": observed["migration"]["review_required"],
        "updater_shim_ready": observed["updater_shim"]["compatible"],
        "sentinel_limits_ready": observed["sentinel_limits"]["compliant"],
        "local_backup_ready": observed["local_backup_ready"],
        "encrypted_off_host_recovery_ready": False,
        "update_owner": policy["updates"]["owner"],
        "generic_update_manager_allowed": False,
        "automatic_update_supported": False,
        "update_ready": False,
        "blockers": blockers,
        "operations": [
            "finish-active-deployments-through-controller-api",
            "create-and-verify-controller-owned-instance-backup",
            "complete-encrypted-off-host-restore-rehearsal",
            "rehearse-soketi-to-reverb-on-disposable-windows-restore",
            "start-update-from-coolify-settings-updates",
            "verify-dashboard-realtime-terminal-proxy-and-synthetic-deployment",
            "reapply-and-verify-sentinel-resource-limits",
        ],
        "changes_performed": False,
    }
    result["plan_id"] = digest(result)
    return result


def validate_plan(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "audit_id", "installed_version",
                 "target_channel", "target_version", "update_available",
                 "controller_api_ready", "windows_compatibility_ready",
                 "reverb_migration_review_required", "updater_shim_ready",
                 "sentinel_limits_ready", "local_backup_ready",
                 "encrypted_off_host_recovery_ready", "update_owner",
                 "generic_update_manager_allowed", "automatic_update_supported",
                 "update_ready", "blockers", "operations", "changes_performed",
                 "plan_id"}, "Coolify controller plan")
    need(value["kind"] == "homelab-coolify-controller-plan"
         and value["contract"] == CONTRACT,
         "Unsupported Coolify controller plan")
    need(value["update_owner"] == "coolify-dashboard"
         and value["generic_update_manager_allowed"] is False
         and value["automatic_update_supported"] is False
         and value["encrypted_off_host_recovery_ready"] is False
         and value["update_ready"] is False
         and value["changes_performed"] is False,
         "Coolify controller plan crossed its ownership or recovery boundary")
    copy = dict(value)
    identifier = copy.pop("plan_id")
    need(identifier == digest(copy), "Coolify controller plan identifier is invalid")
    return value
