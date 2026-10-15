"""Privacy-bounded host snapshots for the reusable Glance operations layout."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import ConfigError, ID, keys, load_json, need
from .privatefs import atomic_json, create_lock_file, create_private_directory, operation_lock, safe_path, verify_private


SCHEMA = 1
MAX_ITEMS = 64
CONTAINER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
SERVICE = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def label(value: object) -> str:
    need(isinstance(value, str) and 0 < len(value) <= 80 and value == value.strip(), "A short display label is required")
    need(not any(ord(char) < 32 or ord(char) == 127 for char in value), "Display labels cannot contain control characters")
    return value


def entries(value: object, location: str) -> list[dict]:
    need(isinstance(value, list) and len(value) <= MAX_ITEMS, f"{location} must be a bounded list")
    need(all(isinstance(item, dict) for item in value), f"{location} entries must be objects")
    identifiers = [item.get("id") for item in value]
    need(all(isinstance(item, str) and ID.fullmatch(item) for item in identifiers), f"{location} contains an invalid ID")
    need(len(identifiers) == len(set(identifiers)), f"{location} contains duplicate IDs")
    return value


def absolute_path(value: object, *, must_exist: bool = False) -> Path:
    need(isinstance(value, str) and value == value.strip(), "A local absolute path is required")
    path = Path(value)
    need(path.is_absolute() and ".." not in path.parts, "A local absolute path without traversal is required")
    need(not any(entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction())
                 for entry in (path, *path.parents)), "Symlink/junction paths require manual review")
    if must_exist:
        need(path.exists(), "A configured monitoring path does not exist")
    return path.resolve()


def validate_config(config: object) -> dict:
    keys(config, {"kind", "schema_version", "output_dir", "docker", "storage", "backups", "endpoints", "windows_services"}, "collector config")
    need(config["kind"] == "homelab-glance-collector" and config["schema_version"] == SCHEMA,
         "Unsupported Glance collector configuration")
    output = safe_path(absolute_path(config["output_dir"]))
    need(output.parent.is_dir(), "Collector output parent must already exist")

    keys(config["docker"], {"enabled", "include"}, "docker collector")
    need(type(config["docker"]["enabled"]) is bool, "Docker enabled must be true or false")
    docker_entries = entries(config["docker"]["include"], "docker include")
    for item in docker_entries:
        keys(item, {"id", "label", "container"}, "docker include entry")
        label(item["label"])
        need(isinstance(item["container"], str) and CONTAINER.fullmatch(item["container"]), "Invalid container name")
    need(config["docker"]["enabled"] or not docker_entries, "Docker entries require the Docker collector")

    storage = entries(config["storage"], "storage")
    for item in storage:
        keys(item, {"id", "label", "path", "warning_free_percent"}, "storage entry")
        label(item["label"])
        absolute_path(item["path"])
        need(type(item["warning_free_percent"]) is int and 1 <= item["warning_free_percent"] <= 50,
             "Storage warning threshold must be between 1 and 50 percent")

    backups = entries(config["backups"], "backups")
    for item in backups:
        keys(item, {"id", "label", "path", "pattern", "max_age_hours"}, "backup entry")
        label(item["label"])
        absolute_path(item["path"])
        need(isinstance(item["pattern"], str) and 0 < len(item["pattern"]) <= 128
             and not Path(item["pattern"]).is_absolute() and ".." not in Path(item["pattern"]).parts,
             "Backup pattern must be a bounded relative glob")
        need(type(item["max_age_hours"]) is int and 1 <= item["max_age_hours"] <= 8760,
             "Backup maximum age must be between 1 and 8760 hours")

    endpoints = entries(config["endpoints"], "endpoints")
    for item in endpoints:
        keys(item, {"id", "label", "url", "accepted_status", "timeout_seconds", "check_tls"}, "endpoint entry")
        label(item["label"])
        parsed = urllib.parse.urlsplit(item["url"] if isinstance(item["url"], str) else "")
        need(parsed.scheme in ("http", "https") and bool(parsed.hostname) and parsed.username is None
             and parsed.password is None and not parsed.fragment, "Endpoint URL must be credential-free HTTP or HTTPS")
        need(len(item["url"]) <= 2048, "Endpoint URL is too long")
        need(isinstance(item["accepted_status"], list) and 1 <= len(item["accepted_status"]) <= 20
             and all(type(code) is int and 100 <= code <= 599 for code in item["accepted_status"]),
             "Endpoint accepted statuses are invalid")
        need(type(item["timeout_seconds"]) is int and 1 <= item["timeout_seconds"] <= 30,
             "Endpoint timeout must be between 1 and 30 seconds")
        need(type(item["check_tls"]) is bool and (not item["check_tls"] or parsed.scheme == "https"),
             "TLS checks require an HTTPS endpoint")

    services = entries(config["windows_services"], "windows services")
    for item in services:
        keys(item, {"id", "label", "name"}, "Windows service entry")
        label(item["label"])
        need(isinstance(item["name"], str) and SERVICE.fullmatch(item["name"]), "Invalid Windows service name")

    monitored = [absolute_path(item["path"]) for item in storage + backups]
    need(all(not output.is_relative_to(path) and not path.is_relative_to(output) for path in monitored),
         "Collector output must not overlap monitored storage")
    return json.loads(json.dumps(config, sort_keys=True))


def public_config(config: dict) -> dict:
    config = validate_config(config)
    return {
        "kind": config["kind"], "schema_version": config["schema_version"], "output_dir": "<private-output>",
        "docker": {"enabled": config["docker"]["enabled"], "include": [
            {"id": row["id"], "label": row["label"]} for row in config["docker"]["include"]]},
        "storage": [{"id": row["id"], "label": row["label"], "path": "<private-path>",
                     "warning_free_percent": row["warning_free_percent"]} for row in config["storage"]],
        "backups": [{"id": row["id"], "label": row["label"], "path": "<private-path>",
                     "pattern": "<private-pattern>", "max_age_hours": row["max_age_hours"]} for row in config["backups"]],
        "endpoints": [{"id": row["id"], "label": row["label"], "origin": "<private-origin>",
                       "accepted_status": row["accepted_status"], "timeout_seconds": row["timeout_seconds"],
                       "check_tls": row["check_tls"]} for row in config["endpoints"]],
        "windows_services": [{"id": row["id"], "label": row["label"]} for row in config["windows_services"]],
    }


def run(command: list[str], timeout: int = 20) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=timeout, shell=False, creationflags=flags)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ConfigError("A local monitoring command is unavailable or timed out") from error
    need(result.returncode == 0, "A local monitoring command failed; raw output is intentionally hidden")
    return result.stdout.strip()


def host_snapshot() -> dict:
    result = {"status": "limited", "platform": "windows" if os.name == "nt" else os.uname().sysname.lower(),
              "metrics_available": False, "cpu_count": os.cpu_count() or 0, "cpu_percent": 0.0,
              "memory_total_gib": 0.0, "memory_used_gib": 0.0, "memory_percent": 0.0}
    try:
        import psutil  # Optional: the collector remains useful without it.
        memory = psutil.virtual_memory()
        result.update(status="ok", metrics_available=True, cpu_percent=round(float(psutil.cpu_percent(interval=0.1)), 1),
                      memory_total_gib=round(memory.total / 1024 ** 3, 2),
                      memory_used_gib=round(memory.used / 1024 ** 3, 2), memory_percent=round(float(memory.percent), 1))
    except (ImportError, OSError, ValueError):
        pass
    return result


def docker_snapshot(specification: dict) -> dict:
    if not specification["enabled"]:
        return {"status": "disabled", "selected": [], "running": 0, "attention": 0}
    context = run(["docker", "context", "show"])
    need(bool(CONTAINER.fullmatch(context)), "Invalid Docker context name")
    endpoint = json.loads(run(["docker", "context", "inspect", context, "--format", "{{json .Endpoints.docker.Host}}"]))
    need(endpoint.startswith(("npipe://", "unix://", "desktop-linux")), "Remote Docker contexts are not supported")
    selected = []
    for item in specification["include"]:
        try:
            raw = run(["docker", "--context", context, "inspect", "--format",
                       "{{json .State.Status}}|{{if .State.Health}}{{json .State.Health.Status}}{{else}}\"none\"{{end}}|{{.RestartCount}}|{{.State.OOMKilled}}",
                       item["container"]])
            state_value, health_value, restarts, oom = raw.split("|")
            state = json.loads(state_value)
            health = json.loads(health_value)
            row = {"id": item["id"], "label": item["label"], "state": state, "health": health,
                   "restarts": int(restarts), "oom": oom.lower() == "true"}
            row["status"] = "ok" if state == "running" and health not in ("unhealthy", "starting") and not row["oom"] else "warning"
        except (ConfigError, ValueError, json.JSONDecodeError):
            row = {"id": item["id"], "label": item["label"], "status": "unavailable", "state": "unknown",
                   "health": "unknown", "restarts": 0, "oom": False}
        selected.append(row)
    return {"status": "ok" if all(row["status"] == "ok" for row in selected) else "warning",
            "selected": selected, "running": sum(row.get("state") == "running" for row in selected),
            "attention": sum(row["status"] != "ok" for row in selected)}


def storage_snapshot(specification: list[dict]) -> list[dict]:
    rows = []
    for item in specification:
        try:
            usage = shutil.disk_usage(item["path"])
            free_percent = round(100 * usage.free / usage.total, 1) if usage.total else 0
            rows.append({"id": item["id"], "label": item["label"],
                         "total_gib": round(usage.total / 1024 ** 3, 1), "free_gib": round(usage.free / 1024 ** 3, 1),
                         "used_percent": round(100 * usage.used / usage.total, 1) if usage.total else 0,
                         "status": "warning" if free_percent < item["warning_free_percent"] else "ok"})
        except OSError:
            rows.append({"id": item["id"], "label": item["label"], "status": "unavailable",
                         "total_gib": -1.0, "free_gib": -1.0, "used_percent": -1.0})
    return rows


def backup_snapshot(specification: list[dict], now: float) -> list[dict]:
    rows = []
    for item in specification:
        base = Path(item["path"])
        try:
            candidates = [path for path in base.glob(item["pattern"])
                          if path.is_file() and not path.is_symlink() and path.stat().st_size > 0]
            if not candidates:
                rows.append({"id": item["id"], "label": item["label"], "status": "missing",
                             "age_hours": -1.0, "artifact_count": 0})
                continue
            latest = max(candidates, key=lambda path: path.stat().st_mtime)
            age = max(0.0, (now - latest.stat().st_mtime) / 3600)
            rows.append({"id": item["id"], "label": item["label"], "status": "ok" if age <= item["max_age_hours"] else "stale",
                         "age_hours": round(age, 1), "artifact_count": len(candidates)})
        except OSError:
            rows.append({"id": item["id"], "label": item["label"], "status": "unavailable",
                         "age_hours": -1.0, "artifact_count": 0})
    return rows


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def endpoint_snapshot(specification: list[dict]) -> tuple[list[dict], list[dict]]:
    endpoints, certificates = [], []
    opener = urllib.request.build_opener(NoRedirect())
    for item in specification:
        started = time.monotonic()
        code = 0
        try:
            request = urllib.request.Request(item["url"], method="HEAD", headers={"User-Agent": "HomeLab-Glance-Collector/1"})
            try:
                response = opener.open(request, timeout=item["timeout_seconds"])
            except urllib.error.HTTPError as error:
                response = error
            with response:
                code = int(response.code)
            status = "ok" if code in item["accepted_status"] else "warning"
        except Exception:
            status = "unavailable"
        endpoints.append({"id": item["id"], "label": item["label"], "status": status,
                          "http_status": code, "latency_ms": round((time.monotonic() - started) * 1000)})
        if item["check_tls"]:
            parsed = urllib.parse.urlsplit(item["url"])
            try:
                context = ssl.create_default_context()
                with socket.create_connection((parsed.hostname, parsed.port or 443), timeout=item["timeout_seconds"]) as raw:
                    with context.wrap_socket(raw, server_hostname=parsed.hostname) as wrapped:
                        certificate = wrapped.getpeercert()
                expires = datetime.strptime(certificate["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                days = max(0, int((expires - datetime.now(timezone.utc)).total_seconds() // 86400))
                certificates.append({"id": item["id"], "label": item["label"], "status": "critical" if days < 7 else "warning" if days < 21 else "ok",
                                     "days_remaining": days})
            except Exception:
                certificates.append({"id": item["id"], "label": item["label"], "status": "unavailable", "days_remaining": -1})
    return endpoints, certificates


def parse_windows_service_state(output: str) -> str:
    code = next((int(value) for value, _ in re.findall(r":\s*(\d+)\s+(\S+)", output)
                 if 1 <= int(value) <= 7), None)
    need(code is not None, "Windows service state was not recognized")
    return {1: "stopped", 2: "start-pending", 3: "stop-pending", 4: "running",
            5: "continue-pending", 6: "pause-pending", 7: "paused"}[code]


def windows_service_snapshot(specification: list[dict]) -> list[dict]:
    rows = []
    for item in specification:
        if os.name != "nt":
            rows.append({"id": item["id"], "label": item["label"], "status": "unsupported", "state": "unknown"})
            continue
        try:
            output = run(["sc.exe", "query", item["name"]])
            state = parse_windows_service_state(output)
            rows.append({"id": item["id"], "label": item["label"], "status": "ok" if state == "running" else "warning", "state": state})
        except ConfigError:
            rows.append({"id": item["id"], "label": item["label"], "status": "unavailable", "state": "unknown"})
    return rows


def prepare_output(path: Path) -> None:
    if not path.exists():
        create_private_directory(path)
    else:
        verify_private(path, directory=True)
    lock = path / "collector.lock"
    if not lock.exists():
        create_lock_file(lock)
    else:
        verify_private(lock)


def publish(path: Path, payload: dict) -> None:
    atomic_json(path, payload, replace=path.exists())


def collect(config: dict) -> dict:
    config = validate_config(config)
    output = Path(config["output_dir"])
    prepare_output(output)
    with operation_lock(output / "collector.lock"):
        generated = utcnow()
        host = host_snapshot()
        try:
            docker = docker_snapshot(config["docker"])
        except ConfigError:
            docker = {"status": "unavailable", "selected": [], "running": 0, "attention": len(config["docker"]["include"])}
        volumes = storage_snapshot(config["storage"])
        backups = backup_snapshot(config["backups"], time.time())
        endpoints, certificates = endpoint_snapshot(config["endpoints"])
        native = windows_service_snapshot(config["windows_services"])
        resources = {"schema_version": SCHEMA, "generated_at": generated, "status": "ok" if host["status"] == "ok" and docker["status"] in ("ok", "disabled") else "warning",
                     "host": host, "docker": docker}
        storage = {"schema_version": SCHEMA, "generated_at": generated,
                   "status": "ok" if all(row["status"] == "ok" for row in volumes + backups) else "warning",
                   "volumes": volumes, "backups": backups}
        services = {"schema_version": SCHEMA, "generated_at": generated,
                    "status": "ok" if all(row["status"] in ("ok", "unsupported") for row in endpoints + native) else "warning",
                    "endpoints": endpoints, "native": native}
        security = {"schema_version": SCHEMA, "generated_at": generated,
                    "status": "ok" if all(row["status"] == "ok" for row in certificates) else "warning",
                    "tls": certificates}
        attention = sum(payload["status"] != "ok" for payload in (resources, storage, services, security))
        overview = {"schema_version": SCHEMA, "generated_at": generated,
                    "status": "ok" if attention == 0 else "warning", "healthy_sections": 4 - attention,
                    "attention_sections": attention, "collector_version": 1}
        for name, payload in (("overview", overview), ("resources", resources), ("storage", storage),
                              ("services", services), ("security", security)):
            publish(output / f"{name}.json", payload)
        return {"module": "glance-collector", "generated_at": generated, "status": overview["status"],
                "snapshots": ["overview", "resources", "storage", "services", "security"],
                "private_output": True, "raw_command_output": "never-reported"}


def load_and_validate(path: Path) -> dict:
    return validate_config(load_json(path))
