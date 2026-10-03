"""Interactive settings only: no host or application mutations."""

from pathlib import Path

from .config import ConfigError, validate_config
from .doctor import host_architecture, host_platform
from .planner import create_plan


def configure(modules: dict, planning: dict, *, ask=input, tell=print) -> dict | None:
    tell("HomeLab settings wizard - planning only; nothing will be deployed.")
    ids = sorted(modules)
    for index, key in enumerate(ids, 1):
        tell(f"{index:2}. {key} - {modules[key]['kind']}; module not yet deployable")

    def prompt(label, default):
        response = ask(f"{label} [{default}]: ").strip()
        return response or default

    while True:
        selection = prompt("Service IDs or numbers, separated by commas", "glance,uptime-kuma")
        try:
            selected = []
            for item in selection.split(","):
                item = item.strip()
                if item.isdigit():
                    index = int(item)
                    if not 1 <= index <= len(ids):
                        raise ValueError
                    item = ids[index - 1]
                if item not in modules or item in selected:
                    raise ValueError
                selected.append(item)
            break
        except ValueError:
            tell("Choose known services once each.")
    system = prompt("Target platform: windows, linux, macos", host_platform())
    architecture = prompt("Target architecture: amd64, arm64", host_architecture())
    identity = prompt("New installation ID", "home-lab")
    defaults = {"windows": "C:\\Homelab", "linux": "/srv/homelab", "macos": str(Path.home() / "Homelab")}
    root = defaults.get(system, "/srv/homelab")
    separator = "\\" if system == "windows" else "/"
    paths = {role: prompt(label, root + separator + suffix) for role, label, suffix in (
        ("installation_root", "Installation/config root", "installation"),
        ("media_root", "Media root", "media"),
        ("backup_root", "Backup root (use separate/off-host storage for real recovery)", "backups"))}
    policy = prompt("Database storage: docker-named-volumes or bind (expert, unvalidated)", "docker-named-volumes")
    paths["database_root"] = prompt("Database bind root", root + separator + "database") if policy == "bind" else None
    access = prompt("Access: loopback or lan (explicit host exposure)", "loopback")

    def integer(label, default):
        while True:
            value = prompt(label, str(default))
            if value.isdigit() and 1 <= int(value) <= 4096:
                return int(value)
            tell("Enter a positive integer no greater than 4096.")

    budget = {"cpu_limit": integer("CPU budget", 2), "memory_gib": integer("Memory budget GiB", 4),
              "reserve_host_gib": integer("RAM headroom for the host GiB", 4)}
    reserve = integer("Free disk reserve GiB for each declared storage path", 5)
    overrides = {}
    tell("Per-service storage overrides are optional. Leave the service ID blank to finish.")
    while True:
        key = ask("Service ID for a separate storage location: ").strip()
        if not key:
            break
        if key not in selected:
            tell("Choose a selected service ID.")
            continue
        custom = {}
        for role in ("media_root", "database_root"):
            if role == "database_root" and policy != "bind":
                continue
            value = ask(f"Absolute independent {role} (blank keeps default): ").strip()
            if value:
                custom[role] = value
        if custom:
            overrides[key] = custom
    port_overrides = {}
    while True:
        raw = ask("Port overrides such as glance.http=18081,uptime-kuma.http=13001 (blank for defaults): ").strip()
        try:
            for assignment in raw.split(",") if raw else []:
                key, value = assignment.split("=", 1)
                if key.strip() in port_overrides:
                    raise ValueError
                port_overrides[key.strip()] = int(value.strip())
            break
        except ValueError:
            port_overrides = {}
            tell("Enter comma-separated port-name=number assignments.")
    config = {"schema_version": 1, "kind": "homelab-settings", "installation_id": identity,
              "platform": system, "architecture": architecture, "mode": "fresh", "access": access,
              "services": selected, "paths": paths, "database_storage": policy,
              "service_paths": overrides, "port_overrides": port_overrides, "resource_budget": budget,
              "storage_reserve_gib": {role: reserve for role in paths}, "gpu": "disabled"}
    try:
        config = validate_config(config, modules, planning)
    except ConfigError:
        tell("Settings did not pass validation; no file was saved. Correct inputs and run again.")
        raise
    plan = create_plan(config, modules, planning)
    tell("Selected: " + ", ".join(key["id"] for key in plan["services"]))
    tell(f"Provisional total: {plan['resources']['allowance_memory_mib']} MiB, {plan['resources']['allowance_cpu_millicores'] / 1000:g} CPUs")
    for issue in plan["issues"]:
        tell("REVIEW: " + issue["detail"])
    tell("This saves private settings only. No credentials are generated and no host checks or deployment run.")
    return config if ask("Save these settings? [y/N]: ").strip().lower() in ("y", "yes") else None
