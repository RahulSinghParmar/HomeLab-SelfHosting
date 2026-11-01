"""Validate and plan owner-operated Phase 5 backup storage without activating it."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from pathlib import PurePosixPath, PureWindowsPath

from .config import ConfigError, canonical, keys, need


CONTRACT = "phase5-owner-backup-policy-v1"
MODULES = (
    "paperless-ngx",
    "affine",
    "nextcloud",
    "firefly-iii",
    "vaultwarden",
    "karakeep",
)
TIME = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z")
IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
FORBIDDEN_SECRET_FIELDS = {
    "password",
    "password_value",
    "secret",
    "secret_value",
    "token",
    "api_key",
    "private_key",
    "credential",
}


def _number(value: object, label: str, *, minimum: float = 0) -> float:
    need(type(value) in (int, float) and value >= minimum, f"{label}: invalid number")
    return float(value)


def _identifier(value: object, label: str) -> str:
    need(isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None,
         f"{label}: invalid identifier")
    return value


def _path(value: object, label: str) -> str:
    need(isinstance(value, str) and value.strip() == value and len(value) >= 3,
         f"{label}: path is required")
    need("\n" not in value and "\r" not in value and "\0" not in value,
         f"{label}: invalid path")
    need(PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute(),
         f"{label}: path must be absolute")
    return value


def _walk_for_secrets(value: object) -> None:
    if isinstance(value, dict):
        for field, child in value.items():
            need(str(field).lower() not in FORBIDDEN_SECRET_FIELDS,
                 "Policy must contain secret references only, never secret values")
            _walk_for_secrets(child)
    elif isinstance(value, list):
        for child in value:
            _walk_for_secrets(child)


def _path_identity(value: str) -> str:
    return value.replace("/", "\\").rstrip("\\").casefold()


def _separate_paths(paths: list[tuple[str, str]]) -> None:
    normalized = [(label, _path_identity(path)) for label, path in paths]
    for index, (left_label, left) in enumerate(normalized):
        for right_label, right in normalized[index + 1:]:
            overlap = left == right or left.startswith(right + "\\") or right.startswith(left + "\\")
            need(not overlap, f"{left_label} and {right_label} storage paths overlap")


def validate_policy(value: object) -> dict:
    """Return a validated copy of an owner policy. No host access is performed."""
    _walk_for_secrets(value)
    keys(value, {"contract", "timezone", "host_device_id", "storage", "capacity",
                 "schedule", "notifications", "recovery_drill"}, "owner backup policy")
    need(value["contract"] == CONTRACT, "Unsupported owner backup policy contract")
    need(isinstance(value["timezone"], str) and 3 <= len(value["timezone"]) <= 64,
         "Timezone is required")
    host_device = _identifier(value["host_device_id"], "host device")

    storage = value["storage"]
    keys(storage, {"staging", "repositories", "key_custody"}, "storage")
    staging = storage["staging"]
    keys(staging, {"path", "device_id"}, "staging")
    staging_path = _path(staging["path"], "staging")
    need(_identifier(staging["device_id"], "staging device") == host_device,
         "Staging must identify the host device and is never an off-host copy")

    repositories = storage["repositories"]
    need(isinstance(repositories, list) and len(repositories) == 2,
         "Exactly one primary and one replica repository are required")
    repository_ids: set[str] = set()
    repository_devices: set[str] = set()
    repository_paths: list[tuple[str, str]] = []
    roles: set[str] = set()
    for item in repositories:
        keys(item, {"id", "role", "kind", "path", "device_id", "off_host",
                    "capacity_gib", "owner_confirmed"}, "repository")
        identifier = _identifier(item["id"], "repository")
        need(identifier not in repository_ids, "Repository identifiers must be unique")
        repository_ids.add(identifier)
        need(item["role"] in ("primary", "replica") and item["role"] not in roles,
             "Repository roles must be one primary and one replica")
        roles.add(item["role"])
        need(item["kind"] == "mounted-filesystem",
             "Only the reviewed mounted-filesystem repository adapter is supported")
        repository_paths.append((f"repository {identifier}", _path(item["path"], "repository")))
        device = _identifier(item["device_id"], "repository device")
        need(device != host_device and device not in repository_devices,
             "Repositories must use distinct devices away from the host")
        repository_devices.add(device)
        need(item["off_host"] is True, "Each repository must be owner-declared off-host")
        _number(item["capacity_gib"], "repository capacity", minimum=1)
        need(type(item["owner_confirmed"]) is bool, "Repository confirmation must be boolean")

    custody = storage["key_custody"]
    keys(custody, {"operational", "recovery_copies"}, "key custody")
    operational = custody["operational"]
    keys(operational, {"path", "device_id"}, "operational key")
    operational_path = _path(operational["path"], "operational key")
    operational_device = _identifier(operational["device_id"], "operational key device")
    need(operational_device not in repository_devices,
         "Operational key must not share a repository device")

    recovery_copies = custody["recovery_copies"]
    need(isinstance(recovery_copies, list) and len(recovery_copies) == 2,
         "Exactly two offline recovery-key copies are required")
    recovery_ids: set[str] = set()
    recovery_devices: set[str] = set()
    recovery_paths: list[tuple[str, str]] = []
    for item in recovery_copies:
        keys(item, {"id", "path", "device_id", "offline", "owner_confirmed"},
             "recovery key copy")
        identifier = _identifier(item["id"], "recovery key copy")
        need(identifier not in recovery_ids, "Recovery-key copy identifiers must be unique")
        recovery_ids.add(identifier)
        recovery_paths.append((f"recovery key {identifier}", _path(item["path"], "recovery key")))
        device = _identifier(item["device_id"], "recovery-key device")
        need(device != host_device and device not in repository_devices
             and device not in recovery_devices,
             "Recovery keys require two distinct offline devices, separate from host and repositories")
        recovery_devices.add(device)
        need(item["offline"] is True, "Recovery-key copies must be offline")
        need(type(item["owner_confirmed"]) is bool, "Recovery-key confirmation must be boolean")

    _separate_paths([("staging", staging_path), ("operational key", operational_path),
                     *repository_paths, *recovery_paths])

    capacity = value["capacity"]
    keys(capacity, {"minimum_free_gib", "modules"}, "capacity")
    _number(capacity["minimum_free_gib"], "minimum free capacity", minimum=1)
    modules = capacity["modules"]
    need(isinstance(modules, list) and len(modules) == len(MODULES),
         "Capacity must cover all six Phase 5 modules")
    found_modules: list[str] = []
    for item in modules:
        keys(item, {"id", "estimated_current_gib", "retention_reserve_gib",
                    "rpo_hours", "rto_hours"}, "module capacity")
        found_modules.append(_identifier(item["id"], "module"))
        _number(item["estimated_current_gib"], "estimated current data")
        _number(item["retention_reserve_gib"], "retention reserve", minimum=1)
        _number(item["rpo_hours"], "RPO", minimum=1)
        _number(item["rto_hours"], "RTO", minimum=1)
    need(tuple(found_modules) == MODULES,
         "Capacity modules must use the reviewed Phase 5 order exactly once")

    schedule = value["schedule"]
    keys(schedule, {"activation", "backup_slots", "full_check", "retention",
                    "restore_rehearsal", "task_settings"}, "schedule")
    need(schedule["activation"] == "disabled",
         "Design policies must keep scheduling disabled until a separate activation review")
    slots = schedule["backup_slots"]
    need(isinstance(slots, list) and len(slots) == len(MODULES),
         "One daily backup slot is required for each Phase 5 module")
    slot_modules: list[str] = []
    slot_times: set[str] = set()
    for slot in slots:
        keys(slot, {"module", "local_time"}, "backup slot")
        slot_modules.append(_identifier(slot["module"], "backup slot module"))
        need(isinstance(slot["local_time"], str) and TIME.fullmatch(slot["local_time"]),
             "Backup slot requires a valid 24-hour local time")
        need(slot["local_time"] not in slot_times, "Backup slots must be staggered")
        slot_times.add(slot["local_time"])
    need(tuple(slot_modules) == MODULES,
         "Backup slots must use the reviewed Phase 5 order exactly once")

    full_check = schedule["full_check"]
    keys(full_check, {"weekday", "local_time"}, "full check")
    need(full_check["weekday"] in ("Monday", "Tuesday", "Wednesday", "Thursday",
                                   "Friday", "Saturday", "Sunday"),
         "Invalid full-check weekday")
    need(isinstance(full_check["local_time"], str) and TIME.fullmatch(full_check["local_time"]),
         "Full check requires a valid local time")
    retention = schedule["retention"]
    keys(retention, {"daily", "weekly", "monthly", "preview_weekday",
                     "preview_local_time", "apply_requires_restore_verified"}, "retention")
    need({name: retention[name] for name in ("daily", "weekly", "monthly")} ==
         {"daily": 7, "weekly": 4, "monthly": 3},
         "Retention must remain the reviewed 7/4/3 policy")
    need(retention["preview_weekday"] in ("Monday", "Tuesday", "Wednesday", "Thursday",
                                           "Friday", "Saturday", "Sunday")
         and isinstance(retention["preview_local_time"], str)
         and TIME.fullmatch(retention["preview_local_time"]),
         "Retention preview schedule is invalid")
    need(retention["apply_requires_restore_verified"] is True,
         "Retention apply must remain restore-verified")
    need(schedule["restore_rehearsal"] == "quarterly-manual",
         "Restore rehearsal must remain quarterly and manual")
    settings = schedule["task_settings"]
    keys(settings, {"hidden", "multiple_instances", "start_when_available",
                    "execution_limit_minutes"}, "task settings")
    need(settings["hidden"] is True and settings["multiple_instances"] == "ignore-new"
         and settings["start_when_available"] is True,
         "Scheduled tasks must be hidden, non-overlapping and start when available")
    need(type(settings["execution_limit_minutes"]) is int
         and 30 <= settings["execution_limit_minutes"] <= 360,
         "Task execution limit must be between 30 and 360 minutes")

    notifications = value["notifications"]
    keys(notifications, {"required", "configured", "channel_reference",
                         "notify_on"}, "notifications")
    need(notifications["required"] is True and type(notifications["configured"]) is bool,
         "Failure notifications must be required")
    need(isinstance(notifications["channel_reference"], str)
         and len(notifications["channel_reference"]) >= 3,
         "Notification channel reference is required")
    need(notifications["notify_on"] == ["backup-failure", "missed-window",
                                         "full-check-failure", "replica-failure"],
         "Notification events must cover the reviewed failure set")

    drill = value["recovery_drill"]
    keys(drill, {"production_data_completed", "last_completed_utc",
                 "evidence_reference"}, "recovery drill")
    need(type(drill["production_data_completed"]) is bool,
         "Recovery-drill status must be boolean")
    need((drill["last_completed_utc"] is None
          and drill["evidence_reference"] is None)
         or (isinstance(drill["last_completed_utc"], str)
             and isinstance(drill["evidence_reference"], str)),
         "Recovery-drill date and evidence must be supplied together")
    return deepcopy(value)


def make_plan(value: object) -> dict:
    """Build a deterministic, non-executable owner plan and readiness decision."""
    policy = validate_policy(value)
    required = sum(float(item["estimated_current_gib"])
                   + float(item["retention_reserve_gib"])
                   for item in policy["capacity"]["modules"])
    required += float(policy["capacity"]["minimum_free_gib"])
    blockers: list[str] = []
    for repository in policy["storage"]["repositories"]:
        if float(repository["capacity_gib"]) < required:
            blockers.append(f'{repository["id"]}: declared capacity is below the policy minimum')
        if not repository["owner_confirmed"]:
            blockers.append(f'{repository["id"]}: off-host ownership/location not confirmed')
    for key_copy in policy["storage"]["key_custody"]["recovery_copies"]:
        if not key_copy["owner_confirmed"]:
            blockers.append(f'{key_copy["id"]}: offline recovery-key custody not confirmed')
    if not policy["notifications"]["configured"]:
        blockers.append("failure notification channel is not configured and tested")
    if not policy["recovery_drill"]["production_data_completed"]:
        blockers.append("representative production-data restore drill is not complete")
    unsigned = {
        "kind": "homelab-phase5-owner-backup-plan",
        "contract": CONTRACT,
        "execution": "disabled-design-only",
        "policy": policy,
        "capacity": {
            "minimum_per_repository_gib": round(required, 2),
            "calculation": "owner estimates plus explicit retention reserve and minimum free space",
        },
        "readiness": {
            "status": "ready-for-separate-activation-review" if not blockers else "blocked",
            "blockers": blockers,
            "activation_included": False,
        },
    }
    return {**unsigned, "plan_id": hashlib.sha256(canonical(unsigned).encode()).hexdigest()}


def public_plan(plan: dict) -> dict:
    """Redact private paths and device identities for terminal/public evidence."""
    result = deepcopy(plan)
    policy = result["policy"]
    policy["host_device_id"] = "<host-device>"
    policy["storage"]["staging"] = {
        "path": "<local-staging-path>", "device_id": "<host-device>"}
    for repository in policy["storage"]["repositories"]:
        repository["path"] = f'<{repository["role"]}-repository-path>'
        repository["device_id"] = f'<{repository["role"]}-repository-device>'
    policy["storage"]["key_custody"]["operational"] = {
        "path": "<operational-key-path>", "device_id": "<operational-key-device>"}
    for index, key_copy in enumerate(
            policy["storage"]["key_custody"]["recovery_copies"], start=1):
        key_copy["path"] = f"<offline-recovery-key-path-{index}>"
        key_copy["device_id"] = f"<offline-recovery-key-device-{index}>"
    policy["notifications"]["channel_reference"] = "<private-notification-reference>"
    if policy["recovery_drill"]["evidence_reference"] is not None:
        policy["recovery_drill"]["evidence_reference"] = "<private-evidence-reference>"
    return result
