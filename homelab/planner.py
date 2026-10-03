"""Pure deterministic intent planning. No deployment operations exist here."""

import hashlib

from . import __version__
from .config import canonical, resolve, validate_config


def port_reservations(config: dict, order: list[str], planning: dict) -> list[dict]:
    ports = []
    for key in order:
        for definition in planning[key]["ports"]:
            label = f"{key}.{definition['name']}"
            start = config["port_overrides"].get(label, definition["port"])
            ports.append({"key": label, "protocol": definition["protocol"], "first": start,
                          "last": start + definition["span"] - 1,
                          "bind": "127.0.0.1" if config["access"] == "loopback" else "0.0.0.0"})
    return ports


def create_plan(config: dict, modules: dict, planning: dict) -> dict:
    config = validate_config(config, modules, planning)
    order = resolve(config["services"], modules)
    ports = port_reservations(config, order, planning)
    issues = []
    for i, port in enumerate(ports):
        for other in ports[i + 1:]:
            if port["protocol"] == other["protocol"] and max(port["first"], other["first"]) <= min(port["last"], other["last"]):
                issues.append({"code": "port-overlap", "detail": f"{port['key']} overlaps {other['key']}"})
    memory = sum(planning[key]["memory_mib"] for key in order)
    cpu = sum(planning[key]["cpu_millicores"] for key in order)
    if memory > config["resource_budget"]["memory_gib"] * 1024:
        issues.append({"code": "memory-budget", "detail": "Provisional module allowances exceed the selected memory budget"})
    if cpu > config["resource_budget"]["cpu_limit"] * 1000:
        issues.append({"code": "cpu-budget", "detail": "Provisional concurrent CPU allowances exceed the selected CPU budget"})
    warnings = ["No application module is deployment-certified. No actions will be executed.",
                "Allowances are planning estimates, not benchmarks, minimum requirements or configured limits.",
                "Image architecture, exact versions, Docker disk capacity and application settings require later validation."]
    if config["database_storage"] == "bind":
        warnings.append("Expert database bind storage is an unvalidated proposal, not an approved database migration.")
    if config["access"] == "lan":
        warnings.append("LAN bindings are requested; firewall, authentication and client compatibility are not verified.")
    if config["architecture"] == "arm64":
        warnings.append("ARM64 image/build availability is unverified; no emulation or x64 fallback will be enabled.")
    if "coolify" in order and config["platform"] != "linux":
        warnings.append("Coolify on this host requires a separately tested Linux VM/experimental adapter.")
    catalog_hash = hashlib.sha256(canonical({"modules": modules, "planning": planning}).encode()).hexdigest()
    configuration_hash = hashlib.sha256(canonical(config).encode()).hexdigest()
    public = {
        "schema_version": 1, "tool_version": __version__, "kind": "homelab-review-plan",
        "execution_allowed": False, "deployment_operations": [],
        "target": {"platform": config["platform"], "architecture": config["architecture"], "mode": "fresh"},
        "configuration_hash": configuration_hash, "catalog_hash": catalog_hash,
        "services": [{"id": key, "automatically_selected": key not in config["services"],
                      "dependencies": sorted(modules[key]["dependencies"]),
                      "bundled_components": modules[key]["components"], "kind": modules[key]["kind"],
                      "implementation_status": modules[key]["status"], "manual_review": planning[key]["manual"]}
                     for key in order],
        "storage": {"roots": {role: (f"<{role}>" if value else None) for role, value in config["paths"].items()},
                    "database_policy": config["database_storage"],
                    "per_service_overrides": {key: sorted(value) for key, value in config["service_paths"].items()},
                    "reserve_gib_per_declared_path": config["storage_reserve_gib"]},
        "ports": ports,
        "resources": {"budget": config["resource_budget"], "allowance_memory_mib": memory,
                      "allowance_cpu_millicores": cpu},
        "issues": issues, "warnings": warnings,
        "host_checked": False,
    }
    public["plan_id"] = hashlib.sha256(canonical(public).encode()).hexdigest()
    return public
