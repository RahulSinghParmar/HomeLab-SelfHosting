"""Reproducible, architecture-aware code-server planning and proof validation."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import ROOT, canonical, keys, load_json, logical_path, need
from .sandbox import digest


CONTRACT = "phase7-code-server-v1"
MODULE = ROOT / "modules/code-server"
BUILD = MODULE / "build.json"
SELECTION = MODULE / "selection.example.json"
IMAGE_CONTEXT = MODULE / "image"
ARCHITECTURES = ("amd64", "arm64")
FEATURES = {
    "autosave": True,
    "session_restore": True,
    "persistent_terminals": True,
    "runtime_extension_network": False,
}
MOUNTS = {
    "config": "/home/coder/.config",
    "local": "/home/coder/.local",
    "secure": "/home/coder/.secure",
    "workspace": "/home/coder/project",
}


def validate_build(value: object) -> dict:
    keys(value, {"kind", "contract", "code_server", "node", "apt_packages",
                 "extensions", "settings"}, "code-server build manifest")
    need(value["kind"] == "homelab-code-server-build"
         and value["contract"] == CONTRACT,
         "Unsupported code-server build manifest")
    code = value["code_server"]
    keys(code, {"version", "image", "platform_digests"}, "code-server release")
    need(isinstance(code["version"], str)
         and bool(re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", code["version"])),
         "Invalid code-server version")
    need(isinstance(code["image"], str)
         and re.fullmatch(r"ghcr\.io/coder/code-server:[^@\s]+@sha256:[0-9a-f]{64}",
                          code["image"]),
         "code-server base must use an immutable GHCR index digest")
    keys(code["platform_digests"], set(ARCHITECTURES),
         "code-server platform digests")
    need(all(re.fullmatch(r"sha256:[0-9a-f]{64}", item)
             for item in code["platform_digests"].values()),
         "Invalid code-server platform digest")

    node = value["node"]
    keys(node, {"version", "archives"}, "Node release")
    need(isinstance(node["version"], str)
         and bool(re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", node["version"])),
         "Invalid Node version")
    keys(node["archives"], set(ARCHITECTURES), "Node architecture archives")
    expected_suffix = {"amd64": "linux-x64.tar.xz", "arm64": "linux-arm64.tar.xz"}
    for arch, item in node["archives"].items():
        keys(item, {"file", "sha256"}, f"Node {arch} archive")
        need(item["file"] == f"node-v{node['version']}-{expected_suffix[arch]}",
             f"Node {arch} archive name does not match the selected version")
        need(bool(re.fullmatch(r"[0-9a-f]{64}", item["sha256"])),
             f"Invalid Node {arch} checksum")

    packages = value["apt_packages"]
    need(isinstance(packages, list) and packages == sorted(set(packages))
         and all(isinstance(item, str) and re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", item)
                 for item in packages),
         "APT package names must be sorted, unique and unversioned identifiers")
    need(all("=" not in item for item in packages),
         "APT package version syntax belongs in a separately reviewed lock")

    extensions = value["extensions"]
    need(isinstance(extensions, list) and bool(extensions),
         "At least one reviewed extension is required")
    seen = set()
    for item in extensions:
        keys(item, {"id", "version"}, "code-server extension")
        need(isinstance(item["id"], str)
             and bool(re.fullmatch(r"[A-Za-z0-9-]+\.[A-Za-z0-9_.-]+", item["id"])),
             "Invalid extension identifier")
        need(isinstance(item["version"], str)
             and bool(re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}(?:[-+][A-Za-z0-9.-]+)?",
                                  item["version"])),
             "Every extension version must be pinned")
        need(item["id"].casefold() not in seen, "Duplicate extension identifier")
        seen.add(item["id"].casefold())
    need([item["id"].casefold() for item in extensions]
         == sorted(item["id"].casefold() for item in extensions),
         "Extensions must be sorted by identifier")

    settings = value["settings"]
    keys(settings, {"seed_policy", "required"}, "code-server default settings")
    need(settings["seed_policy"] == "copy-once-never-overwrite",
         "Default settings must never overwrite an existing user file")
    keys(settings["required"], set(FEATURES) - {"runtime_extension_network"},
         "code-server required settings")
    need(settings["required"] == {
        "autosave": "afterDelay",
        "session_restore": "all",
        "persistent_terminals": True,
    }, "Required editor-persistence settings changed")
    return json.loads(canonical(value))


def load_build(path: Path = BUILD) -> dict:
    return validate_build(load_json(path))


def validate_selection(value: object) -> dict:
    keys(value, {"kind", "contract", "installation_id", "target_platform",
                 "architecture", "state_root", "workspace_root", "port",
                 "timezone", "uid", "gid", "access", "limits", "features"},
         "code-server selection")
    need(value["kind"] == "homelab-code-server-selection"
         and value["contract"] == CONTRACT,
         "Unsupported code-server selection")
    need(isinstance(value["installation_id"], str)
         and bool(re.fullmatch(r"[a-z][a-z0-9-]{2,31}", value["installation_id"])),
         "Invalid code-server installation ID")
    system = value["target_platform"]
    need(system in ("windows", "linux", "macos"),
         "Unsupported code-server target platform")
    need(value["architecture"] in ARCHITECTURES,
         "Unsupported code-server target architecture")
    state = logical_path(value["state_root"], system)
    workspace = logical_path(value["workspace_root"], system)
    need(not state.is_relative_to(workspace) and not workspace.is_relative_to(state),
         "Code-server state and workspace roots must not overlap")
    need(type(value["port"]) is int and 1024 <= value["port"] <= 65535,
         "Code-server port must be unprivileged")
    need(isinstance(value["timezone"], str)
         and bool(re.fullmatch(r"[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)*",
                              value["timezone"])),
         "Invalid code-server timezone")
    for field in ("uid", "gid"):
        need(type(value[field]) is int and 1 <= value[field] <= 65535,
             f"Invalid code-server {field}")
    need(value["access"] == "loopback",
         "Reusable code-server deployment must remain loopback-only")
    limits = value["limits"]
    keys(limits, {"cpus", "memory_mib", "memory_reservation_mib", "pids"},
         "code-server resource limits")
    need(type(limits["cpus"]) in (int, float) and not isinstance(limits["cpus"], bool)
         and 0.5 <= limits["cpus"] <= 64,
         "Invalid code-server CPU limit")
    need(type(limits["memory_mib"]) is int
         and 1024 <= limits["memory_mib"] <= 131072,
         "Invalid code-server memory limit")
    need(type(limits["memory_reservation_mib"]) is int
         and 256 <= limits["memory_reservation_mib"] <= limits["memory_mib"],
         "Invalid code-server memory reservation")
    need(type(limits["pids"]) is int and 128 <= limits["pids"] <= 32768,
         "Invalid code-server PID limit")
    keys(value["features"], set(FEATURES), "code-server features")
    need(value["features"] == FEATURES,
         "Code-server persistence or runtime-network policy changed")
    result = json.loads(canonical(value))
    result["state_root"] = str(state)
    result["workspace_root"] = str(workspace)
    return result


def load_selection(path: Path = SELECTION) -> dict:
    return validate_selection(load_json(path))


def make_plan(selection: dict, build: dict | None = None) -> dict:
    selection = validate_selection(selection)
    build = validate_build(build if build is not None else load_build())
    arch = selection["architecture"]
    node = build["node"]
    plan = {
        "kind": "homelab-code-server-plan",
        "contract": CONTRACT,
        "installation_id": selection["installation_id"],
        "target_platform": selection["target_platform"],
        "architecture": arch,
        "build": {
            "base_image": build["code_server"]["image"],
            "platform_digest": build["code_server"]["platform_digests"][arch],
            "code_server_version": build["code_server"]["version"],
            "node_version": node["version"],
            "node_archive": node["archives"][arch],
            "image": (f"localhost/homelab-code-server:"
                      f"{build['code_server']['version']}-{arch}"),
            "apt_packages": build["apt_packages"],
            "extensions": build["extensions"],
        },
        "paths": {
            "state": selection["state_root"],
            "workspace": selection["workspace_root"],
        },
        "mounts": dict(MOUNTS),
        "identity": {"uid": selection["uid"], "gid": selection["gid"]},
        "timezone": selection["timezone"],
        "access": {"mode": "loopback", "host": "127.0.0.1",
                   "port": selection["port"], "container_port": 8080},
        "limits": selection["limits"],
        "features": dict(FEATURES),
        "settings": build["settings"],
        "authentication": "private-config-file-required",
        "private_material": [
            "workspace-content", "git-identity", "ssh-keys", "gpg-keys",
            "code-server-password", "repository-credentials",
        ],
        "marketplace": "open-vsx-compatible-pinned-seed",
        "production_state_adopted": False,
        "deployment_performed": False,
    }
    plan["plan_id"] = digest(plan)
    return plan


def validate_plan(plan: object) -> dict:
    keys(plan, {"kind", "contract", "installation_id", "target_platform",
                "architecture", "build", "paths", "mounts", "identity",
                "timezone", "access", "limits", "features", "settings",
                "authentication", "private_material", "marketplace",
                "production_state_adopted", "deployment_performed", "plan_id"},
         "code-server plan")
    selection = {
        "kind": "homelab-code-server-selection",
        "contract": CONTRACT,
        "installation_id": plan["installation_id"],
        "target_platform": plan["target_platform"],
        "architecture": plan["architecture"],
        "state_root": plan["paths"]["state"],
        "workspace_root": plan["paths"]["workspace"],
        "port": plan["access"]["port"],
        "timezone": plan["timezone"],
        "uid": plan["identity"]["uid"],
        "gid": plan["identity"]["gid"],
        "access": plan["access"]["mode"],
        "limits": plan["limits"],
        "features": plan["features"],
    }
    expected = make_plan(validate_selection(selection), load_build())
    need(canonical(plan) == canonical(expected),
         "Code-server plan or immutable build inputs changed; review a new plan")
    return plan


def compose(plan: dict) -> dict:
    plan = validate_plan(plan)
    state = plan["paths"]["state"]
    separator = "\\" if plan["target_platform"] == "windows" else "/"

    def child(name: str) -> str:
        return state.rstrip("/\\") + separator + name

    build = plan["build"]
    service = {
        "image": build["image"],
        "pull_policy": "never",
        "build": {
            "context": str(IMAGE_CONTEXT),
            "dockerfile": "Dockerfile",
            "args": {
                "CODE_SERVER_BASE": build["base_image"],
                "CODE_SERVER_VERSION": build["code_server_version"],
                "CODE_SERVER_PLATFORM_DIGEST": build["platform_digest"],
                "NODE_VERSION": build["node_version"],
                "NODE_ARCHIVE_SHA256": build["node_archive"]["sha256"],
                "NODE_SHA256_AMD64": load_build()["node"]["archives"]["amd64"]["sha256"],
                "NODE_SHA256_ARM64": load_build()["node"]["archives"]["arm64"]["sha256"],
            },
        },
        "restart": "unless-stopped",
        "init": True,
        "security_opt": ["no-new-privileges:true"],
        "cap_drop": ["ALL"],
        "pids_limit": plan["limits"]["pids"],
        "mem_limit": f"{plan['limits']['memory_mib']}m",
        "mem_reservation": f"{plan['limits']['memory_reservation_mib']}m",
        "cpus": plan["limits"]["cpus"],
        "environment": {
            "TZ": plan["timezone"],
            "CODE_SERVER_EXPECTED_VERSION": build["code_server_version"],
            "CODE_SERVER_CONFIG": "/home/coder/.config/code-server/config.yaml",
        },
        "command": ["--config", "/home/coder/.config/code-server/config.yaml",
                    "/home/coder/project"],
        "working_dir": "/home/coder/project",
        "ports": [{"target": 8080, "published": str(plan["access"]["port"]),
                   "host_ip": "127.0.0.1", "protocol": "tcp"}],
        "volumes": [
            {"type": "bind", "source": child("config"),
             "target": MOUNTS["config"]},
            {"type": "bind", "source": child("local"),
             "target": MOUNTS["local"]},
            {"type": "bind", "source": child("secure"),
             "target": MOUNTS["secure"]},
            {"type": "bind", "source": plan["paths"]["workspace"],
             "target": MOUNTS["workspace"]},
        ],
        "tmpfs": ["/tmp:rw,nosuid,size=512m,mode=1777"],
        "healthcheck": {
            "test": ["CMD", "curl", "--fail", "--silent", "--show-error",
                     "http://127.0.0.1:8080/healthz"],
            "interval": "30s", "timeout": "5s", "start_period": "60s",
            "retries": 5,
        },
        "logging": {"driver": "json-file",
                    "options": {"max-size": "10m", "max-file": "3"}},
        "labels": {"org.homelab.contract": CONTRACT,
                   "org.homelab.plan-id": plan["plan_id"]},
        "networks": ["code-server"],
    }
    return {
        "name": plan["installation_id"],
        "services": {"code-server": service},
        "networks": {"code-server": {"driver": "bridge"}},
    }


def validate_evidence(value: object, plan: dict) -> dict:
    plan = validate_plan(plan)
    keys(value, {"kind", "contract", "plan_id", "build", "exercise",
                 "persistence", "recovery", "resources", "safety"},
         "code-server evidence")
    need(value["kind"] == "homelab-code-server-evidence"
         and value["contract"] == CONTRACT
         and value["plan_id"] == plan["plan_id"],
         "Code-server evidence does not match the reviewed plan")
    build = value["build"]
    keys(build, {"architecture", "code_server_version", "node_version",
                 "node_archive_sha256", "platform_digest", "extensions"},
         "code-server build evidence")
    need(build["architecture"] == plan["architecture"]
         and build["code_server_version"] == plan["build"]["code_server_version"]
         and build["node_version"] == plan["build"]["node_version"]
         and build["node_archive_sha256"] == plan["build"]["node_archive"]["sha256"]
         and build["platform_digest"] == plan["build"]["platform_digest"],
         "Built code-server identity does not match the reviewed inputs")
    expected_extensions = [f"{item['id']}@{item['version']}"
                           for item in plan["build"]["extensions"]]
    need(build["extensions"] == expected_extensions,
         "Pinned extension evidence is incomplete or reordered")

    exercise = value["exercise"]
    keys(exercise, {"synthetic_project", "server_side_compile",
                    "compile_exit_code", "source_sha256", "artifact_sha256",
                    "http_health", "reconnect_after_restart"},
         "code-server developer exercise")
    need(exercise["synthetic_project"] is True
         and exercise["server_side_compile"] is True
         and exercise["compile_exit_code"] == 0
         and exercise["http_health"] is True
         and exercise["reconnect_after_restart"] is True,
         "Code-server compile, health or restart exercise failed")
    for field in ("source_sha256", "artifact_sha256"):
        need(isinstance(exercise[field], str)
             and bool(re.fullmatch(r"[0-9a-f]{64}", exercise[field])),
             f"Invalid {field} proof")

    persistence = value["persistence"]
    keys(persistence, {"autosave", "settings", "extensions", "workspace",
                       "terminal_policy", "container_recreated"},
         "code-server persistence evidence")
    need(all(persistence[field] is True for field in
             ("autosave", "settings", "extensions", "workspace",
              "terminal_policy", "container_recreated")),
         "Code-server state did not persist across recreation")

    recovery = value["recovery"]
    keys(recovery, {"services_stopped", "included", "independent_root",
                    "restored", "source_hash_match", "settings_hash_match"},
         "code-server recovery evidence")
    need(recovery["services_stopped"] is True
         and recovery["included"] == ["config", "local", "secure", "workspace"]
         and recovery["independent_root"] is True
         and recovery["restored"] is True
         and recovery["source_hash_match"] is True
         and recovery["settings_hash_match"] is True,
         "Code-server recovery proof is incomplete")

    resources = value["resources"]
    keys(resources, {"idle_memory_mib", "compile_peak_memory_mib",
                     "compile_peak_cpu_percent"}, "code-server resources")
    for field in resources:
        need(type(resources[field]) in (int, float)
             and not isinstance(resources[field], bool) and resources[field] >= 0,
             f"Invalid code-server resource measurement {field}")
    need(resources["idle_memory_mib"] <= plan["limits"]["memory_mib"]
         and resources["compile_peak_memory_mib"] <= plan["limits"]["memory_mib"],
         "Code-server memory proof exceeds the reviewed limit")

    safety = value["safety"]
    keys(safety, {"production_paths_used", "production_credentials_used",
                  "private_workspace_read", "docker_socket_mounted",
                  "runtime_extension_network", "cleanup_completed"},
         "code-server safety evidence")
    need(safety == {
        "production_paths_used": False,
        "production_credentials_used": False,
        "private_workspace_read": False,
        "docker_socket_mounted": False,
        "runtime_extension_network": False,
        "cleanup_completed": True,
    }, "Code-server trial crossed its isolation boundary")
    return value
