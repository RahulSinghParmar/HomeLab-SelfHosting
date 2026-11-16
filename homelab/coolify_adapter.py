"""Read-only Coolify inventory and non-owning lifecycle planning."""
from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT, canonical, keys, load_json, need
from .sandbox import digest


CONTRACT = "phase7-coolify-adapter-v1"
MODULE = ROOT / "modules/coolify"
POLICY = MODULE / "policy.example.json"
COMPONENTS = (
    "coolify",
    "coolify-db",
    "coolify-redis",
    "coolify-realtime",
    "coolify-testing-host",
    "coolify-proxy",
    "coolify-sentinel",
)
OWNERS = {
    "coolify": "root-compose",
    "coolify-db": "root-compose",
    "coolify-redis": "root-compose",
    "coolify-realtime": "root-compose",
    "coolify-testing-host": "root-compose",
    "coolify-proxy": "coolify-generated-proxy-compose",
    "coolify-sentinel": "coolify-scheduler",
}
DOCKER_CONTROL = {
    "coolify-testing-host",
    "coolify-proxy",
    "coolify-sentinel",
}


def validate_policy(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "root", "dashboard",
                 "components", "backup", "updates"}, "Coolify policy")
    need(value["kind"] == "homelab-coolify-policy"
         and value["contract"] == CONTRACT,
         "Unsupported Coolify policy")
    need(value["platform"] == "windows-docker-desktop-existing-instance",
         "Coolify adapter supports only the reviewed existing Windows instance")
    need(isinstance(value["root"], str)
         and bool(re.fullmatch(r"[A-Za-z]:\\[^\x00]+", value["root"])),
         "Coolify root must be an absolute Windows path")

    dashboard = value["dashboard"]
    keys(dashboard, {"health_url", "loopback_only"}, "Coolify dashboard")
    need(dashboard == {
        "health_url": "http://127.0.0.1:8000/api/health",
        "loopback_only": True,
    }, "Coolify dashboard health endpoint or loopback policy changed")

    components = value["components"]
    keys(components, set(COMPONENTS), "Coolify components")
    for name in COMPONENTS:
        item = components[name]
        keys(item, {"owner", "docker_control"}, f"Coolify component {name}")
        need(item == {"owner": OWNERS[name],
                      "docker_control": name in DOCKER_CONTROL},
             f"Coolify lifecycle owner changed for {name}")

    backup = value["backup"]
    keys(backup, {"directory", "script", "scheduled_task",
                  "maximum_age_hours", "encrypted_off_host_required",
                  "managed_application_data_included"}, "Coolify backup policy")
    need(backup["directory"] == "backups-host"
         and backup["script"] == "maintenance\\Backup-Coolify.ps1"
         and backup["scheduled_task"] == "Coolify-Daily-Backup",
         "Coolify backup locations changed")
    need(type(backup["maximum_age_hours"]) is int
         and 24 <= backup["maximum_age_hours"] <= 168,
         "Coolify maximum backup age must be between 24 and 168 hours")
    need(backup["encrypted_off_host_required"] is True
         and backup["managed_application_data_included"] is False,
         "Coolify backups must require off-host encryption and exclude app data")

    updates = value["updates"]
    keys(updates, {"automatic", "backup_required", "active_deployments_check",
                   "rollback"}, "Coolify update policy")
    need(updates == {
        "automatic": False,
        "backup_required": True,
        "active_deployments_check": True,
        "rollback": "matching-version-database-restore",
    }, "Coolify controlled-update policy changed")
    return json.loads(canonical(value))


def load_policy(path: Path = POLICY) -> dict:
    return validate_policy(load_json(path))


def _run(arguments: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(arguments, cwd=cwd, text=True, encoding="utf-8",
                          errors="replace", capture_output=True, timeout=30,
                          check=False)


def _container(name: str) -> dict:
    template = (
        '{{json .State}}|{{.Config.Image}}|{{.Image}}|'
        '{{.HostConfig.Privileged}}|'
        '{{index .Config.Labels "com.docker.compose.project"}}|'
        '{{json .Mounts}}|{{json .NetworkSettings.Ports}}'
    )
    result = _run(["docker", "inspect", "--format", template, name])
    if result.returncode != 0:
        return {"name": name, "owner": OWNERS[name], "exists": False,
                "state": "missing", "health": "missing", "image": None,
                "image_id": None, "privileged": False,
                "docker_socket": False, "compose_project": None,
                "published_bindings": []}
    state_text, image, image_id, privileged, project, mounts_text, ports_text = \
        result.stdout.strip().split("|", 6)
    state = json.loads(state_text)
    mounts = json.loads(mounts_text or "[]")
    ports = json.loads(ports_text or "{}") or {}
    bindings = []
    for container_port, rows in sorted(ports.items()):
        for row in rows or []:
            bindings.append({"container_port": container_port,
                             "host_ip": row.get("HostIp"),
                             "host_port": row.get("HostPort")})
    health = state.get("Health", {}).get("Status")
    return {
        "name": name,
        "owner": OWNERS[name],
        "exists": True,
        "state": state.get("Status", "unknown"),
        "health": health or state.get("Status", "unknown"),
        "image": image,
        "image_id": image_id,
        "privileged": privileged.casefold() == "true",
        "docker_socket": any(
            item.get("Destination") in ("/var/run/docker.sock", "/run/docker.sock")
            for item in mounts
        ),
        "compose_project": None if project in ("", "<no value>") else project,
        "published_bindings": bindings,
    }


def _compose_valid(root: Path, proxy: bool = False) -> bool:
    arguments = ["docker", "compose"]
    if proxy:
        arguments += ["-f", "docker-compose.yml", "-f", "docker-compose.override.yml"]
    arguments += ["config", "--quiet"]
    return _run(arguments, cwd=root).returncode == 0


def _health(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def _backup(root: Path, maximum_age_hours: int,
            now: datetime | None = None) -> dict:
    backup_root = root / "backups-host"
    candidates = sorted(
        (item for item in backup_root.iterdir()
         if item.is_dir() and re.fullmatch(r"[0-9]{8}-[0-9]{6}", item.name)),
        key=lambda item: item.name,
        reverse=True,
    ) if backup_root.is_dir() else []
    if not candidates:
        return {"exists": False, "age_hours": None, "fresh": False,
                "database_dump": False, "manifest": False,
                "encrypted_at_rest": False, "off_host_verified": False}
    latest = candidates[0]
    observed = datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc)
    reference = now or datetime.now(timezone.utc)
    age = max(0.0, (reference - observed).total_seconds() / 3600)
    return {
        "exists": True,
        "age_hours": round(age, 2),
        "fresh": age <= maximum_age_hours,
        "database_dump": (latest / "coolify-postgres.dump").is_file(),
        "manifest": (latest / "manifest.json").is_file(),
        "encrypted_at_rest": False,
        "off_host_verified": False,
    }


def audit(policy: dict, *, now: datetime | None = None) -> dict:
    policy = validate_policy(policy)
    root = Path(policy["root"])
    rows = [_container(name) for name in COMPONENTS]
    result = {
        "kind": "homelab-coolify-audit",
        "contract": CONTRACT,
        "platform": policy["platform"],
        "support": "experimental-existing-instance-only",
        "components": rows,
        "checks": {
            "root_compose_valid": _compose_valid(root),
            "proxy_compose_valid": _compose_valid(root / "proxy", proxy=True),
            "dashboard_health": _health(policy["dashboard"]["health_url"]),
        },
        "backup": _backup(root, policy["backup"]["maximum_age_hours"], now),
        "safety": {
            "secrets_read": False,
            "changes_made": False,
            "generated_resources_adopted": False,
        },
    }
    result["audit_id"] = digest(result)
    return result


def validate_audit(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "support", "components",
                 "checks", "backup", "safety", "audit_id"}, "Coolify audit")
    need(value["kind"] == "homelab-coolify-audit"
         and value["contract"] == CONTRACT
         and value["platform"] == "windows-docker-desktop-existing-instance"
         and value["support"] == "experimental-existing-instance-only",
         "Unsupported Coolify audit")
    need(isinstance(value["components"], list)
         and [row.get("name") for row in value["components"]] == list(COMPONENTS),
         "Coolify audit component order changed")
    required_component = {"name", "owner", "exists", "state", "health",
                          "image", "image_id", "privileged", "docker_socket",
                          "compose_project", "published_bindings"}
    for row in value["components"]:
        keys(row, required_component, f"Coolify audit component {row.get('name')}")
        name = row["name"]
        need(row["owner"] == OWNERS[name], f"Incorrect owner for {name}")
        need(row["privileged"] is False, f"Privileged Coolify component: {name}")
        need(row["docker_socket"] is (name in DOCKER_CONTROL),
             f"Unexpected Docker-control boundary for {name}")
    keys(value["checks"], {"root_compose_valid", "proxy_compose_valid",
                           "dashboard_health"}, "Coolify checks")
    keys(value["backup"], {"exists", "age_hours", "fresh", "database_dump",
                           "manifest", "encrypted_at_rest", "off_host_verified"},
         "Coolify backup audit")
    need(value["backup"]["encrypted_at_rest"] is False
         and value["backup"]["off_host_verified"] is False,
         "Off-host or encryption claims require a separate recovery proof")
    need(value["safety"] == {"secrets_read": False, "changes_made": False,
                              "generated_resources_adopted": False},
         "Coolify audit crossed its read-only boundary")
    copy = dict(value)
    identifier = copy.pop("audit_id")
    need(identifier == digest(copy), "Coolify audit identifier does not match content")
    return value


def make_plan(policy: dict, observed: dict) -> dict:
    policy = validate_policy(policy)
    observed = validate_audit(observed)
    healthy = (all(row["exists"] and row["health"] in ("healthy", "running")
                   for row in observed["components"])
               and all(observed["checks"].values()))
    local_backup = (observed["backup"]["fresh"]
                    and observed["backup"]["database_dump"]
                    and observed["backup"]["manifest"])
    result = {
        "kind": "homelab-coolify-adapter-plan",
        "contract": CONTRACT,
        "platform": policy["platform"],
        "support": "experimental-existing-instance-only",
        "audit_id": observed["audit_id"],
        "lifecycle_owners": OWNERS,
        "docker_control_components": sorted(DOCKER_CONTROL),
        "health_ready": healthy,
        "local_control_plane_backup_ready": local_backup,
        "encrypted_off_host_control_plane_recovery": False,
        "managed_application_recovery_included": False,
        "update_ready": False,
        "operations": [
            "health-read-only",
            "control-plane-backup-owner-command",
            "pre-update-active-deployment-check",
            "manual-update-owner-command",
            "post-update-health-validation",
            "matching-version-database-restore-on-failure",
        ],
        "blockers": [
            "windows-docker-desktop-is-not-an-upstream-supported-production-host",
            "encrypted-off-host-control-plane-restore-not-yet-proven",
            "managed-application-data-requires-separate-module-backups",
        ],
        "fresh_install_supported": False,
        "automatic_update_supported": False,
        "production_state_adopted": False,
        "changes_performed": False,
    }
    result["plan_id"] = digest(result)
    return result


def validate_plan(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "support", "audit_id",
                 "lifecycle_owners", "docker_control_components", "health_ready",
                 "local_control_plane_backup_ready",
                 "encrypted_off_host_control_plane_recovery",
                 "managed_application_recovery_included", "update_ready",
                 "operations", "blockers", "fresh_install_supported",
                 "automatic_update_supported", "production_state_adopted",
                 "changes_performed", "plan_id"}, "Coolify adapter plan")
    need(value["kind"] == "homelab-coolify-adapter-plan"
         and value["contract"] == CONTRACT,
         "Unsupported Coolify adapter plan")
    need(value["lifecycle_owners"] == OWNERS
         and value["docker_control_components"] == sorted(DOCKER_CONTROL),
         "Coolify lifecycle ownership changed")
    need(value["update_ready"] is False
         and value["fresh_install_supported"] is False
         and value["automatic_update_supported"] is False
         and value["production_state_adopted"] is False
         and value["changes_performed"] is False,
         "Coolify adapter exceeded its non-owning boundary")
    copy = dict(value)
    identifier = copy.pop("plan_id")
    need(identifier == digest(copy), "Coolify plan identifier does not match content")
    return value
