"""Read-only host probes. Unknown evidence never becomes a passing check."""

from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .config import ROOT, ROLES, logical_path, resolve, validate_config
from .planner import port_reservations

GIB = 1024 ** 3


def command(arguments: list[str]) -> str | None:
    """Capture only stdout; never echo arbitrary process errors or environment."""
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=8, shell=False)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def host_platform() -> str:
    return {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), "unsupported")


def host_architecture() -> str:
    return {"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine().lower(), "unsupported")


def host_memory(system: str, run=command) -> tuple[int | None, int | None]:
    try:
        if system == "windows":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                    (name, ctypes.c_ulonglong) for name in ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
            memory = MemoryStatus()
            memory.length = ctypes.sizeof(memory)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                return memory.total, memory.available
        elif system == "linux":
            values = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, value = line.split(":", 1)
                if key in ("MemTotal", "MemAvailable"):
                    values[key] = int(value.split()[0]) * 1024
            return values.get("MemTotal"), values.get("MemAvailable")
        elif system == "macos":
            total = run(["sysctl", "-n", "hw.memsize"])
            # macOS reclaimable-memory accounting needs a separate validated adapter.
            return int(total) if total and total.isdigit() else None, None
    except (OSError, ValueError, AttributeError):
        pass
    return None, None


def local_endpoint(endpoint: object) -> bool:
    if not isinstance(endpoint, str):
        return False
    return bool(re.fullmatch(r"npipe:////\./pipe/[A-Za-z0-9_.-]+", endpoint, re.IGNORECASE)
                or (endpoint.startswith("unix:///") and not any(c in endpoint for c in ("\n", "\r", "\0", "?", "#"))))


def parse_ss(text: str) -> set[tuple[str, int]]:
    ports = set()
    for line in text.splitlines():
        columns = line.split()
        if len(columns) < 5 or columns[0] not in ("tcp", "udp"):
            raise ValueError("Unrecognized listener row")
        port = columns[4].rsplit(":", 1)[-1]
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError("Unrecognized listener port")
        ports.add((columns[0], int(port)))
    return ports


def parse_lsof(text: str) -> set[tuple[str, int]]:
    ports = set()
    protocol = None
    for line in text.splitlines():
        if line.startswith(("p", "f")):
            protocol = None
        elif line.startswith("P"):
            protocol = line[1:].lower()
        elif line.startswith("n"):
            match = re.search(r":(\d+)(?:->|$|\s)", line[1:])
            if protocol not in ("tcp", "udp") or not match:
                raise ValueError("Unrecognized listener row")
            ports.add((protocol, int(match.group(1))))
        elif line:
            raise ValueError("Unrecognized listener field")
    return ports


def host_ports(system: str, run=command) -> set[tuple[str, int]] | None:
    try:
        if system == "windows":
            script = "$ErrorActionPreference='Stop'; @(@(Get-NetTCPConnection -State Listen | ForEach-Object { @{protocol='tcp';port=$_.LocalPort} }); @(Get-NetUDPEndpoint | ForEach-Object { @{protocol='udp';port=$_.LocalPort} })) | ConvertTo-Json -Compress"
            output = run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script])
            if output is None:
                return None
            values = json.loads(output or "[]")
            if isinstance(values, dict):
                values = [values]
            if not isinstance(values, list):
                return None
            ports = set()
            for value in values:
                if not isinstance(value, dict) or value.get("protocol") not in ("tcp", "udp") or type(value.get("port")) is not int or not 1 <= value["port"] <= 65535:
                    return None
                ports.add((value["protocol"], value["port"]))
            return ports
        if system == "linux":
            output = run(["ss", "-H", "-lntu"])
            return parse_ss(output) if output is not None else None
        if system == "macos":
            output = run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-iUDP", "-FpfPn"])
            return parse_lsof(output) if output is not None else None
    except (ValueError, TypeError, KeyError):
        return None
    return None


def time_status(system: str, run=command) -> tuple[str, str]:
    if system == "linux":
        output = run(["timedatectl", "show", "--property=NTPSynchronized", "--value"])
        if output == "yes":
            return "pass", "OS reports NTP synchronized; not an independent offset measurement"
        if output == "no":
            return "warn", "OS reports NTP not synchronized"
    elif system == "windows":
        output = run(["w32tm", "/query", "/status"])
        # English output only. Localized/unrecognized responses remain unknown.
        if output and re.search(r"(?m)^Leap Indicator:\s*0\b", output) and re.search(r"(?m)^Source:\s*(?!Local CMOS Clock|Free-running System Clock)\S", output):
            return "pass", "OS reports a synchronized time source; actual offset is unverified"
    elif system == "macos":
        run(["systemsetup", "-getusingnetworktime"])
    return "warn", "Time synchronization unknown; verify in OS settings (no clock changes made)"


def inspect_storage(config: dict) -> list[dict]:
    checks = []
    filesystem_reserves = {}
    inspected_paths = []
    requests = [(role, value, config["storage_reserve_gib"][role]) for role, value in config["paths"].items() if value]
    for service, overrides in config["service_paths"].items():
        requests.extend((f"{service}.{role}", value, config["storage_reserve_gib"][role]) for role, value in overrides.items())
    for label, value, reserve in requests:
        path = Path(value)
        try:
            if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()) for p in (path, *path.parents)):
                checks.append({"name": f"storage.{label}", "status": "block", "detail": "Storage path includes a symlink/junction; explicit mapping review required"})
                continue
            resolved = path.resolve()
            if resolved.is_relative_to(ROOT) or ROOT.is_relative_to(resolved):
                checks.append({"name": f"storage.{label}", "status": "block", "detail": "Runtime storage must not contain or be inside the repository"})
                continue
            if any((ancestor / ".git").exists() for ancestor in (resolved, *resolved.parents)):
                checks.append({"name": f"storage.{label}", "status": "block", "detail": "Runtime storage must stay outside Git checkouts"})
                continue
            if config["platform"] == "windows" and not Path(path.anchor).exists():
                checks.append({"name": f"storage.{label}", "status": "block", "detail": "Requested drive is unavailable"})
                continue
            if config["platform"] in ("linux", "macos") and len(path.parts) >= 3 and path.parts[1] in ("mnt", "Volumes"):
                mount = Path(*path.parts[:3])
                if not mount.is_mount():
                    checks.append({"name": f"storage.{label}", "status": "block", "detail": "Expected external mount is not mounted; no fallback to system disk"})
                    continue
            if path.exists() and (not path.is_dir() or next(path.iterdir(), None) is not None):
                checks.append({"name": f"storage.{label}", "status": "block", "detail": "Fresh-install storage is already occupied; no adoption or overwrite will occur"})
                continue
            ancestor = path
            while not ancestor.exists():
                ancestor = ancestor.parent
            if not ancestor.is_dir() or not os.access(ancestor, os.W_OK | os.X_OK):
                checks.append({"name": f"storage.{label}", "status": "block", "detail": "Nearest existing directory is not accessible for proposed storage"})
                continue
            device = ancestor.stat().st_dev
            free = shutil.disk_usage(ancestor).free
            group = filesystem_reserves.setdefault(device, {"requested": 0, "free": free, "roles": []})
            group["requested"] += reserve * GIB
            group["roles"].append(label)
            inspected_paths.append((label, resolved))
            checks.append({"name": f"storage.{label}", "status": "pass", "detail": "Path/ancestor available; permissions are advisory (no write test performed)"})
        except (OSError, ValueError):
            checks.append({"name": f"storage.{label}", "status": "block", "detail": "Storage could not be inspected safely"})
    for i, (_, path) in enumerate(inspected_paths):
        for _, other in inspected_paths[i + 1:]:
            if path.is_relative_to(other) or other.is_relative_to(path):
                checks.append({"name": "storage.alias", "status": "block", "detail": "Physical storage roots/overrides overlap"})
    for group in filesystem_reserves.values():
        checks.append({"name": "storage.capacity:" + ",".join(group["roles"]),
                       "status": "pass" if group["free"] >= group["requested"] else "block",
                       "detail": "Combined free-space reserves on the shared filesystem",
                       "free_gib": round(group["free"] / GIB, 2), "requested_gib": group["requested"] // GIB})
    checks.append({"name": "storage.docker-disk", "status": "warn", "detail": "Docker image/named-volume disk capacity and filesystem suitability require separate verification"})
    return checks


def diagnose(config=None, modules=None, planning=None, *, run=command, environment=None,
             system=None, architecture=None, memory=None, ports=None, storage_probe=inspect_storage) -> dict:
    system = system or host_platform()
    architecture = architecture or host_architecture()
    environment = os.environ if environment is None else environment
    checks = []
    facts = {"platform": system, "architecture": architecture, "python": platform.python_version(), "host_cpu_count": os.cpu_count()}

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    add("platform", "pass" if system in ("windows", "linux", "macos") else "block", "Host platform detection")
    add("architecture", "pass" if architecture in ("amd64", "arm64") else "block", "Host architecture detection; image support is not implied")
    add("python", "pass" if sys.version_info >= (3, 12) else "block", "Python 3.12 or newer required")
    total, available = memory if memory is not None else host_memory(system, run)
    facts.update({"host_memory_gib": round(total / GIB, 2) if total is not None else None,
                  "host_available_gib": round(available / GIB, 2) if available is not None else None})
    add("memory-probe", "pass" if total is not None else "warn", "Physical memory detection; available memory is a changing snapshot")
    add("time-sync", *time_status(system, run))
    if config is not None:
        config = validate_config(config, modules, planning)
        add("target", "pass" if config["platform"] == system and config["architecture"] == architecture else "block", "Settings target must match this host for live checks")
        if config["platform"] == system:
            checks.extend(storage_probe(config))
        budget = config["resource_budget"]
        if total is None:
            add("host-headroom", "warn", "Cannot verify host memory headroom")
        else:
            add("host-headroom", "pass" if (budget["memory_gib"] + budget["reserve_host_gib"]) * GIB <= total else "block", "Memory budget plus host reserve must fit physical RAM")
        if available is not None and available < budget["reserve_host_gib"] * GIB:
            add("available-memory", "warn", "Current available host memory is below the requested host reserve")
        if facts["host_cpu_count"] is not None:
            add("host-cpu", "pass" if budget["cpu_limit"] <= facts["host_cpu_count"] else "block", "Requested CPU ceiling must fit the host")
    docker = None
    if any(environment.get(key) for key in ("DOCKER_HOST", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")):
        add("docker-context", "block", "Docker endpoint/TLS environment overrides are present; clear or review them explicitly before local checks")
    else:
        context = run(["docker", "context", "show"])
        if not context or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", context):
            add("docker-context", "block", "Docker CLI/context unavailable; install or start the intended local runtime manually")
        else:
            endpoint_text = run(["docker", "context", "inspect", context, "--format", "{{json .Endpoints.docker.Host}}"])
            try:
                endpoint = json.loads(endpoint_text) if endpoint_text else None
            except ValueError:
                endpoint = None
            if not local_endpoint(endpoint):
                add("docker-context", "block", "Remote or unrecognized Docker endpoint refused before any daemon query")
            else:
                docker = ["docker", "--context", context]
                add("docker-context", "pass", "Local socket/pipe context selected explicitly; no context changes made")
    if docker is not None:
        raw = run(docker + ["info", "--format", '{"os":{{json .OSType}},"architecture":{{json .Architecture}},"cpus":{{json .NCPU}},"memory":{{json .MemTotal}}}'])
        try:
            info = json.loads(raw) if raw else None
            if not isinstance(info, dict) or type(info.get("cpus")) is not int or type(info.get("memory")) is not int or info["cpus"] <= 0 or info["memory"] <= 0:
                raise ValueError("invalid metadata")
            facts.update({"engine_cpu_count": info["cpus"], "engine_memory_gib": round(info["memory"] / GIB, 2)})
            add("docker-engine", "pass" if info.get("os") == "linux" else "block", "Linux-container engine required")
            engine_arch = {"x86_64": "amd64", "aarch64": "arm64", "amd64": "amd64", "arm64": "arm64"}.get(info.get("architecture"))
            add("docker-architecture", "pass" if engine_arch == (config["architecture"] if config else architecture) else "block", "Engine architecture must match target; no automatic emulation")
            if config:
                add("engine-budget", "pass" if config["resource_budget"]["cpu_limit"] <= info["cpus"] and config["resource_budget"]["memory_gib"] * GIB <= info["memory"] else "block", "Requested budget must fit the current Docker engine ceiling")
        except (ValueError, TypeError):
            add("docker-engine", "block", "Docker daemon metadata unavailable or invalid; it may be stopped or inaccessible")
        compose = run(docker + ["compose", "version", "--short"])
        version = re.fullmatch(r"v?(\d+)\.\d+\.\d+(?:[-+][A-Za-z0-9_.-]+)?", compose or "")
        add("compose", "pass" if version and int(version.group(1)) >= 2 else "block", "Compose v2-compatible CLI required")
        if version:
            facts["compose_version"] = compose
        if config:
            rows = run(docker + ["ps", "-a", "--format", '{"project":{{json (.Label "com.docker.compose.project")}},"ports":{{json .Ports}}}'])
            if rows is None:
                add("docker-existing", "block", "Cannot check existing Docker projects/port bindings")
            else:
                try:
                    entries = [json.loads(line) for line in rows.splitlines() if line]
                    order = resolve(config["services"], modules)
                    proposed_projects = {f"hl-{config['installation_id']}-{key}" for key in order}
                    occupied = any(row.get("project") in proposed_projects for row in entries)
                    add("docker-existing", "block" if occupied else "pass", "Check proposed project names for existing ownership; no adoption")
                    binding_ports = set()
                    for row in entries:
                        for first, last, protocol in re.findall(r":(\d+)(?:-(\d+))?->[^,]+?/(tcp|udp)", row.get("ports", "")):
                            start, end = int(first), int(last or first)
                            if not 1 <= start <= end <= 65535:
                                raise ValueError("invalid port metadata")
                            binding_ports.update((protocol, port) for port in range(start, end + 1))
                    reservations = port_reservations(config, order, planning)
                    conflicts = [p["key"] for p in reservations if any((p["protocol"], port) in binding_ports for port in range(p["first"], p["last"] + 1))]
                    add("docker-ports", "block" if conflicts else "pass", "Docker binding conflicts: " + ", ".join(conflicts) if conflicts else "No matching published Docker bindings observed")
                except (ValueError, TypeError, AttributeError):
                    add("docker-existing", "block", "Existing Docker metadata could not be interpreted safely")
    if config:
        listeners = ports if ports is not None else host_ports(system, run)
        if listeners is None:
            add("host-ports", "block", "Native listener inventory unavailable; port availability cannot be assumed")
        else:
            for port in port_reservations(config, resolve(config["services"], modules), planning):
                conflict = any((port["protocol"], p) in listeners for p in range(port["first"], port["last"] + 1))
                add("port:" + port["key"], "block" if conflict else "pass", "Port/range is occupied" if conflict else "No listener observed; this is a snapshot, not a port reservation")
    add("module-support", "warn", "Application templates, image architecture and recovery remain unvalidated; deployment is disabled")
    return {"kind": "homelab-doctor", "execution_allowed": False, "facts": facts, "checks": checks,
            "status": "blocked" if any(c["status"] == "block" for c in checks) else "review-required"}
