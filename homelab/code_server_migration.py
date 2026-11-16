"""Backup-gated code-server production migration contracts."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import code_server
from .config import ROOT, canonical, keys, load_json, need
from .sandbox import digest


CONTRACT = "phase7-code-server-migration-v1"
MODULE = ROOT / "modules/code-server"
POLICY = MODULE / "migration.example.json"
RESTIC = MODULE / "restic.json"
SCOPES = ["config", "local", "secure", "workspace"]
BACKUP_INCLUDED = SCOPES + ["compose", "build-metadata"]
MOUNT_TARGETS = [code_server.MOUNTS[name] for name in SCOPES]


def load_restic(path: Path = RESTIC) -> dict:
    value = load_json(path)
    keys(value, {"version", "windows_amd64"}, "code-server Restic manifest")
    need(value["version"] == "0.19.1", "Unreviewed Restic version")
    item = value["windows_amd64"]
    keys(item, {"archive_url", "archive_sha256", "executable_sha256"},
         "code-server Windows Restic release")
    need(item == {
        "archive_url": ("https://github.com/restic/restic/releases/download/"
                        "v0.19.1/restic_0.19.1_windows_amd64.zip"),
        "archive_sha256":
            "da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d",
        "executable_sha256":
            "b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830",
    }, "Reviewed Restic identity changed")
    return json.loads(canonical(value))


def validate_policy(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "source", "candidate",
                 "persistence", "network", "limits", "backup", "recovery",
                 "migration"}, "code-server migration policy")
    need(value["kind"] == "homelab-code-server-migration-policy"
         and value["contract"] == CONTRACT
         and value["platform"] == "windows-docker-desktop-amd64",
         "Unsupported code-server migration policy")

    source = value["source"]
    keys(source, {"configured_image", "actual_code_server_version"},
         "code-server migration source")
    need(source == {"configured_image": "local/code-server-dev:4.144.0",
                    "actual_code_server_version": "4.131.0"},
         "Reference source identity changed")

    build = code_server.load_build()
    candidate = value["candidate"]
    keys(candidate, {"image", "code_server_version", "node_version",
                     "architecture", "platform_digest"},
         "code-server migration candidate")
    need(candidate == {
        "image": "localhost/homelab-code-server:4.145.0-amd64",
        "code_server_version": build["code_server"]["version"],
        "node_version": build["node"]["version"],
        "architecture": "amd64",
        "platform_digest": build["code_server"]["platform_digests"]["amd64"],
    }, "Migration candidate does not match the reviewed build")

    keys(value["persistence"], {"scopes", "mount_targets"},
         "code-server migration persistence")
    need(value["persistence"] == {"scopes": SCOPES,
                                   "mount_targets": MOUNT_TARGETS},
         "Code-server migration persistence scopes changed")
    keys(value["network"], {"source_publish", "target_publish",
                            "public_validation_required"},
         "code-server migration network")
    need(value["network"] == {
        "source_publish": "0.0.0.0:8443",
        "target_publish": "127.0.0.1:8443",
        "public_validation_required": True,
    }, "Code-server migration network boundary changed")
    need(value["limits"] == {"cpus": 6.0, "memory_mib": 6144,
                              "memory_reservation_mib": 512, "pids": 2048},
         "Code-server production limits changed")

    backup = value["backup"]
    keys(backup, {"tool", "services_stopped", "included",
                  "repository_separate_physical_disk",
                  "recovery_key_separate_physical_disk",
                  "full_data_check", "remove_plaintext_staging"},
         "code-server migration backup")
    restic = load_restic()
    need(backup == {
        "tool": {"name": "restic", "version": restic["version"],
                 "executable_sha256":
                    restic["windows_amd64"]["executable_sha256"]},
        "services_stopped": True,
        "included": BACKUP_INCLUDED,
        "repository_separate_physical_disk": True,
        "recovery_key_separate_physical_disk": True,
        "full_data_check": True,
        "remove_plaintext_staging": True,
    }, "Code-server encrypted backup policy changed")

    need(value["recovery"] == {
        "independent_root_required": True,
        "archive_hashes_required": True,
        "server_side_compile_required": True,
        "restart_required": True,
    }, "Code-server recovery gates changed")
    need(value["migration"] == {
        "compose_backup_required": True,
        "force_recreate": True,
        "local_health_required": True,
        "public_health_required": True,
        "automatic_rollback_on_failed_gate": True,
        "old_image_retained": True,
    }, "Code-server production migration gates changed")
    return json.loads(canonical(value))


def load_policy(path: Path = POLICY) -> dict:
    return validate_policy(load_json(path))


def make_plan(policy: dict) -> dict:
    policy = validate_policy(policy)
    result = {
        "kind": "homelab-code-server-migration-plan",
        "contract": CONTRACT,
        "platform": policy["platform"],
        "source": policy["source"],
        "candidate": policy["candidate"],
        "persistence": policy["persistence"],
        "network": policy["network"],
        "limits": policy["limits"],
        "backup": policy["backup"],
        "recovery": policy["recovery"],
        "migration": policy["migration"],
        "ordered_gates": [
            "read-only-source-audit",
            "stopped-state-backup",
            "encrypted-snapshot",
            "repository-check-read-data",
            "independent-root-restore",
            "restored-runtime-compile-restart",
            "compose-rollback-copy",
            "production-force-recreate",
            "local-and-public-health",
            "production-compose-restart",
            "plaintext-staging-cleanup",
        ],
        "production_change_authorized": False,
        "execution_performed": False,
    }
    result["plan_id"] = digest(result)
    return result


def validate_plan(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "source", "candidate",
                 "persistence", "network", "limits", "backup", "recovery",
                 "migration", "ordered_gates", "production_change_authorized",
                 "execution_performed", "plan_id"},
         "code-server migration plan")
    policy = {"kind": "homelab-code-server-migration-policy",
              "contract": CONTRACT,
              **{name: value[name] for name in
                 ("platform", "source", "candidate", "persistence", "network",
                  "limits", "backup", "recovery", "migration")}}
    expected = make_plan(validate_policy(policy))
    need(canonical(value) == canonical(expected),
         "Code-server migration plan changed; review a new plan")
    return value


def validate_evidence(value: object, plan: dict) -> dict:
    plan = validate_plan(plan)
    keys(value, {"kind", "contract", "plan_id", "backup", "restore",
                 "production", "safety", "evidence_id"},
         "code-server migration evidence")
    need(value["kind"] == "homelab-code-server-production-migration-evidence"
         and value["contract"] == CONTRACT
         and value["plan_id"] == plan["plan_id"],
         "Code-server migration evidence does not match the reviewed plan")

    backup = value["backup"]
    keys(backup, {"restic_version", "restic_sha256", "snapshot_id",
                  "services_stopped", "included", "encrypted",
                  "repository_check_read_data",
                  "repository_separate_physical_disk",
                  "recovery_key_separate_physical_disk",
                  "plaintext_staging_removed"}, "code-server backup evidence")
    need(backup["restic_version"] == plan["backup"]["tool"]["version"]
         and backup["restic_sha256"]
             == plan["backup"]["tool"]["executable_sha256"]
         and bool(re.fullmatch(r"[0-9a-f]{64}", backup["snapshot_id"]))
         and backup["included"] == BACKUP_INCLUDED
         and all(backup[name] is True for name in (
             "services_stopped", "encrypted", "repository_check_read_data",
             "repository_separate_physical_disk",
             "recovery_key_separate_physical_disk",
             "plaintext_staging_removed")),
         "Encrypted code-server backup proof is incomplete")

    restore = value["restore"]
    keys(restore, {"independent_root", "archive_hashes_match",
                   "code_server_version", "node_version", "extension_count",
                   "server_side_compile", "http_health", "restart_persistence"},
         "code-server restore evidence")
    need(restore["code_server_version"]
            == plan["candidate"]["code_server_version"]
         and restore["node_version"] == plan["candidate"]["node_version"]
         and type(restore["extension_count"]) is int
         and restore["extension_count"] >= len(code_server.load_build()["extensions"])
         and all(restore[name] is True for name in (
             "independent_root", "archive_hashes_match", "server_side_compile",
             "http_health", "restart_persistence")),
         "Independent code-server restore proof is incomplete")

    production = value["production"]
    keys(production, {"source_code_server_version", "target_code_server_version",
                      "node_version", "image_id", "loopback_only",
                      "published_port", "limits", "mount_targets",
                      "server_side_compile", "local_health", "public_health",
                      "compose_restart", "rollback_compose_backup",
                      "encrypted_state_recovery"},
         "code-server production migration evidence")
    need(production["source_code_server_version"]
            == plan["source"]["actual_code_server_version"]
         and production["target_code_server_version"]
            == plan["candidate"]["code_server_version"]
         and production["node_version"] == plan["candidate"]["node_version"]
         and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", production["image_id"]))
         and production["published_port"] == 8443
         and production["limits"] == plan["limits"]
         and production["mount_targets"] == MOUNT_TARGETS
         and all(production[name] is True for name in (
             "loopback_only", "server_side_compile", "local_health",
             "public_health", "compose_restart", "rollback_compose_backup",
             "encrypted_state_recovery")),
         "Production code-server migration proof is incomplete")

    need(value["safety"] == {
        "credentials_read": False,
        "workspace_content_read": False,
        "production_workspace_modified": False,
        "docker_socket_mounted": False,
        "old_image_retained": True,
    }, "Code-server migration crossed its privacy or rollback boundary")
    copy = dict(value)
    identifier = copy.pop("evidence_id")
    need(identifier == digest(copy), "Code-server migration evidence changed")
    return value
