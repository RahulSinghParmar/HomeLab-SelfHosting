"""Windows-only Beszel agent upgrade adapter with secret-safe service fingerprints."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time

from .config import ROOT, ConfigError, canonical, keys, need
from .privatefs import atomic_json, create_private_directory, create_lock_file, operation_lock, safe_path
from .sandbox import digest


CONTRACT = "beszel-windows-existing-v1"
DEFAULT_SERVICE = "BeszelAgent"
def file_sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def pe_architecture(path: Path) -> str:
    need(path.is_file() and path.suffix.lower() == ".exe", "Candidate must be a Windows executable")
    need(0 < path.stat().st_size <= 100 * 1024 * 1024, "Candidate executable size is invalid")
    with path.open("rb") as source:
        header = source.read(64)
        need(len(header) == 64 and header[:2] == b"MZ", "Candidate has no valid PE header")
        offset = struct.unpack_from("<I", header, 0x3C)[0]
        need(64 <= offset <= 16 * 1024 * 1024, "Candidate PE header offset is invalid")
        source.seek(offset)
        pe = source.read(6)
    need(pe[:4] == b"PE\0\0", "Candidate has no valid PE signature")
    machine = struct.unpack_from("<H", pe, 4)[0]
    need(machine == 0x8664, "Only the reviewed Windows amd64 agent is supported")
    return "amd64"


def _environment(entries) -> tuple[list[str], str]:
    raw = [str(entry) for entry in (entries or [])]
    names = []
    for entry in raw:
        name = entry.split("=", 1)[0].strip()
        need(bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)), "Unexpected NSSM environment entry")
        names.append(name.upper())
    need(len(names) == len(set(names)), "Duplicate NSSM environment variable")
    # Values stay local. The hash binds later operations to the exact configuration.
    return sorted(names), digest(sorted(raw))


def read_service(service: str = DEFAULT_SERVICE) -> dict:
    need(os.name == "nt", "The Beszel Windows adapter only runs on Windows")
    need(bool(re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", service)), "Invalid Windows service name")
    try:
        import winreg
        base_path = rf"SYSTEM\CurrentControlSet\Services\{service}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path) as base:
            wrapper = winreg.QueryValueEx(base, "ImagePath")[0]
            start = winreg.QueryValueEx(base, "Start")[0]
            account = winreg.QueryValueEx(base, "ObjectName")[0]
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path + r"\Parameters") as parameters:
            application = winreg.QueryValueEx(parameters, "Application")[0]
            directory = winreg.QueryValueEx(parameters, "AppDirectory")[0]
            try:
                environment = winreg.QueryValueEx(parameters, "AppEnvironmentExtra")[0]
            except FileNotFoundError:
                environment = []
    except (FileNotFoundError, OSError) as error:
        raise ConfigError("Beszel NSSM service configuration is unavailable") from error
    names, environment_hash = _environment(environment)
    target = Path(application).resolve()
    need(target.is_file(), "Configured Beszel agent executable is missing")
    need("nssm" in str(wrapper).lower(), "Only an existing NSSM-managed Beszel service is supported")
    need(start == 2, "Beszel service must use automatic startup")
    need(any(name in names for name in ("KEY", "TOKEN")), "Beszel service has no KEY or TOKEN configuration")
    snapshot = {
        "service": service,
        "wrapper": str(wrapper),
        "application": str(target),
        "application_directory": str(Path(directory).resolve()),
        "start_mode": "automatic",
        "account": str(account),
        "environment_names": names,
        "environment_hash": environment_hash,
        "binary_sha256": file_sha256(target),
        "binary_architecture": pe_architecture(target),
    }
    snapshot["fingerprint"] = digest(snapshot)
    return snapshot


def public_snapshot(snapshot: dict) -> dict:
    keys(snapshot, {"service", "wrapper", "application", "application_directory", "start_mode", "account",
                    "environment_names", "environment_hash", "binary_sha256", "binary_architecture", "fingerprint"},
         "Windows service snapshot")
    return {
        "service": snapshot["service"],
        "start_mode": snapshot["start_mode"],
        "account": snapshot["account"],
        "environment_names": snapshot["environment_names"],
        "binary_sha256": snapshot["binary_sha256"],
        "binary_architecture": snapshot["binary_architecture"],
        "configuration_fingerprint": snapshot["fingerprint"],
        "paths": "redacted",
        "environment_values": "never-reported",
    }


def make_plan(candidate, backup_root, service=DEFAULT_SERVICE, snapshot=None):
    candidate = safe_path(Path(candidate))
    backup_root = safe_path(Path(backup_root))
    need(candidate.is_file(), "Candidate Beszel agent does not exist")
    need(backup_root.is_dir(), "Backup root must already exist")
    need(not candidate.is_relative_to(ROOT), "Candidate binary must stay outside the public repository")
    architecture = pe_architecture(candidate)
    current = snapshot if snapshot is not None else read_service(service)
    keys(current, {"service", "wrapper", "application", "application_directory", "start_mode", "account",
                   "environment_names", "environment_hash", "binary_sha256", "binary_architecture", "fingerprint"},
         "Windows service snapshot")
    need(current["service"] == service and current["binary_architecture"] == "amd64", "Unexpected service snapshot")
    target = Path(current["application"])
    need(not backup_root.is_relative_to(target.parent), "Backup root must be outside the live agent directory")
    plan = {
        "kind": "homelab-beszel-windows-plan",
        "contract": CONTRACT,
        "service": service,
        "candidate": {"path": str(candidate), "sha256": file_sha256(candidate), "architecture": architecture},
        "backup_root": str(backup_root),
        "expected_service": current,
        "operation": "replace-existing-agent-binary-only",
        "configuration_values": "preserved-not-recorded",
    }
    plan["plan_id"] = digest(plan)
    plan["backup_directory"] = str(backup_root / ("beszel-windows-" + plan["plan_id"][:16]))
    return plan


def validate_plan(plan):
    keys(plan, {"kind", "contract", "service", "candidate", "backup_root", "expected_service", "operation",
                "configuration_values", "plan_id", "backup_directory"}, "Beszel Windows plan")
    need(plan["kind"] == "homelab-beszel-windows-plan" and plan["contract"] == CONTRACT,
         "Unsupported Beszel Windows plan")
    expected_id = plan["plan_id"]
    base = {key: value for key, value in plan.items() if key not in ("plan_id", "backup_directory")}
    need(digest(base) == expected_id, "Beszel Windows plan was modified")
    need(Path(plan["backup_directory"]) == Path(plan["backup_root"]) / ("beszel-windows-" + expected_id[:16]),
         "Backup destination drift")
    candidate = safe_path(Path(plan["candidate"]["path"]))
    need(pe_architecture(candidate) == plan["candidate"]["architecture"]
         and file_sha256(candidate) == plan["candidate"]["sha256"], "Candidate binary drift")
    return plan


def status(plan, snapshot=None):
    validate_plan(plan)
    current = snapshot if snapshot is not None else read_service(plan["service"])
    changed = [name for name in ("wrapper", "application", "application_directory", "start_mode", "account",
                                  "environment_names", "environment_hash", "binary_architecture")
               if current.get(name) != plan["expected_service"].get(name)]
    target_hash = current.get("binary_sha256")
    return {
        "module": "beszel-windows-host",
        "service": plan["service"],
        "service_configuration": "matching" if not changed else "drifted",
        "changed_fields": changed,
        "binary": "candidate-installed" if target_hash == plan["candidate"]["sha256"] else "original-installed",
        "service_state": service_state(plan["service"]) if snapshot is None else "test-snapshot",
        "backup": "present" if Path(plan["backup_directory"]).is_dir() else "not-created",
        "environment_values": "never-reported",
    }


def service_state(service: str) -> str:
    result = subprocess.run(["sc.exe", "query", service], capture_output=True, text=True, timeout=15,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    need(result.returncode == 0, "Windows could not query the Beszel service")
    text = result.stdout.upper()
    return "running" if "RUNNING" in text else "stopped" if "STOPPED" in text else "transitioning"


def _admin() -> bool:
    return os.name == "nt" and bool(ctypes.windll.shell32.IsUserAnAdmin())


def _control(service: str, action: str, expected: str) -> None:
    need(action in ("start", "stop"), "Unsupported service operation")
    result = subprocess.run(["sc.exe", action, service], capture_output=True, text=True, timeout=15,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    need(result.returncode in (0, 1062) if action == "stop" else result.returncode in (0, 1056),
         "Windows service control failed")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if service_state(service) == expected:
            return
        time.sleep(1)
    raise ConfigError("Beszel service did not reach " + expected)


def apply(plan, confirmation):
    validate_plan(plan)
    need(confirmation == plan["plan_id"], "Confirm the complete reviewed plan ID")
    need(_admin(), "Run the apply command from an elevated terminal")
    backup = Path(plan["backup_directory"])
    lock = Path(plan["backup_root"]) / ("." + plan["service"] + ".upgrade.lock")
    if not lock.exists():
        create_lock_file(lock)
    with operation_lock(lock):
        current = read_service(plan["service"])
        report = status(plan, current)
        need(report["service_configuration"] == "matching", "Service configuration drift; create and review a new plan")
        if report["binary"] == "candidate-installed":
            return {**report, "changed": False, "rollback_available": backup.is_dir()}
        need(not backup.exists(), "Backup destination already exists; preserve it and review")
        create_private_directory(backup)
        target = Path(current["application"])
        original = backup / "beszel-agent.exe"
        shutil.copy2(target, original)
        manifest = {"kind": "beszel-windows-backup-v1", "plan_id": plan["plan_id"],
                    "service_fingerprint": current["fingerprint"], "binary_sha256": file_sha256(original)}
        atomic_json(backup / "manifest.json", manifest)
        try:
            if service_state(plan["service"]) == "running":
                _control(plan["service"], "stop", "stopped")
            temporary = target.with_name(target.name + ".homelab-new")
            shutil.copy2(plan["candidate"]["path"], temporary)
            need(file_sha256(temporary) == plan["candidate"]["sha256"], "Staged binary hash mismatch")
            os.replace(temporary, target)
            _control(plan["service"], "start", "running")
            need(file_sha256(target) == plan["candidate"]["sha256"], "Installed binary hash mismatch")
        except Exception:
            try:
                if service_state(plan["service"]) == "running":
                    _control(plan["service"], "stop", "stopped")
                shutil.copy2(original, target)
                _control(plan["service"], "start", "running")
            finally:
                raise
        return {**status(plan), "changed": True, "rollback_available": True}


def rollback(plan, confirmation):
    validate_plan(plan)
    need(confirmation == plan["plan_id"], "Confirm the complete reviewed plan ID")
    need(_admin(), "Run rollback from an elevated terminal")
    backup = Path(plan["backup_directory"])
    manifest_path, original = backup / "manifest.json", backup / "beszel-agent.exe"
    need(manifest_path.is_file() and original.is_file(), "Verified rollback backup is unavailable")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    keys(manifest, {"kind", "plan_id", "service_fingerprint", "binary_sha256"}, "Beszel Windows backup")
    need(manifest["kind"] == "beszel-windows-backup-v1" and manifest["plan_id"] == plan["plan_id"]
         and file_sha256(original) == manifest["binary_sha256"], "Rollback backup verification failed")
    current = read_service(plan["service"])
    need(status(plan, current)["service_configuration"] == "matching",
         "Service configuration drift; create and review a new plan")
    need(current["binary_sha256"] == plan["candidate"]["sha256"], "Current binary is not the planned candidate")
    target = Path(current["application"])
    if service_state(plan["service"]) == "running":
        _control(plan["service"], "stop", "stopped")
    shutil.copy2(original, target)
    _control(plan["service"], "start", "running")
    need(file_sha256(target) == manifest["binary_sha256"], "Rollback binary hash mismatch")
    return {"module": "beszel-windows-host", "rolled_back": True, "service_state": "running",
            "backup_retained": True}
