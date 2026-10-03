"""Strict private settings schema and deterministic dependency resolution."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
ROLES = ("installation_root", "media_root", "backup_root", "database_root")


class ConfigError(ValueError):
    """Safe, value-free diagnostic suitable for displaying to an operator."""


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def keys(value: object, expected: set[str], location: str) -> None:
    need(isinstance(value, dict) and set(value) == expected, f"{location}: missing or unexpected fields")


def load_json(path: Path) -> object:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    try:
        need(path.stat().st_size <= 2_000_000, "JSON input is too large")
        return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ConfigError("Non-finite JSON number")))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConfigError("Cannot read a valid UTF-8 JSON input file") from error


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def catalogs() -> tuple[dict, dict]:
    catalog = load_json(ROOT / "catalog/services.json")
    planning = load_json(ROOT / "catalog/planning.json")
    modules = {entry["id"]: entry for entry in catalog["modules"]}
    validate_planning(planning, set(modules))
    return modules, planning["modules"]


def validate_planning(planning: object, ids: set[str]) -> None:
    keys(planning, {"schema_version", "estimate_basis", "modules"}, "planning catalog")
    need(type(planning["schema_version"]) is int and planning["schema_version"] == 1, "Unsupported planning catalog")
    need(isinstance(planning["estimate_basis"], str) and bool(planning["estimate_basis"]), "Estimate basis required")
    need(isinstance(planning["modules"], dict) and set(planning["modules"]) == ids, "Planning module coverage mismatch")
    for specification in planning["modules"].values():
        keys(specification, {"memory_mib", "cpu_millicores", "database_data", "ports", "manual"}, "planning module")
        for field in ("memory_mib", "cpu_millicores"):
            need(type(specification[field]) is int and specification[field] > 0, "Invalid planning allowance")
        need(type(specification["database_data"]) is bool, "Invalid database-data flag")
        need(isinstance(specification["manual"], str) and bool(specification["manual"]), "Manual review description required")
        need(isinstance(specification["ports"], list), "Port list required")
        names = set()
        for entry in specification["ports"]:
            keys(entry, {"name", "port", "protocol", "span"}, "port definition")
            need(isinstance(entry["name"], str) and bool(ID.fullmatch(entry["name"])) and entry["name"] not in names,
                 "Invalid or duplicate port name")
            names.add(entry["name"])
            need(entry["protocol"] in ("tcp", "udp"), "Invalid port protocol")
            need(type(entry["port"]) is int and type(entry["span"]) is int
                 and 1 <= entry["span"] <= 1000 and 1 <= entry["port"] <= 65536 - entry["span"], "Invalid port range")


def resolve(selected: list[str], modules: dict) -> list[str]:
    ordered, active, done = [], set(), set()

    def visit(key):
        need(isinstance(key, str) and key in modules, "Unknown service or dependency")
        need(key not in active, "Service dependency cycle")
        if key in done:
            return
        active.add(key)
        for dependency in sorted(modules[key]["dependencies"]):
            visit(dependency)
        active.remove(key)
        done.add(key)
        ordered.append(key)

    for key in sorted(selected):
        visit(key)
    return ordered


def logical_path(value: object, system: str):
    need(isinstance(value, str) and 0 < len(value) <= 2048 and value == value.strip(), "Storage path must be a nonempty string")
    need(not any(ord(char) < 32 or ord(char) == 127 for char in value), "Control characters in storage path")
    path = PureWindowsPath(value) if system == "windows" else PurePosixPath(value)
    need(path.is_absolute() and len(path.parts) > 1 and ".." not in path.parts, "Storage requires absolute dedicated paths without traversal")
    if system == "windows":
        need(bool(re.fullmatch(r"[A-Za-z]:", path.drive)), "UNC/device storage paths are not supported in Phase 2")
        for part in path.parts[1:]:
            need(not re.search(r'[<>:"|?*]', part) and not part.endswith((".", " ")),
                 "Invalid Windows path component")
            need(not re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part), "Reserved Windows path component")
    else:
        need(not value.startswith("//"), "Network-like POSIX path is not supported")
    return path


def validate_config(config: object, modules: dict, planning: dict) -> dict:
    keys(config, {"schema_version", "kind", "installation_id", "platform", "architecture", "mode", "access",
                  "services", "paths", "database_storage", "service_paths", "port_overrides", "resource_budget",
                  "storage_reserve_gib", "gpu"}, "settings")
    need(type(config["schema_version"]) is int and config["schema_version"] == 1
         and config["kind"] == "homelab-settings", "Unsupported settings schema; design examples are not settings")
    identifier = config["installation_id"]
    need(isinstance(identifier, str) and len(identifier) <= 32 and bool(ID.fullmatch(identifier)), "Invalid installation ID")
    need(config["platform"] in ("windows", "linux", "macos"), "Unsupported target platform")
    need(config["architecture"] in ("amd64", "arm64"), "Unsupported target architecture")
    need(config["mode"] == "fresh", "Only fresh-install planning is implemented; restore/adopt/replica are unavailable")
    need(config["access"] in ("loopback", "lan"), "Only loopback or explicit LAN planning is implemented")
    need(config["gpu"] == "disabled", "GPU provisioning is not implemented; select disabled")
    selected = config["services"]
    need(isinstance(selected, list) and bool(selected) and all(isinstance(x, str) for x in selected), "Select at least one service")
    need(len(selected) == len(set(selected)), "Duplicate service selection")
    order = resolve(selected, modules)
    keys(config["paths"], set(ROLES), "paths")
    need(config["database_storage"] in ("docker-named-volumes", "bind"), "Invalid database storage policy")
    if config["database_storage"] == "docker-named-volumes":
        need(config["paths"]["database_root"] is None, "Named volumes do not have an independently selectable host database path")
    else:
        need(config["paths"]["database_root"] is not None, "Bind policy requires a database path")
    roots = [logical_path(value, config["platform"]) for value in config["paths"].values() if value is not None]
    need(all(config["paths"][role] is not None for role in ROLES[:3]), "Installation, media and backup roots required")
    for i, path in enumerate(roots):
        for other in roots[i + 1:]:
            need(not path.is_relative_to(other) and not other.is_relative_to(path), "Storage roots overlap")
    need(isinstance(config["service_paths"], dict) and set(config["service_paths"]) <= set(order), "Invalid per-service path selection")
    for service, overrides in config["service_paths"].items():
        need(isinstance(overrides, dict) and bool(overrides) and set(overrides) <= {"media_root", "database_root"}, "Invalid per-service storage roles")
        for role, value in overrides.items():
            need(role != "database_root" or config["database_storage"] == "bind", "Database path override requires bind policy")
            need(role != "database_root" or planning[service]["database_data"], "Selected service has no declared database data role")
            override = logical_path(value, config["platform"])
            need(all(not override.is_relative_to(root) and not root.is_relative_to(override) for root in roots),
                 "Per-service overrides must use independent non-overlapping roots; omit overrides to use module subdirectories")
    keys(config["resource_budget"], {"cpu_limit", "memory_gib", "reserve_host_gib"}, "resource budget")
    need(all(type(x) is int and 1 <= x <= 4096 for x in config["resource_budget"].values()), "Resource budgets must be positive bounded integers")
    keys(config["storage_reserve_gib"], set(ROLES), "storage reserves")
    need(all(type(x) is int and 1 <= x <= 1_000_000 for x in config["storage_reserve_gib"].values()), "Storage reserves must be positive bounded integers")
    allowed_ports = {f"{key}.{entry['name']}": entry for key in order for entry in planning[key]["ports"]}
    need(isinstance(config["port_overrides"], dict) and set(config["port_overrides"]) <= set(allowed_ports), "Unknown port override")
    for name, port in config["port_overrides"].items():
        need(type(port) is int and 1 <= port <= 65536 - allowed_ports[name]["span"], "Invalid port override/range")
    # Validate effective per-service destinations, not just global roots.
    destinations = service_destinations(config, order, planning)
    entries = [(key, role, logical_path(value, config["platform"])) for key, paths in destinations.items()
               for role, value in paths.items() if value is not None]
    for i, (_, _, path) in enumerate(entries):
        for _, _, other in entries[i + 1:]:
            need(not path.is_relative_to(other) and not other.is_relative_to(path), "Effective service storage overlaps")
    normalized = json.loads(canonical(config))
    normalized["services"] = sorted(selected)
    for role, value in normalized["paths"].items():
        if value is not None:
            normalized["paths"][role] = str(logical_path(value, config["platform"]))
    for overrides in normalized["service_paths"].values():
        for role, value in overrides.items():
            overrides[role] = str(logical_path(value, config["platform"]))
    return normalized


def service_destinations(config: dict, order: list[str], planning: dict) -> dict:
    result = {}
    path_type = PureWindowsPath if config["platform"] == "windows" else PurePosixPath
    for key in order:
        result[key] = {}
        for role, root in config["paths"].items():
            if role == "database_root" and not planning[key]["database_data"]:
                result[key][role] = None
                continue
            override = config["service_paths"].get(key, {}).get(role)
            result[key][role] = override if override else (str(path_type(root) / key) if root else None)
    return result
