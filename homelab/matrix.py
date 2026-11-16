"""Identity-safe Matrix planning and synthetic recovery evidence validation."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .config import ROOT, canonical, keys, load_json, logical_path, need
from .sandbox import digest


CONTRACT = "phase7-matrix-v1"
MODULE = ROOT / "modules/matrix"
IMAGES = MODULE / "images.json"
SELECTION = MODULE / "selection.example.json"
ARCHITECTURES = ("amd64", "arm64")
FEATURES = {
    "element": True,
    "federation": False,
    "open_registration": False,
    "turn": False,
    "bridges": False,
    "admin_ui": False,
    "metrics": False,
}
ROLES = ("database", "synapse", "element")
CONTAINER_PORTS = {"synapse": 8008, "element": 80}


def _version(value: object, label: str) -> str:
    need(isinstance(value, str)
         and bool(re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", value)),
         f"Invalid {label} version")
    return value


def _image(value: object, label: str) -> str:
    need(isinstance(value, str)
         and bool(re.fullmatch(r"[^\s@]+:[^\s@]+@sha256:[0-9a-f]{64}", value)),
         f"{label} image must use a tagged immutable index digest")
    return value


def validate_images(value: object) -> dict:
    keys(value, {"kind", "contract", *ROLES}, "Matrix image manifest")
    need(value["kind"] == "homelab-matrix-images"
         and value["contract"] == CONTRACT,
         "Unsupported Matrix image manifest")
    for role in ROLES:
        item = value[role]
        keys(item, {"version", "image", "platform_digests"},
             f"Matrix {role} image")
        _version(item["version"], role)
        _image(item["image"], role)
        keys(item["platform_digests"], set(ARCHITECTURES),
             f"Matrix {role} platform digests")
        need(all(re.fullmatch(r"sha256:[0-9a-f]{64}", item_digest)
                 for item_digest in item["platform_digests"].values()),
             f"Invalid Matrix {role} platform digest")
    return json.loads(canonical(value))


def load_images(path: Path = IMAGES) -> dict:
    return validate_images(load_json(path))


def _https_url(value: object, label: str) -> str:
    need(isinstance(value, str), f"Invalid {label}")
    parsed = urlparse(value)
    need(parsed.scheme == "https" and bool(parsed.hostname)
         and parsed.username is None and parsed.password is None
         and parsed.query == "" and parsed.fragment == "",
         f"{label} must be an HTTPS origin without credentials, query or fragment")
    path = parsed.path or "/"
    need(path == "/", f"{label} must not contain an application path")
    return value.rstrip("/") + "/"


def validate_selection(value: object) -> dict:
    keys(value, {"kind", "contract", "installation_id", "target_platform",
                 "architecture", "server_name", "public_base_url",
                 "element_base_url", "state_root", "media_root", "ports",
                 "timezone", "access", "limits", "features"},
         "Matrix selection")
    need(value["kind"] == "homelab-matrix-selection"
         and value["contract"] == CONTRACT,
         "Unsupported Matrix selection")
    need(isinstance(value["installation_id"], str)
         and bool(re.fullmatch(r"[a-z][a-z0-9-]{2,31}",
                              value["installation_id"])),
         "Invalid Matrix installation ID")
    platform = value["target_platform"]
    need(platform in ("windows", "linux", "macos"),
         "Unsupported Matrix target platform")
    need(value["architecture"] in ARCHITECTURES,
         "Unsupported Matrix target architecture")
    need(isinstance(value["server_name"], str)
         and bool(re.fullmatch(
             r"(?=.{1,255}$)(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)",
             value["server_name"])),
         "Invalid immutable Matrix server name")
    public = _https_url(value["public_base_url"], "Matrix public base URL")
    element = _https_url(value["element_base_url"], "Element base URL")
    need(urlparse(public).hostname != urlparse(element).hostname,
         "Synapse and Element should use distinct public hostnames")
    state = logical_path(value["state_root"], platform)
    media = logical_path(value["media_root"], platform)
    need(not state.is_relative_to(media) and not media.is_relative_to(state),
         "Matrix state and media roots must not overlap")
    keys(value["ports"], {"synapse", "element"}, "Matrix ports")
    need(all(type(port) is int and 1024 <= port <= 65535
             for port in value["ports"].values())
         and len(set(value["ports"].values())) == 2,
         "Matrix ports must be distinct and unprivileged")
    need(isinstance(value["timezone"], str)
         and bool(re.fullmatch(r"[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)*",
                              value["timezone"])),
         "Invalid Matrix timezone")
    need(value["access"] == "loopback",
         "Reusable Matrix HTTP services must remain loopback-only")
    keys(value["limits"], set(ROLES), "Matrix resource limits")
    for role, limit in value["limits"].items():
        keys(limit, {"cpus", "memory_mib", "memory_reservation_mib", "pids"},
             f"Matrix {role} resource limits")
        need(type(limit["cpus"]) in (int, float)
             and not isinstance(limit["cpus"], bool) and 0.1 <= limit["cpus"] <= 32,
             f"Invalid Matrix {role} CPU limit")
        need(type(limit["memory_mib"]) is int and 64 <= limit["memory_mib"] <= 65536,
             f"Invalid Matrix {role} memory limit")
        need(type(limit["memory_reservation_mib"]) is int
             and 32 <= limit["memory_reservation_mib"] <= limit["memory_mib"],
             f"Invalid Matrix {role} memory reservation")
        need(type(limit["pids"]) is int and 32 <= limit["pids"] <= 8192,
             f"Invalid Matrix {role} PID limit")
    keys(value["features"], set(FEATURES), "Matrix features")
    need(value["features"] == FEATURES,
         "Matrix core safety features changed; review optional integrations separately")
    result = json.loads(canonical(value))
    result["public_base_url"] = public
    result["element_base_url"] = element
    result["state_root"] = str(state)
    result["media_root"] = str(media)
    return result


def load_selection(path: Path = SELECTION) -> dict:
    return validate_selection(load_json(path))


def make_plan(selection: dict, images: dict | None = None) -> dict:
    selection = validate_selection(selection)
    images = validate_images(images if images is not None else load_images())
    architecture = selection["architecture"]
    plan = {
        "kind": "homelab-matrix-plan",
        "contract": CONTRACT,
        "installation_id": selection["installation_id"],
        "target_platform": selection["target_platform"],
        "architecture": architecture,
        "identity": {
            "server_name": selection["server_name"],
            "renamable_after_restore": False,
            "signing_key_required": True,
        },
        "urls": {
            "synapse": selection["public_base_url"],
            "element": selection["element_base_url"],
        },
        "paths": {"state": selection["state_root"],
                  "media": selection["media_root"]},
        "access": {
            "mode": "loopback", "host": "127.0.0.1",
            "ports": selection["ports"],
            "container_ports": dict(CONTAINER_PORTS),
        },
        "timezone": selection["timezone"],
        "limits": selection["limits"],
        "features": dict(FEATURES),
        "images": {
            role: {
                "version": images[role]["version"],
                "image": images[role]["image"],
                "platform_digest": images[role]["platform_digests"][architecture],
            } for role in ROLES
        },
        "recovery_material": [
            "postgres-custom-dump", "homeserver-config", "server-signing-key",
            "media-store", "element-config", "sanitized-compose-metadata",
        ],
        "client_e2ee_recovery": "separate-owner-validated-key-backup",
        "private_material": [
            "database-password", "registration-shared-secret",
            "macaroon-secret-key", "form-secret", "server-signing-key",
            "smtp-credentials", "client-e2ee-recovery-key",
        ],
        "production_state_adopted": False,
        "deployment_performed": False,
    }
    plan["plan_id"] = digest(plan)
    return plan


def validate_plan(plan: object) -> dict:
    keys(plan, {"kind", "contract", "installation_id", "target_platform",
                "architecture", "identity", "urls", "paths", "access",
                "timezone", "limits", "features", "images",
                "recovery_material", "client_e2ee_recovery",
                "private_material", "production_state_adopted",
                "deployment_performed", "plan_id"}, "Matrix plan")
    selection = {
        "kind": "homelab-matrix-selection", "contract": CONTRACT,
        "installation_id": plan["installation_id"],
        "target_platform": plan["target_platform"],
        "architecture": plan["architecture"],
        "server_name": plan["identity"]["server_name"],
        "public_base_url": plan["urls"]["synapse"],
        "element_base_url": plan["urls"]["element"],
        "state_root": plan["paths"]["state"],
        "media_root": plan["paths"]["media"],
        "ports": plan["access"]["ports"],
        "timezone": plan["timezone"], "access": plan["access"]["mode"],
        "limits": plan["limits"], "features": plan["features"],
    }
    expected = make_plan(validate_selection(selection), load_images())
    need(canonical(plan) == canonical(expected),
         "Matrix plan or immutable image inputs changed; review a new plan")
    return plan


def compose(plan: dict) -> dict:
    plan = validate_plan(plan)
    state = plan["paths"]["state"]
    separator = "\\" if plan["target_platform"] == "windows" else "/"

    def child(name: str) -> str:
        return state.rstrip("/\\") + separator + name

    labels = {"org.homelab.contract": CONTRACT,
              "org.homelab.plan-id": plan["plan_id"]}
    common = {
        "pull_policy": "never", "restart": "unless-stopped",
        "security_opt": ["no-new-privileges:true"],
        "logging": {"driver": "json-file",
                    "options": {"max-size": "10m", "max-file": "3"}},
        "labels": labels,
    }

    def limits(role: str) -> dict:
        value = plan["limits"][role]
        return {"cpus": value["cpus"], "mem_limit": f"{value['memory_mib']}m",
                "mem_reservation": f"{value['memory_reservation_mib']}m",
                "pids_limit": value["pids"]}

    database = {
        **common, **limits("database"), "image": plan["images"]["database"]["image"],
        "environment": {"POSTGRES_DB": "synapse", "POSTGRES_USER": "synapse",
                        "POSTGRES_PASSWORD_FILE": "/run/secrets/postgres_password",
                        "POSTGRES_INITDB_ARGS": "--encoding=UTF8 --locale=C"},
        "secrets": ["postgres_password"],
        "volumes": [{"type": "volume", "source": "database-data",
                     "target": "/var/lib/postgresql/data"}],
        "networks": ["backend"], "shm_size": "128m",
        "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U synapse -d synapse"],
                        "interval": "10s", "timeout": "5s", "retries": 12,
                        "start_period": "20s"},
    }
    synapse = {
        **common, **limits("synapse"), "image": plan["images"]["synapse"]["image"],
        "environment": {"TZ": plan["timezone"],
                        "SYNAPSE_CONFIG_PATH": "/data/homeserver.yaml"},
        "depends_on": {"database": {"condition": "service_healthy"}},
        "ports": [{"target": 8008,
                   "published": str(plan["access"]["ports"]["synapse"]),
                   "host_ip": "127.0.0.1", "protocol": "tcp"}],
        "volumes": [
            {"type": "bind", "source": child("synapse"), "target": "/data"},
            {"type": "bind", "source": plan["paths"]["media"],
             "target": "/data/media_store"},
        ],
        "networks": ["backend", "frontend"], "stop_grace_period": "60s",
        "healthcheck": {
            "test": ["CMD", "python", "-c",
                     "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8008/health', timeout=5).read()"],
            "interval": "15s", "timeout": "10s", "retries": 20,
            "start_period": "45s"},
    }
    element = {
        **common, **limits("element"), "image": plan["images"]["element"]["image"],
        "ports": [{"target": 80,
                   "published": str(plan["access"]["ports"]["element"]),
                   "host_ip": "127.0.0.1", "protocol": "tcp"}],
        "volumes": [{"type": "bind", "source": child("element/config.json"),
                     "target": "/app/config.json", "read_only": True}],
        "networks": ["frontend"],
        "healthcheck": {"test": ["CMD", "wget", "--spider", "-q",
                                 "http://127.0.0.1/"],
                        "interval": "30s", "timeout": "5s", "retries": 10,
                        "start_period": "20s"},
    }
    return {
        "name": plan["installation_id"],
        "services": {"database": database, "synapse": synapse,
                     "element": element},
        "volumes": {"database-data": {"labels": labels}},
        "networks": {
            "backend": {"driver": "bridge", "internal": True,
                        "labels": labels},
            "frontend": {"driver": "bridge", "labels": labels},
        },
        "secrets": {"postgres_password": {
            "file": child("secrets/postgres_password")}},
    }


def validate_evidence(value: object, plan: dict) -> dict:
    plan = validate_plan(plan)
    keys(value, {"kind", "contract", "plan_id", "images", "identity",
                 "exercise", "backup", "restore", "client_e2ee", "network",
                 "resources", "safety"}, "Matrix evidence")
    need(value["kind"] == "homelab-matrix-evidence"
         and value["contract"] == CONTRACT
         and value["plan_id"] == plan["plan_id"],
         "Matrix evidence does not match the reviewed plan")
    keys(value["images"], set(ROLES), "Matrix image evidence")
    for role in ROLES:
        keys(value["images"][role], {"version", "platform_digest"},
             f"Matrix {role} image evidence")
        need(value["images"][role] == {
            "version": plan["images"][role]["version"],
            "platform_digest": plan["images"][role]["platform_digest"],
        }, f"Matrix {role} runtime identity changed")
    identity = value["identity"]
    keys(identity, {"server_name", "signing_key_sha256_before",
                    "signing_key_sha256_after", "unchanged"},
         "Matrix identity evidence")
    need(identity["server_name"] == plan["identity"]["server_name"]
         and identity["unchanged"] is True
         and identity["signing_key_sha256_before"]
             == identity["signing_key_sha256_after"]
         and bool(re.fullmatch(r"[0-9a-f]{64}",
                              identity["signing_key_sha256_before"])),
         "Matrix server identity/signing key was not preserved")
    exercise = value["exercise"]
    keys(exercise, {"login", "room_created", "text_event", "media_upload",
                    "media_download", "element_http", "independent_sessions"},
         "Matrix exercise evidence")
    need(all(item is True for item in exercise.values()),
         "Matrix login, room, message, media or Element exercise failed")
    backup = value["backup"]
    keys(backup, {"synapse_quiesced", "postgres_custom_dump", "config",
                  "signing_key", "media", "element_config", "manifest_sha256",
                  "source_removed"}, "Matrix backup evidence")
    need(all(backup[field] is True for field in
             ("synapse_quiesced", "postgres_custom_dump", "config",
              "signing_key", "media", "element_config", "source_removed"))
         and bool(re.fullmatch(r"[0-9a-f]{64}", backup["manifest_sha256"])),
         "Matrix application-consistent backup evidence is incomplete")
    restore = value["restore"]
    keys(restore, {"independent_root", "same_versions", "database_restored",
                   "login", "room", "text_event", "media", "element_http"},
         "Matrix restore evidence")
    need(all(item is True for item in restore.values()),
         "Matrix independent restore did not recover actual synthetic content")
    e2ee = value["client_e2ee"]
    keys(e2ee, {"server_backup_claimed", "client_key_backup_tested",
                "owner_validation_required"}, "Matrix client E2EE evidence")
    need(e2ee == {"server_backup_claimed": False,
                  "client_key_backup_tested": False,
                  "owner_validation_required": True},
         "Server recovery must not be presented as client E2EE-key recovery")
    network = value["network"]
    keys(network, {"federation_enabled", "turn_tested", "bridges_tested",
                   "outbound_integrations_enabled"}, "Matrix network evidence")
    need(network == {"federation_enabled": False, "turn_tested": False,
                     "bridges_tested": False,
                     "outbound_integrations_enabled": False},
         "Optional Matrix networking crossed the isolated core trial")
    resources = value["resources"]
    keys(resources, {"idle_memory_mib", "peak_memory_mib"},
         "Matrix resource evidence")
    need(all(type(item) in (int, float) and not isinstance(item, bool)
             and item >= 0 for item in resources.values())
         and resources["peak_memory_mib"]
             <= sum(limit["memory_mib"] for limit in plan["limits"].values()),
         "Invalid Matrix resource evidence")
    safety = value["safety"]
    keys(safety, {"production_paths_used", "production_credentials_used",
                  "production_messages_read", "docker_socket_mounted",
                  "cleanup_completed"}, "Matrix safety evidence")
    need(safety == {"production_paths_used": False,
                    "production_credentials_used": False,
                    "production_messages_read": False,
                    "docker_socket_mounted": False,
                    "cleanup_completed": True},
         "Matrix trial crossed its synthetic isolation boundary")
    return value
