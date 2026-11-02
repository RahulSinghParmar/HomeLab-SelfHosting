"""Isolated Immich lifecycle with protected-original recovery evidence."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .doctor import host_platform
from .glance import docker, local_runtime, port_free
from .privatefs import (atomic_json, create_lock_file, create_private_directory,
                        operation_lock, read_private, safe_path, verify_private,
                        windows_acl, windows_tree_acl)
from .sandbox import digest, pending_guard


MODULE = ROOT / "modules/immich"
SERVICES = ("redis", "database", "immich-server", "immich-machine-learning")
AUTHORITATIVE_AREAS = {
    "library": "/data/library",
    "upload": "/data/upload",
    "profile": "/data/profile",
}
DERIVED_AREAS = ("thumbs", "encoded-video", "backups")
SYSTEM_MARKER = ".immich"
VOLUMES = ("redis-data", "database-data", "model-cache")
LIMITS = {
    "redis": {"memory_mib": 256, "cpus": 0.25, "pids": 96},
    "database": {"memory_mib": 1024, "cpus": 1.0, "pids": 256},
    "immich-server": {"memory_mib": 2048, "cpus": 2.0, "pids": 512},
    "immich-machine-learning": {"memory_mib": 1536, "cpus": 1.0, "pids": 256},
}
ML_ENVIRONMENT = {
    "MACHINE_LEARNING_MODEL_TTL": "60",
    "MACHINE_LEARNING_MODEL_TTL_POLL_S": "10",
    "MACHINE_LEARNING_REQUEST_THREADS": "1",
    "MACHINE_LEARNING_MODEL_INTER_OP_THREADS": "1",
    "MACHINE_LEARNING_MODEL_INTRA_OP_THREADS": "1",
    "MACHINE_LEARNING_WORKERS": "1",
    "MACHINE_LEARNING_MAX_BATCH_SIZE__FACIAL_RECOGNITION": "1",
    "MACHINE_LEARNING_MAX_BATCH_SIZE__OCR": "1",
    "MACHINE_LEARNING_MODEL_ARENA": "false",
}
ADMIN_EMAIL = "phase6-immich@example.invalid"
FIXTURE_NAME = "phase6-immich-original.png"
# A deterministic nonempty 1x1 PNG used only by a disposable project.
FIXTURE_BODY = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cff00000040101005f9719890000000049454e44ae426082"
)


def images():
    return load_json(MODULE / "images.json")


def make_plan(root, port, runtime, backup=None):
    root = safe_path(Path(root))
    need(root.parent.is_dir() and "$" not in str(root),
         "Choose an absent installation under an existing local parent without interpolation characters")
    need(type(port) is int and 1024 <= port <= 65535,
         "Choose an unprivileged TCP port")
    keys(runtime, {"context", "endpoint", "engine_id"}, "local runtime")
    recovery = None
    if backup is not None:
        source = safe_path(Path(backup))
        need(not source.is_relative_to(root) and not root.is_relative_to(source),
             "Backup and installation must not overlap")
        manifest = verify_backup(source)
        recovery = {"path": str(source), "manifest_id": digest(manifest),
                    "method": "quiesced-postgres-protected-originals"}
    plan = {
        "kind": "homelab-immich-plan",
        "contract": "immich-isolated-recovery-v1",
        "platform": host_platform(),
        "root": str(root),
        "port": port,
        "runtime": runtime,
        "images": images(),
        "recovery": recovery,
        "limits": LIMITS,
        "machine_learning": {
            "backend": "cpu",
            "environment": ML_ENVIRONMENT,
            "device_access": False,
            "independently_stoppable": True,
        },
        "access": "loopback",
        "networks": ["frontend", "internal-backend"],
        "docker_socket": False,
        "public_registration": False,
        "external_libraries": "not-mounted",
        "recovery_method": "quiesced-postgres-protected-originals",
        "authoritative_material": ["postgres-custom-dump", *AUTHORITATIVE_AREAS],
        "derived_material": list(DERIVED_AREAS),
        "cache_material": ["redis-data", "model-cache"],
    }
    plan["plan_id"] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {"kind", "contract", "platform", "root", "port", "runtime",
                "images", "recovery", "limits", "machine_learning", "access",
                "networks", "docker_socket", "public_registration",
                "external_libraries", "recovery_method", "authoritative_material",
                "derived_material", "cache_material", "plan_id"}, "Immich plan")
    backup = plan["recovery"]["path"] if plan["recovery"] is not None else None
    need(canonical(plan) == canonical(make_plan(plan["root"], plan["port"],
                                                plan["runtime"], backup)),
         "Plan/image/recovery drift; review a new plan")
    return plan


def project(plan):
    return "hl-immich-" + plan["plan_id"][:16]


def tags(plan, owner):
    return {"org.homelab.owner": owner, "org.homelab.plan": plan["plan_id"],
            "org.homelab.module": "immich"}


def new_credentials():
    return {"database_password": secrets.token_urlsafe(48),
            "admin_password": secrets.token_urlsafe(48)}


def validate_credentials(value):
    keys(value, {"database_password", "admin_password"}, "Immich credentials")
    need(all(isinstance(value[name], str) and len(value[name]) >= 64 for name in value),
         "Invalid private credential material")
    need(all("\n" not in value[name] and "\r" not in value[name] for name in value),
         "Invalid private credential material")
    return value


def _write_secret(path, value):
    need(not path.exists(), "Refusing to overwrite an existing secret file")
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    if os.name == "nt":
        windows_acl(path, create=True)
    verify_private(path)


def _secret_path(plan):
    return Path(plan["root"]) / "secrets" / "database_password.txt"


def compose(plan, owner, credentials):
    validate_credentials(credentials)
    label = tags(plan, owner)
    common = {
        "labels": label,
        "pull_policy": "never",
        "restart": "unless-stopped",
        "security_opt": ["no-new-privileges:true"],
        "logging": {"driver": "json-file",
                    "options": {"max-size": "10m", "max-file": "3"}},
    }
    redis = {
        **common,
        "image": plan["images"]["cache"],
        "command": ["valkey-server", "--appendonly", "yes", "--save", "60", "1"],
        "volumes": [{"type": "volume", "source": "redis-data", "target": "/data"}],
        "networks": ["backend"],
        "healthcheck": {"test": ["CMD-SHELL", "valkey-cli ping | grep -q PONG"],
                        "interval": "10s", "timeout": "5s", "retries": 12,
                        "start_period": "5s"},
        "mem_limit": "256m", "mem_reservation": "32m", "memswap_limit": "320m",
        "cpus": 0.25, "pids_limit": 96,
    }
    database = {
        **common,
        "image": plan["images"]["database"],
        "environment": {"POSTGRES_DB": "immich", "POSTGRES_USER": "postgres",
                        "POSTGRES_PASSWORD_FILE": "/run/secrets/database_password",
                        "POSTGRES_INITDB_ARGS": "--data-checksums"},
        "secrets": ["database_password"],
        "volumes": [{"type": "volume", "source": "database-data",
                     "target": "/var/lib/postgresql/data"}],
        "networks": ["backend"],
        "shm_size": "128m",
        "mem_limit": "1024m", "mem_reservation": "256m", "memswap_limit": "1280m",
        "cpus": 1.0, "pids_limit": 256,
    }
    server = {
        **common,
        "image": plan["images"]["server"],
        # The image entrypoint is ``bash -c``. Keep this as one argv item so
        # Compose cannot tokenize ``export`` away from the server command.
        "command": ["export DB_PASSWORD=\"$$(cat /run/secrets/database_password)\"; exec start.sh"],
        "environment": {"DB_HOSTNAME": "database", "DB_USERNAME": "postgres",
                        "DB_DATABASE_NAME": "immich", "REDIS_HOSTNAME": "redis",
                        "CPU_CORES": "2", "IMMICH_ENV": "production",
                        "IMMICH_LOG_LEVEL": "warn", "IMMICH_ALLOW_SETUP": "true"},
        "secrets": ["database_password"],
        "depends_on": {"redis": {"condition": "service_healthy"},
                       "database": {"condition": "service_healthy"}},
        "ports": [{"target": 2283, "published": str(plan["port"]),
                   "host_ip": "127.0.0.1", "protocol": "tcp"}],
        "volumes": [{"type": "bind", "source": str(Path(plan["root"]) / "media"),
                     "target": "/data"}],
        "networks": ["frontend", "backend"],
        "stop_grace_period": "60s",
        "mem_limit": "2048m", "mem_reservation": "384m", "memswap_limit": "2560m",
        "cpus": 2.0, "pids_limit": 512,
    }
    machine_learning = {
        **common,
        "image": plan["images"]["machine_learning"],
        "environment": plan["machine_learning"]["environment"],
        "volumes": [{"type": "volume", "source": "model-cache", "target": "/cache"}],
        "networks": ["backend"],
        "mem_limit": "1536m", "mem_reservation": "128m", "memswap_limit": "1792m",
        "cpus": 1.0, "pids_limit": 256,
    }
    return {
        "services": {"redis": redis, "database": database,
                     "immich-server": server,
                     "immich-machine-learning": machine_learning},
        "volumes": {name: {"labels": label} for name in VOLUMES},
        "networks": {"frontend": {"driver": "bridge", "labels": label},
                     "backend": {"driver": "bridge", "internal": True,
                                 "labels": label}},
        "secrets": {"database_password": {"file": str(_secret_path(plan))}},
    }


def compose_args(plan):
    root = Path(plan["root"])
    return ["compose", "--project-name", project(plan), "--project-directory", str(root),
            "-f", str(root / "compose.json")]


def _role_image(plan, role):
    mapping = {"redis": "cache", "database": "database", "immich-server": "server",
               "immich-machine-learning": "machine_learning"}
    return plan["images"][mapping[role]]


def inventory(plan, owner):
    context = plan["runtime"]["context"]
    found = {"containers": {}, "networks": [], "volumes": []}
    ids = docker(["ps", "-aq", "--filter", "label=com.docker.compose.project=" + project(plan)],
                 context=context).split()
    need(len(ids) <= len(SERVICES), "Unexpected Immich project containers")
    rows = json.loads(docker(["inspect", *ids], context=context)) if ids else []
    for row in rows:
        labels = row["Config"].get("Labels") or {}
        need(owner is not None and all(labels.get(key) == value
                                       for key, value in tags(plan, owner).items()),
             "Foreign resource; no adoption or mutation")
        role = labels.get("com.docker.compose.service")
        need(role in SERVICES and role not in found["containers"],
             "Unexpected or duplicate service")
        need(row["Config"]["Image"] == _role_image(plan, role), "Image drift")
        host = row["HostConfig"]
        need(not host["Privileged"] and not host.get("Devices")
             and not host.get("DeviceRequests"), "Privilege/device drift")
        need("no-new-privileges:true" in host["SecurityOpt"], "Security option drift")
        limit = LIMITS[role]
        need(host["Memory"] == limit["memory_mib"] * 1024**2
             and host["NanoCpus"] == int(limit["cpus"] * 1_000_000_000)
             and host["PidsLimit"] == limit["pids"], "Resource drift")
        expected_ports = ({"2283/tcp": [{"HostIp": "127.0.0.1",
                                         "HostPort": str(plan["port"])}]}
                          if role == "immich-server" else {})
        need((host.get("PortBindings") or {}) == expected_ports, "Port binding drift")
        found["containers"][role] = row
    for kind, listing, inspect in (
            ("networks", ["network", "ls", "-q"], ["network", "inspect"]),
            ("volumes", ["volume", "ls", "-q"], ["volume", "inspect"])):
        resource_ids = docker(listing + ["--filter",
                              "label=com.docker.compose.project=" + project(plan)],
                              context=context).split()
        resources = json.loads(docker(inspect + resource_ids, context=context)) if resource_ids else []
        expected_max = 2 if kind == "networks" else len(VOLUMES)
        need(len(resources) <= expected_max, "Unexpected Immich project resources")
        for row in resources:
            labels = row.get("Labels") or {}
            need(owner is not None and all(labels.get(key) == value
                                           for key, value in tags(plan, owner).items()),
                 "Foreign resource; no adoption or mutation")
        found[kind] = resources
    return found


def state_read(plan):
    root = Path(plan["root"])
    verify_private(root, directory=True)
    pending_guard(root)
    state = read_private(root / "state.json")
    keys(state, {"kind", "owner", "plan_id", "status", "recovery"}, "Immich state")
    need(state["kind"] == "immich-owned-v1" and state["plan_id"] == plan["plan_id"],
         "Ownership mismatch")
    need(isinstance(state["owner"], str) and re.fullmatch("[0-9a-f]{32}", state["owner"]),
         "Invalid owner")
    need(state["status"] in ("prepared", "restoring", "running", "stopped",
                              "removing", "removed"), "Invalid state")
    credentials = validate_credentials(read_private(root / "credentials.json"))
    verify_private(_secret_path(plan))
    need(_secret_path(plan).read_text(encoding="utf-8") == credentials["database_password"],
         "Private database secret differs from reviewed credentials")
    need(read_private(root / "compose.json") == compose(plan, state["owner"], credentials),
         "Compose modified; refusing execution")
    return state


def prepare(plan):
    root = Path(plan["root"])
    if root.exists():
        return state_read(plan)
    inventory(plan, None)
    port_free(plan["port"])
    context = plan["runtime"]["context"]
    for image in plan["images"].values():
        inspected = json.loads(docker(["image", "inspect", image], context=context))[0]
        need(inspected["Os"] == "linux" and inspected["Architecture"] == "amd64",
             "Reviewed linux/amd64 images must be cached")
    create_private_directory(root)
    create_lock_file(root / "operation.lock")
    create_private_directory(root / "secrets")
    create_private_directory(root / "media")
    credentials = (read_private(Path(plan["recovery"]["path"]) / "credentials.json")
                   if plan["recovery"] else new_credentials())
    validate_credentials(credentials)
    _write_secret(_secret_path(plan), credentials["database_password"])
    owner = uuid.uuid4().hex
    state = {"kind": "immich-owned-v1", "owner": owner, "plan_id": plan["plan_id"],
             "status": "prepared", "recovery": None}
    atomic_json(root / "credentials.json", credentials)
    atomic_json(root / "compose.json", compose(plan, owner, credentials))
    atomic_json(root / "state.json", state)
    return state


def wait_health(plan, roles, deadline_seconds=600):
    deadline = time.monotonic() + deadline_seconds
    context = plan["runtime"]["context"]
    while time.monotonic() < deadline:
        ids = docker(compose_args(plan) + ["ps", "-q", *roles], context=context).split()
        if len(ids) == len(roles):
            values = [docker(["inspect", "--format",
                              "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                              value], context=context) for value in ids]
            if all(value in ("healthy", "running") for value in values):
                return
            need(not any(value in ("exited", "dead") for value in values),
                 "Immich service exited before becoming ready")
        time.sleep(2)
    raise ConfigError("Immich services did not become ready before the bounded deadline")


def _request(plan, method, path, *, token=None, body=None, content_type="application/json",
             expected=(200, 201)):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = body
    if isinstance(body, (dict, list)):
        data = json.dumps(body).encode("utf-8")
    if data is not None:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(
        f'http://127.0.0.1:{plan["port"]}/api{path}', data=data, method=method,
        headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
            need(response.status in expected, "Unexpected Immich response")
            return response.status, payload, response.headers
    except urllib.error.HTTPError as error:
        raise ConfigError(f"Immich API request failed with status {error.code}") from error
    except urllib.error.URLError as error:
        raise ConfigError("Immich API request failed") from error


def _login(plan, credentials, *, create=False):
    if create:
        _request(plan, "POST", "/auth/admin-sign-up",
                 body={"email": ADMIN_EMAIL, "name": "Phase 6 Recovery",
                       "password": credentials["admin_password"]})
    _, payload, _ = _request(plan, "POST", "/auth/login",
                             body={"email": ADMIN_EMAIL,
                                   "password": credentials["admin_password"]})
    value = json.loads(payload)
    need(value.get("isAdmin") is True and isinstance(value.get("accessToken"), str),
         "Immich admin login evidence is incomplete")
    return value["accessToken"]


def _multipart_asset():
    boundary = "homelab-" + uuid.uuid4().hex
    created = "2026-01-01T00:00:00.000Z"
    parts = []
    for name, value in (("fileCreatedAt", created), ("fileModifiedAt", created),
                        ("filename", FIXTURE_NAME), ("isFavorite", "false")):
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
                      f"\r\n\r\n{value}\r\n").encode())
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="assetData"; '
                  f'filename="{FIXTURE_NAME}"\r\nContent-Type: image/png\r\n\r\n').encode()
                 + FIXTURE_BODY + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def _fixture_evidence(plan, credentials, asset_id=None):
    token = _login(plan, credentials)
    if asset_id is None:
        asset_id = read_private(Path(plan["root"]) / "fixture.json")["asset_id"]
    _, payload, headers = _request(plan, "GET", f"/assets/{asset_id}/original",
                                   token=token, expected=(200,))
    need(payload == FIXTURE_BODY, "Restored Immich original differs from uploaded bytes")
    return {"asset_id": asset_id, "filename": FIXTURE_NAME, "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "content_type": headers.get_content_type(), "original_verified": True}


def _restore_database(plan, backup, database_id):
    context = plan["runtime"]["context"]
    target = "/tmp/immich-restore-" + uuid.uuid4().hex + ".dump"
    docker(["cp", str(backup / "immich-postgres.dump"), database_id + ":" + target],
           context=context, timeout=180)
    try:
        docker(["exec", database_id, "pg_restore", "--clean", "--if-exists",
                "--exit-on-error", "--no-owner", "-U", "postgres", "-d", "immich", target],
               context=context, timeout=600)
    finally:
        docker(["exec", database_id, "rm", "-f", target], context=context)


def _restore_files(plan, backup, server_id):
    context = plan["runtime"]["context"]
    for name, target in AUTHORITATIVE_AREAS.items():
        docker(["cp", str(backup / "filesystem" / name) + "/.", server_id + ":" + target],
               context=context, timeout=600)
    media = safe_path(Path(plan["root"]) / "media")
    for name in DERIVED_AREAS:
        target = safe_path(media / name)
        target.mkdir(mode=0o700, exist_ok=False)
        shutil.copy2(backup / "system-markers" / name / SYSTEM_MARKER,
                     target / SYSTEM_MARKER)


def operate(plan, action, confirmation=None):
    validate_plan(plan)
    need(action in ("up", "status", "stop", "remove"), "Unsupported Immich action")
    if action != "status":
        need(confirmation == plan["plan_id"], "Confirm the complete reviewed plan ID")
    need(local_runtime() == plan["runtime"], "Local Docker context/engine changed")
    root = Path(plan["root"])
    if action == "up":
        prepare(plan)
    with operation_lock(root / "operation.lock"):
        state = state_read(plan)
        resources = inventory(plan, state["owner"])
        containers = resources["containers"]
        context = plan["runtime"]["context"]
        need(state["status"] != "restoring",
             "Interrupted restore requires manual evidence review and a fresh target")
        if action == "up":
            need(state["status"] not in ("removing", "removed"),
                 "Removed deployments require a fresh root")
            if not containers:
                need(state["status"] == "prepared", "Recorded resources missing; no silent recreation")
                port_free(plan["port"])
                docker(compose_args(plan) + ["create", "--pull", "never", "--no-build"],
                       context=context, timeout=300)
                resources = inventory(plan, state["owner"])
                containers = resources["containers"]
            need(set(containers) == set(SERVICES) and len(resources["volumes"]) == len(VOLUMES),
                 "Incomplete Immich creation; retain state for review")
            if plan["recovery"] and state["status"] == "prepared":
                need(not any(row["State"]["Running"] for row in containers.values()),
                     "Recovery must target never-started containers")
                state["status"] = "restoring"
                atomic_json(root / "state.json", state, replace=True)
                docker(compose_args(plan) + ["start", "redis", "database"], context=context)
                wait_health(plan, ("redis", "database"))
                backup_root = Path(plan["recovery"]["path"])
                _restore_database(plan, backup_root, containers["database"]["Id"])
                _restore_files(plan, backup_root, containers["immich-server"]["Id"])
                shutil.copy2(backup_root / "fixture.json", root / "fixture.json")
                state["status"] = "prepared"
                atomic_json(root / "state.json", state, replace=True)
            docker(compose_args(plan) + ["up", "-d", "--no-build", "--pull", "never"],
                   context=context, timeout=600)
            wait_health(plan, SERVICES)
            credentials = read_private(root / "credentials.json")
            if plan["recovery"]:
                restored = _fixture_evidence(plan, credentials)
                source = verify_backup(Path(plan["recovery"]["path"]))
                need(restored == source["fixture"],
                     "Restored Immich content differs from backup evidence")
                state["recovery"] = {"manifest_id": plan["recovery"]["manifest_id"],
                                     "verified": True,
                                     "original_sha256": restored["sha256"]}
            state["status"] = "running"
        elif action == "stop":
            need(set(containers) == set(SERVICES), "No complete owned deployment to stop")
            docker(compose_args(plan) + ["stop", "--timeout", "60"],
                   context=context, timeout=180)
            state["status"] = "stopped"
        elif action == "remove":
            need(not any(row["State"]["Running"] for row in containers.values()),
                 "Stop all owned services before removal")
            if state["status"] != "removed":
                state["status"] = "removing"
                atomic_json(root / "state.json", state, replace=True)
                docker(compose_args(plan) + ["down", "--remove-orphans"],
                       context=context, timeout=180)
                state["status"] = "removed"
        if action != "status" and read_private(root / "state.json") != state:
            atomic_json(root / "state.json", state, replace=True)
        resources = inventory(plan, state["owner"])
        health = {
            role: ((row["State"].get("Health") or {}).get("Status", row["State"]["Status"])
                   if row["State"]["Running"] else row["State"]["Status"])
            for role, row in resources["containers"].items()
        }
        return {"module": "immich", "state": state["status"], "health": health,
                "url": "http://127.0.0.1:" + str(plan["port"]),
                "media_retained": (root / "media").is_dir(),
                "data_volumes_retained": len(resources["volumes"]),
                "recovery": state["recovery"]}


def exercise(plan, confirmation):
    validate_plan(plan)
    need(confirmation == plan["plan_id"], "Confirm the complete reviewed plan ID")
    need(local_runtime() == plan["runtime"], "Local Docker context/engine changed")
    root = Path(plan["root"])
    with operation_lock(root / "operation.lock"):
        state = state_read(plan)
        resources = inventory(plan, state["owner"])
        need(state["status"] == "running" and set(resources["containers"]) == set(SERVICES),
             "Start the complete owned Immich project before exercise")
        need(not (root / "fixture.json").exists(), "Synthetic fixture already exists")
        credentials = read_private(root / "credentials.json")
        token = _login(plan, credentials, create=True)
        body, content_type = _multipart_asset()
        _, payload, _ = _request(plan, "POST", "/assets", token=token, body=body,
                                 content_type=content_type, expected=(201,))
        value = json.loads(payload)
        need(isinstance(value.get("id"), str), "Immich upload did not return an asset ID")
        atomic_json(root / "fixture.json", {"asset_id": value["id"]})
        evidence = _fixture_evidence(plan, credentials, value["id"])
        context = plan["runtime"]["context"]
        docker(compose_args(plan) + ["stop", "--timeout", "30", "immich-machine-learning"],
               context=context, timeout=120)
        try:
            without_ml = _fixture_evidence(plan, credentials, value["id"])
            need(without_ml == evidence, "Original browsing changed while ML was stopped")
        finally:
            docker(compose_args(plan) + ["start", "immich-machine-learning"], context=context)
            wait_health(plan, ("immich-machine-learning",))
        return {"operation": "upload-download-ml-isolation", "status": "passed",
                **evidence, "machine_learning_independent": True,
                "machine_learning_limits": plan["limits"]["immich-machine-learning"]}


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def tree_files(root, *, protect_new=False):
    root = safe_path(root)
    verify_private(root, directory=True)
    paths = sorted(root.rglob("*"))
    result = {}
    for path in paths:
        safe_path(path)
        info = path.stat()
        need(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode),
             "Unexpected backup resource")
        need(path.is_dir() or info.st_nlink == 1, "Hard-linked backup files refused")
        if os.name != "nt":
            if protect_new:
                path.chmod(0o700 if path.is_dir() else 0o600)
            verify_private(path, directory=path.is_dir())
    if os.name == "nt":
        windows_tree_acl(root, create=protect_new)
    for path in paths:
        if path.is_file():
            result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def backup_summary(manifest):
    trees = manifest["trees"]
    return {"original_files": sum(len(value) for value in trees.values()),
            "original_bytes": sum(item["bytes"] for item in manifest["file_inventory"]),
            "fixture_sha256": manifest["fixture"]["sha256"],
            "derived_included": False, "ml_cache_included": False}


def verify_backup(root):
    root = safe_path(Path(root))
    verify_private(root, directory=True)
    manifest = read_private(root / "manifest.json")
    keys(manifest, {"kind", "created_utc", "images", "method",
                    "authoritative_material", "derived_material", "cache_material",
                    "system_markers",
                    "consistency", "recovery_status", "credentials_hash",
                    "configuration_sha256", "database_sha256", "trees",
                    "file_inventory", "fixture", "summary"}, "Immich backup manifest")
    need(manifest["kind"] == "immich-consistent-backup-v1"
         and manifest["images"] == images()
         and manifest["method"] == "quiesced-postgres-protected-originals",
         "Backup image/format mismatch")
    need(manifest["authoritative_material"] == ["postgres-custom-dump", *AUTHORITATIVE_AREAS]
         and manifest["derived_material"] == list(DERIVED_AREAS)
         and manifest["cache_material"] == ["redis-data", "model-cache"],
         "Immich backup storage classification changed")
    marker_hashes = {}
    for name in DERIVED_AREAS:
        marker = root / "system-markers" / name / SYSTEM_MARKER
        need(marker.is_file() and marker.stat().st_size > 0,
             "Immich system-integrity marker is missing")
        marker_hashes[name] = file_hash(marker)
    need(manifest["system_markers"] == marker_hashes,
         "Immich system-integrity marker checksum mismatch")
    need(manifest["consistency"] == {"server_quiesced": True, "ml_quiesced": True,
                                     "postgres_archive_readable": True,
                                     "protected_originals_complete": True}
         and manifest["recovery_status"] == "pending-independent-restore",
         "Backup consistency/recovery evidence is incomplete")
    credentials = validate_credentials(read_private(root / "credentials.json"))
    need(digest(credentials) == manifest["credentials_hash"],
         "Backup credential checksum mismatch")
    need(file_hash(root / "immich-postgres.dump") == manifest["database_sha256"],
         "PostgreSQL dump checksum mismatch")
    need(manifest["configuration_sha256"] == {
        "private": file_hash(root / "compose.private.json"),
        "sanitized": file_hash(root / "sanitized-config.json")},
        "Backup configuration checksum mismatch")
    expected = {name: tree_files(root / "filesystem" / name)
                for name in AUTHORITATIVE_AREAS}
    need(expected == manifest["trees"], "Protected-original checksum mismatch")
    inventory = []
    for area, values in expected.items():
        for relative, sha256 in values.items():
            path = root / "filesystem" / area / relative
            inventory.append({"path": f"{area}/{relative}", "bytes": path.stat().st_size,
                              "sha256": sha256})
    need(inventory == manifest["file_inventory"], "Protected-original inventory mismatch")
    need(manifest["fixture"]["filename"] == FIXTURE_NAME
         and manifest["fixture"]["sha256"] == hashlib.sha256(FIXTURE_BODY).hexdigest()
         and manifest["fixture"]["bytes"] == len(FIXTURE_BODY)
         and manifest["fixture"]["original_verified"] is True,
         "Backup lacks nonempty Immich original evidence")
    need(backup_summary(manifest) == manifest["summary"], "Backup summary mismatch")
    return manifest


def backup(plan, destination, confirmation):
    validate_plan(plan)
    need(confirmation == plan["plan_id"], "Confirm the complete reviewed plan ID")
    need(local_runtime() == plan["runtime"], "Local Docker context/engine changed")
    root = Path(plan["root"])
    destination = safe_path(Path(destination))
    need(not destination.is_relative_to(root) and not root.is_relative_to(destination),
         "Backup and installation must not overlap")
    need(not destination.exists() and destination.parent.is_dir(),
         "Backup requires an absent destination under an existing parent")
    with operation_lock(root / "operation.lock"):
        state = state_read(plan)
        resources = inventory(plan, state["owner"])
        need(state["status"] == "running" and set(resources["containers"]) == set(SERVICES)
             and all(row["State"]["Running"] for row in resources["containers"].values()),
             "Start the complete owned Immich project before backup")
        credentials = read_private(root / "credentials.json")
        fixture = _fixture_evidence(plan, credentials)
        context = plan["runtime"]["context"]
        database = resources["containers"]["database"]["Id"]
        server = resources["containers"]["immich-server"]["Id"]
        stopped = False
        failed_stage = "quiesce"
        create_private_directory(destination)
        try:
            docker(compose_args(plan) + ["stop", "--timeout", "60",
                                         "immich-server", "immich-machine-learning"],
                   context=context, timeout=180)
            stopped = True
            dump_target = "/tmp/immich-" + uuid.uuid4().hex + ".dump"
            failed_stage = "postgres-dump"
            docker(["exec", database, "pg_dump", "-U", "postgres", "-d", "immich",
                    "--format", "custom", "--file", dump_target],
                   context=context, timeout=600)
            failed_stage = "postgres-archive-check"
            docker(["exec", database, "pg_restore", "--list", dump_target],
                   context=context, timeout=120)
            docker(["cp", database + ":" + dump_target,
                    str(destination / "immich-postgres.dump")],
                   context=context, timeout=180)
            docker(["exec", database, "rm", "-f", dump_target], context=context)
            failed_stage = "protected-original-copy"
            create_private_directory(destination / "filesystem")
            for name, source in AUTHORITATIVE_AREAS.items():
                create_private_directory(destination / "filesystem" / name)
                docker(["cp", server + ":" + source + "/.",
                        str(destination / "filesystem" / name)],
                       context=context, timeout=600)
            create_private_directory(destination / "system-markers")
            for name in DERIVED_AREAS:
                create_private_directory(destination / "system-markers" / name)
                docker(["cp", server + f":/data/{name}/{SYSTEM_MARKER}",
                        str(destination / "system-markers" / name / SYSTEM_MARKER)],
                       context=context, timeout=120)
            failed_stage = "metadata-copy"
            shutil.copy2(root / "credentials.json", destination / "credentials.json")
            shutil.copy2(root / "compose.json", destination / "compose.private.json")
            shutil.copy2(root / "fixture.json", destination / "fixture.json")
            atomic_json(destination / "sanitized-config.json", {
                "kind": "immich-sanitized-configuration-v1",
                "images": plan["images"], "limits": plan["limits"],
                "machine_learning": plan["machine_learning"],
                "access": plan["access"], "public_registration": False,
                "external_libraries": plan["external_libraries"],
                "recovery_method": plan["recovery_method"],
            })
            tree_files(destination / "filesystem", protect_new=True)
            tree_files(destination / "system-markers", protect_new=True)
            protected = ("credentials.json", "compose.private.json", "fixture.json",
                         "immich-postgres.dump")
            for name in protected:
                path = destination / name
                if os.name == "nt":
                    windows_acl(path, create=True)
                else:
                    path.chmod(0o600)
                verify_private(path)
            trees = {name: tree_files(destination / "filesystem" / name)
                     for name in AUTHORITATIVE_AREAS}
            system_markers = {
                name: file_hash(destination / "system-markers" / name / SYSTEM_MARKER)
                for name in DERIVED_AREAS
            }
            file_inventory = []
            for area, values in trees.items():
                for relative, sha256 in values.items():
                    path = destination / "filesystem" / area / relative
                    file_inventory.append({"path": f"{area}/{relative}",
                                           "bytes": path.stat().st_size,
                                           "sha256": sha256})
            manifest = {
                "kind": "immich-consistent-backup-v1",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "images": plan["images"],
                "method": "quiesced-postgres-protected-originals",
                "authoritative_material": ["postgres-custom-dump", *AUTHORITATIVE_AREAS],
                "derived_material": list(DERIVED_AREAS),
                "cache_material": ["redis-data", "model-cache"],
                "system_markers": system_markers,
                "consistency": {"server_quiesced": True, "ml_quiesced": True,
                                "postgres_archive_readable": True,
                                "protected_originals_complete": True},
                "recovery_status": "pending-independent-restore",
                "credentials_hash": digest(read_private(destination / "credentials.json")),
                "configuration_sha256": {
                    "private": file_hash(destination / "compose.private.json"),
                    "sanitized": file_hash(destination / "sanitized-config.json")},
                "database_sha256": file_hash(destination / "immich-postgres.dump"),
                "trees": trees, "file_inventory": file_inventory,
                "fixture": fixture, "summary": None,
            }
            manifest["summary"] = backup_summary(manifest)
            atomic_json(destination / "manifest.json", manifest)
            failed_stage = "manifest-verification"
            verify_backup(destination)
        except ConfigError as error:
            raise ConfigError("Immich backup failed during " + failed_stage
                              + "; sensitive partial state was retained for review") from error
        finally:
            if stopped:
                docker(compose_args(plan) + ["start", "immich-server",
                                             "immich-machine-learning"], context=context)
                wait_health(plan, ("immich-server", "immich-machine-learning"))
        return {"backup_complete": True, "application_consistent": True,
                "protected_originals": True, "derived_excluded": True,
                "machine_learning_cache_excluded": True, "encrypted": False,
                "contains_credentials": True, "summary": manifest["summary"],
                "recovery_verified": False,
                "note": "Sensitive staging backup; independently restore before encrypted retention"}
