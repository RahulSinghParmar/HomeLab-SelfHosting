"""Explicit, backup-gated Docker Compose image update management."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .config import ConfigError


CONTRACT = 1
ROLLING_TAGS = {"latest", "stable", "edge", "main", "master", "develop", "nightly"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute_path(value: str) -> bool:
    return (Path(value).is_absolute() or PureWindowsPath(value).is_absolute()
            or PurePosixPath(value).is_absolute())


def _run(arguments: list[str], *, timeout: int = 120) -> str:
    try:
        result = subprocess.run(
            arguments, check=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ConfigError(f"Command could not run safely: {arguments[0]}") from error
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise ConfigError(f"Command failed: {' '.join(arguments[:3])}{suffix}")
    return result.stdout


def load_policy(path: Path) -> dict:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError("Update policy is not readable JSON") from error
    if policy.get("schema_version") != CONTRACT:
        raise ConfigError("Unsupported update-policy schema")
    if not isinstance(policy.get("projects", {}), dict):
        raise ConfigError("Update policy projects must be an object")
    raw_root = policy.get("state_root", "")
    if not _absolute_path(raw_root):
        raise ConfigError("Update policy state_root must be absolute")
    return policy


def _json_rows(text: str) -> list[dict]:
    text = text.strip()
    if not text:
        return []
    try:
        value = json.loads(text)
        return value if isinstance(value, list) else [value]
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            rows.append(json.loads(line))
        return rows


def _project_rule(policy: dict, name: str, files: list[str]) -> dict:
    exact = policy.get("projects", {}).get(name)
    if exact:
        return {"owner": "operator", "mode": "audit-only", **exact}
    joined = " ".join(files)
    for pattern in policy.get("controller_path_patterns", []):
        if re.search(pattern, joined):
            return {"owner": "controller", "mode": "controller-managed"}
    return {"owner": "unreviewed", "mode": policy.get("defaults", {}).get("mode", "audit-only")}


def _repository(reference: str) -> str:
    value = reference.split("@", 1)[0]
    last_slash = value.rfind("/")
    last_colon = value.rfind(":")
    if last_colon > last_slash:
        value = value[:last_colon]
    if "/" not in value:
        value = "docker.io/library/" + value
    elif value.split("/", 1)[0].find(".") < 0 and ":" not in value.split("/", 1)[0]:
        value = "docker.io/" + value
    return value.lower()


def _tag(reference: str) -> str | None:
    if "@" in reference:
        return None
    last = reference.rsplit("/", 1)[-1]
    return last.rsplit(":", 1)[1] if ":" in last else "latest"


def _exact_target(reference: str) -> bool:
    if "@sha256:" in reference:
        return True
    tag = _tag(reference)
    return bool(tag and tag.lower() not in ROLLING_TAGS)


def _remote_digest(reference: str) -> dict:
    try:
        output = _run(["docker", "buildx", "imagetools", "inspect", reference], timeout=90)
        match = re.search(r"(?m)^Digest:\s+(sha256:[0-9a-f]{64})\s*$", output)
        if not match:
            return {"status": "unverifiable", "error": "remote digest absent"}
        return {"status": "checked", "digest": match.group(1)}
    except ConfigError as error:
        return {"status": "unavailable", "error": str(error)}


def inspect_remote(reference: str) -> dict:
    digest = _remote_digest(reference)
    if digest["status"] != "checked":
        return {"image": reference, **digest}
    try:
        raw = _run([
            "docker", "buildx", "imagetools", "inspect", reference,
            "--format", "{{json .Image}}",
        ], timeout=90)
        images = json.loads(raw)
        image = images.get("linux/amd64") if isinstance(images, dict) else None
        if image is None and isinstance(images, dict) and "config" in images:
            image = images
        labels = (image or {}).get("config", {}).get("Labels", {}) or {}
        return {
            "image": reference,
            **digest,
            "platform": "linux/amd64" if image else "unknown",
            "version": labels.get("org.opencontainers.image.version"),
            "revision": labels.get("org.opencontainers.image.revision"),
            "created": (image or {}).get("created"),
        }
    except (ConfigError, json.JSONDecodeError):
        return {"image": reference, **digest, "platform": "unknown"}


def audit(policy: dict, *, online: bool = False, workers: int = 4) -> dict:
    _run(["docker", "info", "--format", "{{json .ServerVersion}}"], timeout=30)
    projects = _json_rows(_run(["docker", "compose", "ls", "--all", "--format", "json"]))
    container_ids = [row for row in _run(["docker", "ps", "-aq"]).splitlines() if row]
    containers = json.loads(_run(["docker", "inspect", *container_ids])) if container_ids else []
    by_project: dict[str, list[dict]] = {}
    image_cache: dict[str, dict] = {}
    for item in containers:
        labels = item.get("Config", {}).get("Labels") or {}
        project = labels.get("com.docker.compose.project")
        service = labels.get("com.docker.compose.service")
        if not project or not service:
            continue
        image_id = item.get("Image", "")
        if image_id not in image_cache:
            try:
                local = json.loads(_run(["docker", "image", "inspect", image_id]))[0]
                image_cache[image_id] = {
                    "repo_digests": local.get("RepoDigests") or [],
                    "labels": local.get("Config", {}).get("Labels") or {},
                }
            except (ConfigError, KeyError, IndexError, json.JSONDecodeError):
                image_cache[image_id] = {"repo_digests": [], "labels": {}}
        state = item.get("State", {})
        local = image_cache[image_id]
        by_project.setdefault(project, []).append({
            "service": service,
            "container": item.get("Name", "").lstrip("/"),
            "image": item.get("Config", {}).get("Image", ""),
            "image_id": image_id,
            "version": local["labels"].get("org.opencontainers.image.version"),
            "revision": local["labels"].get("org.opencontainers.image.revision"),
            "repo_digests": local["repo_digests"],
            "state": state.get("Status"),
            "health": (state.get("Health") or {}).get("Status"),
        })
    project_rows = []
    remote_refs = sorted({
        service["image"] for services in by_project.values() for service in services
        if service["image"] and not service["image"].startswith(("localhost/", "local/"))
        and "@sha256:" not in service["image"]
    })
    remote: dict[str, dict] = {}
    if online:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
            future_map = {pool.submit(_remote_digest, ref): ref for ref in remote_refs}
            for future in concurrent.futures.as_completed(future_map):
                remote[future_map[future]] = future.result()
    listed = {row.get("Name"): row for row in projects}
    names = sorted(set(listed) | set(by_project))
    summary = {"projects": len(names), "services": 0, "current": 0, "updates_available": 0,
               "pinned": 0, "local": 0, "unchecked": 0, "unverifiable": 0,
               "unavailable": 0, "non_running": 0}
    for name in names:
        listed_row = listed.get(name, {})
        raw_files = listed_row.get("ConfigFiles", "")
        files = [part.strip() for part in raw_files.split(",") if part.strip()]
        rule = _project_rule(policy, name, files)
        services = sorted(by_project.get(name, []), key=lambda row: row["service"])
        for service in services:
            summary["services"] += 1
            if service["state"] != "running":
                summary["non_running"] += 1
            ref = service["image"]
            if ref.startswith(("localhost/", "local/")):
                status = "local"
            elif "@sha256:" in ref:
                status = "pinned"
            elif not online:
                status = "unchecked"
            else:
                check = remote.get(ref, {"status": "unavailable"})
                if check.get("status") != "checked":
                    status = check.get("status", "unavailable")
                elif any(value.endswith("@" + check["digest"]) for value in service["repo_digests"]):
                    status = "current"
                else:
                    status = "update_available"
                service["remote_digest"] = check.get("digest")
                service["remote_error"] = check.get("error")
            service["update_status"] = status
            key = {"update_available": "updates_available"}.get(status, status)
            if key in summary:
                summary[key] += 1
        project_rows.append({
            "name": name,
            "status": listed_row.get("Status", "not-listed"),
            "config_files": files,
            "owner": rule["owner"],
            "mode": rule["mode"],
            "services": services,
        })
    return {
        "kind": "homelab-docker-update-audit",
        "contract": CONTRACT,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "online_registry_check": online,
        "summary": summary,
        "projects": project_rows,
    }


def make_plan(audit_report: dict, policy: dict, project: str, service: str,
              target_image: str, target_remote: dict | None = None) -> dict:
    if audit_report.get("kind") != "homelab-docker-update-audit":
        raise ConfigError("Expected a Docker update audit")
    project_row = next((row for row in audit_report["projects"] if row["name"] == project), None)
    if not project_row:
        raise ConfigError("Project is absent from the audit")
    service_rows = [row for row in project_row["services"] if row["service"] == service]
    if not service_rows:
        raise ConfigError("Service is absent from the audited project")
    if len(service_rows) != 1:
        raise ConfigError("Managed apply requires exactly one container for the selected service")
    service_row = service_rows[0]
    rule = policy.get("projects", {}).get(project, {})
    service_rule = rule.get("services", {}).get(service)
    if project_row.get("owner") != "operator" or rule.get("mode") != "manual":
        raise ConfigError("Project is audit-only or controller-managed")
    if not service_rule or not service_rule.get("enabled", False):
        raise ConfigError("Service has not been explicitly enabled for managed updates")
    if not _exact_target(target_image):
        raise ConfigError("Target image must use an exact version tag or sha256 digest")
    if _repository(service_row["image"]) != _repository(target_image):
        raise ConfigError("Target image repository differs from the running service")
    target_remote = target_remote or _remote_digest(target_image)
    if target_remote.get("status") != "checked" or not target_remote.get("digest"):
        raise ConfigError("Target image digest could not be verified in the registry")
    if "@sha256:" in target_image and not target_image.endswith("@" + target_remote["digest"]):
        raise ConfigError("Target digest differs from the registry response")
    files = project_row.get("config_files", [])
    if len(files) != 1:
        raise ConfigError("Managed apply currently requires exactly one Compose source file")
    compose_file = Path(files[0])
    if not compose_file.is_file():
        raise ConfigError("Compose source file is unavailable")
    backup_paths = [str(Path(value)) for value in service_rule.get("backup_paths", [])]
    if any(not _absolute_path(value) for value in backup_paths):
        raise ConfigError("Backup paths must be absolute")
    if service_rule.get("backup_required", True) and not backup_paths:
        raise ConfigError("Service needs an application-specific backup policy before updates")
    timeout = int(service_rule.get("health_timeout_seconds", 180))
    if not 30 <= timeout <= 900:
        raise ConfigError("Health timeout must be between 30 and 900 seconds")
    body = {
        "kind": "homelab-docker-update-plan",
        "contract": CONTRACT,
        "project": project,
        "service": service,
        "compose_file": str(compose_file),
        "compose_sha256": _file_sha(compose_file),
        "source_image": service_row["image"],
        "source_image_id": service_row["image_id"],
        "target_image": target_image,
        "target_remote_digest": target_remote["digest"],
        "backup_paths": backup_paths,
        "backup_required": service_rule.get("backup_required", True),
        "health_url": service_rule.get("health_url"),
        "health_timeout_seconds": timeout,
        "state_root": policy["state_root"],
        "automatic": False,
    }
    return {**body, "plan_id": _sha(body)}


def validate_plan(plan: dict) -> dict:
    if plan.get("kind") != "homelab-docker-update-plan" or plan.get("contract") != CONTRACT:
        raise ConfigError("Unsupported Docker update plan")
    body = {key: value for key, value in plan.items() if key != "plan_id"}
    if plan.get("plan_id") != _sha(body):
        raise ConfigError("Docker update plan changed after review")
    if plan.get("automatic") is not False or not _exact_target(plan.get("target_image", "")):
        raise ConfigError("Docker update plan is not explicit and bounded")
    return plan


def replace_service_image(text: str, service: str, target: str) -> str:
    lines = text.splitlines(keepends=True)
    services_index = next((index for index, line in enumerate(lines)
                           if re.match(r"^services:\s*(?:#.*)?(?:\r?\n)?$", line)), None)
    if services_index is None:
        raise ConfigError("Compose file has no top-level services mapping")
    match_index = None
    match_indent = None
    service_pattern = re.compile(rf"^(\s+){re.escape(service)}:\s*(?:#.*)?(?:\r?\n)?$")
    for index in range(services_index + 1, len(lines)):
        match = service_pattern.match(lines[index])
        if match:
            if match_index is not None:
                raise ConfigError("Compose service is duplicated")
            match_index, match_indent = index, len(match.group(1))
    if match_index is None or match_indent is None:
        raise ConfigError("Compose service block was not found")
    end = len(lines)
    for index in range(match_index + 1, len(lines)):
        stripped = lines[index].lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(lines[index]) - len(stripped)
        if indent <= match_indent:
            end = index
            break
    image_rows = []
    image_pattern = re.compile(r"^(\s+)image:\s*[^#\r\n]+?(\s*(?:#.*)?)?(\r?\n)?$")
    for index in range(match_index + 1, end):
        match = image_pattern.match(lines[index])
        if match and len(match.group(1)) > match_indent:
            image_rows.append((index, match))
    if len(image_rows) != 1:
        raise ConfigError("Compose service must contain exactly one simple image field")
    index, match = image_rows[0]
    comment = match.group(2) or ""
    newline = match.group(3) or ""
    lines[index] = f"{match.group(1)}image: {target}{comment}{newline}"
    return "".join(lines)


def _container_for(project: str, service: str) -> dict | None:
    ids = [row for row in _run([
        "docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}",
        "--filter", f"label=com.docker.compose.service={service}",
    ]).splitlines() if row]
    if len(ids) != 1:
        return None
    return json.loads(_run(["docker", "inspect", ids[0]]))[0]


def _healthy(plan: dict) -> bool:
    deadline = time.monotonic() + plan["health_timeout_seconds"]
    while time.monotonic() < deadline:
        item = _container_for(plan["project"], plan["service"])
        if item:
            state = item.get("State", {})
            health = (state.get("Health") or {}).get("Status")
            if state.get("Status") == "running" and health in (None, "healthy"):
                if plan.get("health_url"):
                    try:
                        with urllib.request.urlopen(plan["health_url"], timeout=10) as response:
                            if 200 <= response.status < 400:
                                return True
                    except OSError:
                        pass
                else:
                    return True
        time.sleep(3)
    return False


def _path_manifest(path: Path) -> dict[str, str]:
    if path.is_file():
        return {".": _file_sha(path)}
    return {
        file.relative_to(path).as_posix(): _file_sha(file)
        for file in sorted(path.rglob("*")) if file.is_file()
    }


def apply(plan: dict, confirmation: str) -> dict:
    plan = validate_plan(plan)
    if confirmation != plan["plan_id"]:
        raise ConfigError("Confirmation must equal the full reviewed plan ID")
    compose_file = Path(plan["compose_file"])
    if _file_sha(compose_file) != plan["compose_sha256"]:
        raise ConfigError("Compose source changed after the plan was created")
    item = _container_for(plan["project"], plan["service"])
    if not item or item.get("Image") != plan["source_image_id"]:
        raise ConfigError("Running service image changed after the audit")
    state_root = Path(plan["state_root"])
    state_root.mkdir(parents=True, exist_ok=True)
    lock = state_root / f".{plan['project']}-{plan['service']}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    except FileExistsError as error:
        raise ConfigError("Another update for this service is already active") from error
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    recovery = state_root / f"{stamp}-{plan['project']}-{plan['service']}-{plan['plan_id'][:12]}"
    recovery.mkdir(parents=True)
    compose_backup = recovery / compose_file.name
    shutil.copy2(compose_file, compose_backup)
    journal = {"plan_id": plan["plan_id"], "status": "started", "recovery": str(recovery)}
    update_attempted = False
    try:
        _run(["docker", "pull", plan["target_image"]], timeout=900)
        pulled = json.loads(_run(["docker", "image", "inspect", plan["target_image"]]))[0]
        pulled_digests = pulled.get("RepoDigests") or []
        if not any(value.endswith("@" + plan["target_remote_digest"])
                   for value in pulled_digests):
            raise ConfigError("Pulled target digest differs from the reviewed plan")
        if plan["backup_paths"]:
            _run(["docker", "compose", "-f", str(compose_file), "stop", "-t", "60", plan["service"]])
            backup_root = recovery / "application-backup"
            backup_root.mkdir()
            for index, raw in enumerate(plan["backup_paths"]):
                source = Path(raw)
                if not source.exists():
                    raise ConfigError(f"Backup path is missing: {source}")
                destination = backup_root / f"{index:02d}-{source.name}"
                if source.is_dir():
                    shutil.copytree(source, destination)
                else:
                    shutil.copy2(source, destination)
                source_manifest = _path_manifest(source)
                backup_manifest = _path_manifest(destination)
                if source_manifest != backup_manifest:
                    raise ConfigError(f"Backup verification failed: {source}")
                journal.setdefault("backups", []).append({
                    "source": str(source), "copy": str(destination),
                    "files": len(backup_manifest),
                    "manifest_sha256": _sha(backup_manifest),
                })
        updated = replace_service_image(
            compose_file.read_text(encoding="utf-8"), plan["service"], plan["target_image"])
        temporary = compose_file.with_suffix(compose_file.suffix + ".update.tmp")
        temporary.write_text(updated, encoding="utf-8", newline="")
        os.replace(temporary, compose_file)
        _run(["docker", "compose", "-f", str(compose_file), "config", "--quiet"])
        update_attempted = True
        _run([
            "docker", "compose", "-f", str(compose_file), "up", "-d", "--no-deps",
            "--force-recreate", "--pull", "never", plan["service"],
        ], timeout=300)
        if not _healthy(plan):
            journal["status"] = "manual-recovery-required"
            journal["reason"] = "updated service did not pass health validation"
            (recovery / "journal.json").write_text(json.dumps(journal, indent=2), encoding="utf-8")
            raise ConfigError(
                "Updated service failed health validation; it was not auto-downgraded because "
                f"data may have migrated. Recovery set: {recovery}"
            )
        final = _container_for(plan["project"], plan["service"])
        journal.update({"status": "complete", "target_image": plan["target_image"],
                        "target_image_id": (final or {}).get("Image")})
        (recovery / "journal.json").write_text(json.dumps(journal, indent=2), encoding="utf-8")
        return journal
    except Exception:
        if journal["status"] == "started" and not update_attempted:
            shutil.copy2(compose_backup, compose_file)
            journal["status"] = "failed-before-validated-start"
            (recovery / "journal.json").write_text(json.dumps(journal, indent=2), encoding="utf-8")
            try:
                _run(["docker", "compose", "-f", str(compose_file), "up", "-d", "--no-deps",
                      "--pull", "never", plan["service"]], timeout=300)
            except ConfigError:
                pass
        elif journal["status"] == "started":
            journal["status"] = "manual-recovery-required"
            journal["reason"] = "update start failed after a possible application migration"
            (recovery / "journal.json").write_text(json.dumps(journal, indent=2), encoding="utf-8")
        raise
    finally:
        lock.unlink(missing_ok=True)
