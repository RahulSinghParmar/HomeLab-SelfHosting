"""Encrypted off-host recovery contracts for Jellyfin application state and media."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import UUID

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .doctor import host_architecture, host_platform
from .sandbox import digest


MODULE = ROOT / "modules/jellyfin"
SET_CONTRACT = "jellyfin-application-media-recovery-set-v1"
PORTABLE_CONTRACT = "jellyfin-portable-recovery-v1"
PROOF_CONTRACT = "jellyfin-encrypted-off-host-recovery-v1"
HOST = "homelab-jellyfin"
TAGS = ("jellyfin", "phase6-encrypted", "application-and-media")
VERIFIED_TAG = "recovery-verified"
RETENTION = {"daily": 7, "weekly": 4, "monthly": 3}
ARCHIVE_PATH = "application/jellyfin-backup.zip"
MEDIA_PATH = "media/originals/phase6-jellyfin-direct-play.mp4"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def specification() -> dict:
    return load_json(MODULE / "restic.json")


def file_sha256(path: str | Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.upper().startswith("RESTIC_"):
            environment.pop(name, None)
    return environment


def validate_tool(path: str | Path) -> dict:
    candidate = Path(path).resolve()
    need(candidate.is_file() and not candidate.is_symlink(),
         "Restic candidate must be one regular file")
    info = candidate.stat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
         and 1_000_000 <= info.st_size <= 100_000_000,
         "Restic candidate must be one bounded regular file")
    reviewed = specification()
    system, architecture = host_platform(), host_architecture()
    target = system + "_" + architecture
    need(target in ("windows_amd64", "linux_amd64") and target in reviewed,
         "Jellyfin vault supports reviewed Windows/Linux amd64 Restic only")
    need((system != "windows" or candidate.suffix.lower() == ".exe")
         and (system == "windows" or os.access(candidate, os.X_OK)),
         "Restic candidate is not executable on this platform")
    need(file_sha256(candidate) == reviewed[target]["executable_sha256"],
         "Restic executable checksum differs from the reviewed release")
    try:
        result = subprocess.run(
            [str(candidate), "version"], env=_clean_environment(),
            capture_output=True, text=True, timeout=15, shell=False, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ConfigError("Restic candidate could not be executed") from error
    expected = "restic " + reviewed["version"] + " "
    need(result.returncode == 0 and result.stdout.startswith(expected)
         and system + "/" + architecture in result.stdout,
         "Restic version/platform mismatch")
    return {"path": str(candidate), "version": reviewed["version"],
            "sha256": reviewed[target]["executable_sha256"],
            "archive_sha256": reviewed[target]["archive_sha256"]}


def _regular_file(path: Path, label: str) -> None:
    need(path.is_file() and not path.is_symlink(), f"{label} is unavailable")
    info = path.stat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
         f"{label} must be one regular non-hardlinked file")


def _iso(value: object, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ConfigError(f"{label} is invalid") from error
    need(parsed.tzinfo is not None, f"{label} must include a timezone")
    return parsed


def _validate_archive(path: Path, expected_entries: int) -> None:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = {name.replace("\\", "/").casefold()
                     for name in archive.namelist()}
            bad = archive.testzip()
    except zipfile.BadZipFile as error:
        raise ConfigError("Jellyfin application archive is not a valid ZIP") from error
    required = {"manifest.json", "config/system.xml", "database/users.json",
                "database/baseitems.json", "database/userdata.json"}
    need(bad is None and len(names) == expected_entries
         and required.issubset(names),
         "Jellyfin application archive content or integrity differs")


def write_recovery_set(application_archive: str | Path, media_file: str | Path,
                       destination: str | Path, backup: dict,
                       created_utc: str) -> dict:
    application_archive = Path(application_archive).resolve()
    media_file = Path(media_file).resolve()
    destination = Path(destination).resolve()
    _regular_file(application_archive, "Jellyfin application archive")
    _regular_file(media_file, "Owner-managed media fixture")
    need(not destination.exists() and destination.parent.is_dir(),
         "Recovery set requires an absent destination under an existing parent")
    need(not application_archive.is_relative_to(destination)
         and not media_file.is_relative_to(destination),
         "Recovery inputs must be outside the destination")
    options = {"Database": True, "Metadata": True,
               "Subtitles": True, "Trickplay": True}
    need(isinstance(backup, dict)
         and set(backup) >= {"server_version", "backup_engine_version", "options",
                         "zip_entries"}
         and re.fullmatch(r"12\.4\.\d+\.\d+", str(backup["server_version"]))
         and backup["backup_engine_version"] == "0.2.0"
         and backup["options"] == options
         and type(backup["zip_entries"]) is int and backup["zip_entries"] > 0,
         "Jellyfin backup evidence is incompatible with the recovery set")
    _iso(created_utc, "Recovery-set creation time")
    (destination / "application").mkdir(parents=True, mode=0o700)
    (destination / "media" / "originals").mkdir(parents=True, mode=0o700)
    archive_target = destination / ARCHIVE_PATH
    media_target = destination / MEDIA_PATH
    shutil.copy2(application_archive, archive_target)
    shutil.copy2(media_file, media_target)
    manifest = {
        "kind": "homelab-jellyfin-recovery-set",
        "contract": SET_CONTRACT,
        "created_utc": created_utc,
        "jellyfin_version": backup["server_version"],
        "application": {
            "path": ARCHIVE_PATH, "bytes": archive_target.stat().st_size,
            "sha256": file_sha256(archive_target),
            "backup_engine_version": backup["backup_engine_version"],
            "options": options, "zip_entries": backup["zip_entries"],
        },
        "media": {
            "path": MEDIA_PATH, "bytes": media_target.stat().st_size,
            "sha256": file_sha256(media_target), "owner_managed": True,
            "included_in_application_archive": False,
        },
        "production_data_used": False,
    }
    temporary = destination / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    os.replace(temporary, destination / "manifest.json")
    return validate_recovery_set(destination)


def validate_recovery_set(root: str | Path) -> dict:
    root = Path(root).resolve()
    need(root.is_dir() and not root.is_symlink(),
         "Jellyfin recovery-set root is unavailable")
    manifest_path = root / "manifest.json"
    _regular_file(manifest_path, "Jellyfin recovery manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConfigError("Jellyfin recovery manifest is invalid") from error
    keys(manifest, {"kind", "contract", "created_utc", "jellyfin_version",
                    "application", "media", "production_data_used"},
         "Jellyfin recovery manifest")
    need(manifest["kind"] == "homelab-jellyfin-recovery-set"
         and manifest["contract"] == SET_CONTRACT
         and re.fullmatch(r"12\.4\.\d+\.\d+", str(manifest["jellyfin_version"]))
         and manifest["production_data_used"] is False,
         "Unsupported Jellyfin recovery manifest")
    _iso(manifest["created_utc"], "Recovery-set creation time")
    application = manifest["application"]
    keys(application, {"path", "bytes", "sha256", "backup_engine_version",
                       "options", "zip_entries"}, "Jellyfin application material")
    media = manifest["media"]
    keys(media, {"path", "bytes", "sha256", "owner_managed",
                 "included_in_application_archive"}, "Jellyfin media material")
    expected_options = {"Database": True, "Metadata": True,
                        "Subtitles": True, "Trickplay": True}
    need(application["path"] == ARCHIVE_PATH
         and application["backup_engine_version"] == "0.2.0"
         and application["options"] == expected_options
         and type(application["zip_entries"]) is int
         and application["zip_entries"] > 0,
         "Jellyfin application material changed")
    need(media["path"] == MEDIA_PATH and media["owner_managed"] is True
         and media["included_in_application_archive"] is False,
         "Jellyfin media ownership boundary changed")
    archive_path, media_path = root / ARCHIVE_PATH, root / MEDIA_PATH
    _regular_file(archive_path, "Jellyfin application archive")
    _regular_file(media_path, "Owner-managed media fixture")
    for material, path, label in (
            (application, archive_path, "Jellyfin application archive"),
            (media, media_path, "Owner-managed media fixture")):
        need(type(material["bytes"]) is int and material["bytes"] > 0
             and SHA256.fullmatch(str(material["sha256"]))
             and path.stat().st_size == material["bytes"]
             and file_sha256(path) == material["sha256"],
             f"{label} differs from its manifest")
    _validate_archive(archive_path, application["zip_entries"])
    tree = list(root.rglob("*"))
    need(not any(path.is_symlink() for path in tree),
         "Jellyfin recovery set must not contain links")
    actual = {path.relative_to(root).as_posix()
              for path in tree if path.is_file()}
    need(actual == {"manifest.json", ARCHIVE_PATH, MEDIA_PATH},
         "Jellyfin recovery set contains unexpected or missing files")
    return json.loads(canonical(manifest))


def recovery_summary(manifest: dict) -> dict:
    need(isinstance(manifest, dict), "Jellyfin recovery manifest is required")
    return {
        "jellyfin_version": manifest["jellyfin_version"],
        "application_bytes": manifest["application"]["bytes"],
        "application_sha256": manifest["application"]["sha256"],
        "media_files": 1,
        "media_bytes": manifest["media"]["bytes"],
        "media_sha256": manifest["media"]["sha256"],
        "owner_managed_media": True,
    }


def make_portable_manifest(repository_id: str, snapshot_id: str,
                           recovery_set: dict, full_data_check_utc: str) -> dict:
    need(SHA256.fullmatch(str(repository_id))
         and SHA256.fullmatch(str(snapshot_id)),
         "Restic repository or snapshot identity is invalid")
    _iso(full_data_check_utc, "Full-data check time")
    summary = recovery_summary(recovery_set)
    set_id = digest(recovery_set)
    required_tags = sorted({*TAGS, VERIFIED_TAG, "manifest-" + set_id[:16]})
    value = {
        "kind": "homelab-jellyfin-portable-recovery",
        "contract": PORTABLE_CONTRACT,
        "repository_id": repository_id,
        "snapshot_id": snapshot_id,
        "recovery_set_id": set_id,
        "summary": summary,
        "summary_id": digest(summary),
        "restic_version": specification()["version"],
        "required_tags": required_tags,
        "full_data_check_utc": full_data_check_utc,
        "source_machine_state_required": False,
        "transport_contains_recovery_key": False,
    }
    value["recovery_manifest_id"] = digest(value)
    return validate_portable_manifest(value)


def validate_portable_manifest(value: object) -> dict:
    keys(value, {"kind", "contract", "repository_id", "snapshot_id",
                 "recovery_set_id", "summary", "summary_id", "restic_version",
                 "required_tags", "full_data_check_utc",
                 "source_machine_state_required", "transport_contains_recovery_key",
                 "recovery_manifest_id"}, "Portable Jellyfin recovery manifest")
    unsigned = {name: item for name, item in value.items()
                if name != "recovery_manifest_id"}
    set_id = value["recovery_set_id"]
    expected_tags = sorted({*TAGS, VERIFIED_TAG, "manifest-" + set_id[:16]})
    need(value["kind"] == "homelab-jellyfin-portable-recovery"
         and value["contract"] == PORTABLE_CONTRACT
         and value["restic_version"] == specification()["version"]
         and all(SHA256.fullmatch(str(value[name])) for name in
                 ("repository_id", "snapshot_id", "recovery_set_id", "summary_id"))
         and value["required_tags"] == expected_tags
         and value["source_machine_state_required"] is False
         and value["transport_contains_recovery_key"] is False
         and value["recovery_manifest_id"] == digest(unsigned),
         "Portable Jellyfin recovery manifest identity or policy changed")
    _iso(value["full_data_check_utc"], "Full-data check time")
    summary = value["summary"]
    keys(summary, {"jellyfin_version", "application_bytes", "application_sha256",
                   "media_files", "media_bytes", "media_sha256",
                   "owner_managed_media"}, "Portable Jellyfin recovery summary")
    need(re.fullmatch(r"12\.4\.\d+\.\d+", str(summary["jellyfin_version"]))
         and type(summary["application_bytes"]) is int
         and summary["application_bytes"] > 0
         and SHA256.fullmatch(str(summary["application_sha256"]))
         and summary["media_files"] == 1
         and type(summary["media_bytes"]) is int and summary["media_bytes"] > 0
         and SHA256.fullmatch(str(summary["media_sha256"]))
         and summary["owner_managed_media"] is True
         and value["summary_id"] == digest(summary),
         "Portable Jellyfin recovery summary is invalid")
    return json.loads(canonical(value))


def validate_offhost_proof(value: object) -> dict:
    keys(value, {"kind", "contract", "repository_id", "snapshot_id",
                 "recovery_manifest_id", "recovery_set_id", "summary_id",
                 "restic_version", "full_repository_data_check",
                 "encrypted_repository", "transport_contains_recovery_key",
                 "source_machine_state_used", "clean_target",
                 "application_restore_verified", "media_replica_restored",
                 "source_direct_play_exact", "restored_direct_play_exact",
                 "restart_direct_play_exact", "restart_persistence_verified",
                 "production_data_used", "production_service_changed",
                 "gpu_used", "transcode_requested", "trial_id", "proof_id"},
         "Jellyfin off-host recovery proof")
    unsigned = {name: item for name, item in value.items() if name != "proof_id"}
    need(value["kind"] == "homelab-jellyfin-off-host-recovery-proof"
         and value["contract"] == PROOF_CONTRACT
         and value["restic_version"] == specification()["version"]
         and all(SHA256.fullmatch(str(value[name])) for name in
                 ("repository_id", "snapshot_id", "recovery_manifest_id",
                  "recovery_set_id", "summary_id"))
         and all(value[name] is True for name in
                 ("full_repository_data_check", "encrypted_repository",
                  "clean_target", "application_restore_verified",
                  "media_replica_restored", "source_direct_play_exact",
                  "restored_direct_play_exact", "restart_direct_play_exact",
                  "restart_persistence_verified"))
         and all(value[name] is False for name in
                 ("transport_contains_recovery_key", "source_machine_state_used",
                  "production_data_used", "production_service_changed",
                  "gpu_used", "transcode_requested"))
         and value["proof_id"] == digest(unsigned),
         "Jellyfin off-host recovery proof is incomplete or unsafe")
    try:
        trial = UUID(str(value["trial_id"]))
    except ValueError as error:
        raise ConfigError("Jellyfin off-host trial identity is invalid") from error
    need(trial.version == 4, "Jellyfin off-host trial identity is invalid")
    return json.loads(canonical(value))
