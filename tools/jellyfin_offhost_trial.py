"""Disposable encrypted off-host Jellyfin application and media recovery trial."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homelab.config import ConfigError, load_json, need
from homelab.jellyfin_vault import (
    HOST, TAGS, VERIFIED_TAG, file_sha256, make_portable_manifest,
    validate_offhost_proof, validate_portable_manifest, validate_recovery_set,
    validate_tool, write_recovery_set,
)
from homelab.privatefs import create_private_directory, windows_acl
from homelab.sandbox import digest
from tools.jellyfin_native_trial import (
    FIXTURE_NAME, add_library, atomic_json, create_backup, direct_play,
    find_fixture, login, make_fixture, network_xml, setup, start, stop,
    wait_library_idle, wait_ready,
)


CONFIRM = "RUN-ENCRYPTED-OFFHOST-JELLYFIN-TRIAL"


def progress(stage: str) -> None:
    print(json.dumps({"recovery_stage": stage}, sort_keys=True), flush=True)


def ensure_absent(path: Path, label: str) -> Path:
    path = path.resolve()
    need(path.is_absolute() and not path.exists() and path.parent.is_dir(),
         f"{label} must be absent under an existing parent")
    return path


def private_key(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    if os.name == "nt":
        windows_acl(path, create=True)
    else:
        path.chmod(0o600)


def restic(binary: Path, repository: Path, key: Path, arguments: list[str],
           timeout: int = 1800) -> str:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.upper().startswith("RESTIC_"):
            environment.pop(name, None)
    environment.update({"RESTIC_REPOSITORY": str(repository),
                        "RESTIC_PASSWORD_FILE": str(key)})
    result = subprocess.run([str(binary), *arguments], env=environment,
                            capture_output=True, text=True, timeout=timeout,
                            shell=False, check=False,
                            creationflags=(subprocess.CREATE_NO_WINDOW
                                           if os.name == "nt" else 0))
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-1200:]
        raise ConfigError(f"Restic {arguments[0]} failed: {detail}")
    return result.stdout


def json_lines(value: str) -> list[dict]:
    rows = []
    for line in value.splitlines():
        if line.strip():
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise ConfigError("Restic returned invalid JSON") from error
            if isinstance(item, dict):
                rows.append(item)
    return rows


def repository_id(binary: Path, repository: Path, key: Path) -> str:
    try:
        value = json.loads(restic(binary, repository, key, ["cat", "config"]))
    except json.JSONDecodeError as error:
        raise ConfigError("Restic repository configuration is invalid") from error
    identity = value.get("id") if isinstance(value, dict) else None
    need(isinstance(identity, str) and len(identity) == 64,
         "Restic repository identity is invalid")
    return identity


def snapshot_id(output: str) -> str:
    summaries = [row for row in json_lines(output)
                 if row.get("message_type") == "summary"]
    identity = summaries[-1].get("snapshot_id") if summaries else None
    need(isinstance(identity, str) and len(identity) == 64,
         "Restic did not return one full snapshot identity")
    return identity


def tag_verified(binary: Path, repository: Path, key: Path,
                 identity: str) -> str:
    rows = json_lines(restic(
        binary, repository, key,
        ["tag", "--json", "--add", VERIFIED_TAG, identity]))
    changed = [row for row in rows if row.get("message_type") == "changed"]
    need(len(changed) == 1 and changed[0].get("old_snapshot_id") == identity,
         "Restic did not verify one snapshot tag transition")
    replacement = changed[0].get("new_snapshot_id")
    need(isinstance(replacement, str) and len(replacement) == 64,
         "Restic verified snapshot identity is invalid")
    return replacement


def find_set(target: Path) -> Path:
    candidates = []
    for manifest in target.rglob("manifest.json"):
        try:
            validate_recovery_set(manifest.parent)
            candidates.append(manifest.parent)
        except ConfigError:
            pass
    need(len(candidates) == 1, "Restic restore did not contain one recovery set")
    return candidates[0]


def snapshot_matches(binary: Path, repository: Path, key: Path,
                     portable: dict) -> None:
    try:
        rows = json.loads(restic(binary, repository, key,
                                 ["snapshots", "--json", portable["snapshot_id"]]))
    except json.JSONDecodeError as error:
        raise ConfigError("Restic snapshot listing is invalid") from error
    need(isinstance(rows, list) and len(rows) == 1
         and rows[0].get("id") == portable["snapshot_id"]
         and set(portable["required_tags"]).issubset(set(rows[0].get("tags") or [])),
         "Encrypted repository snapshot or recovery tags differ")


def restore_application(base: str, state: Path, media: Path, archive: Path,
                        binary: Path, web: Path, ffmpeg: Path, password: str,
                        port: int) -> tuple[dict, dict]:
    network_xml(state / "config" / "network.xml", port)
    process = start(binary, state, web, ffmpeg)
    try:
        info = wait_ready(base, process)
        need(info.get("StartupWizardCompleted") is False,
             "Recovery target was not a fresh Jellyfin instance")
        temporary_auth = setup(base, secrets.token_urlsafe(48))
        stop(base, process, temporary_auth["token"])
        process = None
        process = start(binary, state, web, ffmpeg, archive)
        try:
            restored_info = wait_ready(base, process)
        except ConfigError:
            if process.poll() == 0:
                process = start(binary, state, web, ffmpeg)
                restored_info = wait_ready(base, process)
            else:
                raise
        auth = login(base, password)
        item = find_fixture(base, auth["token"])
        playback = direct_play(base, auth["token"], item, media)
        stop(base, process, auth["token"])
        process = None
        return restored_info, playback
    finally:
        if process is not None:
            stop(base, process, None)


def run(work_root: Path, transport_root: Path, key_root: Path, output: Path,
        restic_binary: Path, jellyfin_binary: Path, web: Path, ffmpeg: Path,
        port: int, keep: bool = False) -> dict:
    work_root = ensure_absent(work_root, "Trial work root")
    transport_root = ensure_absent(transport_root, "Encrypted transport root")
    key_root = ensure_absent(key_root, "Recovery-key root")
    output = output.resolve()
    need(output.is_absolute() and not output.exists() and output.parent.is_dir(),
         "Evidence output must be an absent file under an existing parent")
    for first in (work_root, transport_root, key_root, output):
        for second in (work_root, transport_root, key_root, output):
            if first != second:
                need(not first.is_relative_to(second) and not second.is_relative_to(first),
                     "Trial, transport, key and evidence paths must not overlap")
    need(os.name == "nt" and 1024 <= port <= 65535 and port != 8096,
         "Use Windows and a non-production unprivileged Jellyfin port")
    need(jellyfin_binary.is_file() and web.is_dir() and ffmpeg.is_file(),
         "Installed Jellyfin binary, web assets or bundled FFmpeg are unavailable")
    tool = validate_tool(restic_binary)
    base = f"http://127.0.0.1:{port}"
    repository = transport_root / "repository"
    transport_manifest = transport_root / "recovery-manifest.json"
    operational_key = work_root / "operational-key" / "password.txt"
    recovery_key = key_root / "password.txt"
    source_state = work_root / "source-state"
    source_media = work_root / "media"
    fixture_path = source_media / FIXTURE_NAME
    staging_parent = work_root / "staging"
    application_archive = staging_parent / "jellyfin-backup.zip"
    recovery_set = work_root / "recovery-set"
    local_restore = work_root / "local-decrypted"
    password = secrets.token_urlsafe(48)
    source_process = None
    restored_process = None
    success = False
    create_private_directory(work_root)
    create_private_directory(transport_root)
    create_private_directory(key_root)
    try:
        secret = (secrets.token_urlsafe(64) + "\n").encode("ascii")
        private_key(operational_key, secret)
        private_key(recovery_key, secret)
        progress("create-source-application-and-media")
        fixture = make_fixture(ffmpeg, fixture_path)
        network_xml(source_state / "config" / "network.xml", port)
        source_process = start(jellyfin_binary, source_state, web, ffmpeg)
        source_info = wait_ready(base, source_process)
        need(source_info.get("StartupWizardCompleted") is False,
             "Disposable source was not a fresh Jellyfin instance")
        source_auth = setup(base, password)
        add_library(base, source_auth["token"], source_media)
        source_item = find_fixture(base, source_auth["token"])
        wait_library_idle(base, source_auth["token"])
        source_direct = direct_play(base, source_auth["token"], source_item,
                                    fixture_path)
        backup = create_backup(base, source_auth["token"], source_state,
                               application_archive)
        set_manifest = write_recovery_set(
            application_archive, fixture_path, recovery_set, backup,
            datetime.now(timezone.utc).isoformat())
        stop(base, source_process, source_auth["token"])
        source_process = None

        progress("encrypt-and-locally-verify")
        repository.mkdir()
        restic(restic_binary, repository, operational_key, ["init"])
        tags = [*TAGS, "manifest-" + digest(set_manifest)[:16]]
        command = ["backup", "--json", "--host", HOST]
        for tag in tags:
            command.extend(["--tag", tag])
        command.append(str(recovery_set))
        stored_id = snapshot_id(restic(restic_binary, repository, operational_key,
                                       command))
        restic(restic_binary, repository, operational_key,
               ["restore", stored_id, "--target", str(local_restore)])
        local_set = find_set(local_restore)
        need(validate_recovery_set(local_set) == set_manifest,
             "Local encrypted recovery-set validation changed")
        verified_id = tag_verified(restic_binary, repository, operational_key,
                                   stored_id)
        restic(restic_binary, repository, operational_key,
               ["check", "--read-data"])
        checked = datetime.now(timezone.utc).isoformat()
        portable = make_portable_manifest(
            repository_id(restic_binary, repository, operational_key),
            verified_id, set_manifest, checked)
        snapshot_matches(restic_binary, repository, operational_key, portable)
        atomic_json(transport_manifest, portable)
        need(not recovery_key.is_relative_to(transport_root)
             and not operational_key.is_relative_to(transport_root),
             "Encrypted transport must not contain recovery keys")

        progress("destroy-source-and-operational-custody")
        shutil.rmtree(work_root)
        need(not work_root.exists() and transport_root.is_dir()
             and recovery_key.is_file(),
             "Source destruction or independent recovery custody failed")
        create_private_directory(work_root)

        progress("recover-from-off-host-material-only")
        portable = validate_portable_manifest(load_json(transport_manifest))
        need(repository_id(restic_binary, repository, recovery_key)
             == portable["repository_id"],
             "Recovered repository identity changed")
        restic(restic_binary, repository, recovery_key,
               ["check", "--read-data"])
        snapshot_matches(restic_binary, repository, recovery_key, portable)
        offhost_restore = work_root / "offhost-decrypted"
        restic(restic_binary, repository, recovery_key,
               ["restore", portable["snapshot_id"], "--target",
                str(offhost_restore)])
        recovered_set = find_set(offhost_restore)
        recovered_manifest = validate_recovery_set(recovered_set)
        need(digest(recovered_manifest) == portable["recovery_set_id"],
             "Recovered set identity differs from transported evidence")
        recovered_media = recovered_set / recovered_manifest["media"]["path"]
        recovered_archive = recovered_set / recovered_manifest["application"]["path"]
        recovered_media_target = work_root / "media" / FIXTURE_NAME
        recovered_media_target.parent.mkdir(parents=True)
        shutil.copy2(recovered_media, recovered_media_target)
        need(file_sha256(recovered_media_target) == fixture["sha256"],
             "Owner-managed media replica changed during recovery")

        progress("restore-application-and-test-direct-play")
        restored_state = work_root / "restored-state"
        restored_info, restored_direct = restore_application(
            base, restored_state, recovered_media_target, recovered_archive,
            jellyfin_binary, web, ffmpeg, password, port)
        restored_process = start(jellyfin_binary, restored_state, web, ffmpeg)
        restart_info = wait_ready(base, restored_process)
        restart_auth = login(base, password)
        restart_item = find_fixture(base, restart_auth["token"])
        restart_direct = direct_play(
            base, restart_auth["token"], restart_item, recovered_media_target)
        stop(base, restored_process, restart_auth["token"])
        restored_process = None
        need(restored_info.get("Version") == source_info.get("Version")
             and restart_info.get("Version") == source_info.get("Version"),
             "Recovered Jellyfin version differs from the source")

        proof = {
            "kind": "homelab-jellyfin-off-host-recovery-proof",
            "contract": "jellyfin-encrypted-off-host-recovery-v1",
            "repository_id": portable["repository_id"],
            "snapshot_id": portable["snapshot_id"],
            "recovery_manifest_id": portable["recovery_manifest_id"],
            "recovery_set_id": portable["recovery_set_id"],
            "summary_id": portable["summary_id"],
            "restic_version": tool["version"],
            "full_repository_data_check": True,
            "encrypted_repository": True,
            "transport_contains_recovery_key": False,
            "source_machine_state_used": False,
            "clean_target": True,
            "application_restore_verified": True,
            "media_replica_restored": True,
            "source_direct_play_exact": source_direct["exact"],
            "restored_direct_play_exact": restored_direct["exact"],
            "restart_direct_play_exact": restart_direct["exact"],
            "restart_persistence_verified": True,
            "production_data_used": False,
            "production_service_changed": False,
            "gpu_used": False,
            "transcode_requested": False,
            "trial_id": str(uuid.uuid4()),
        }
        proof["proof_id"] = digest(proof)
        proof = validate_offhost_proof(proof)
        atomic_json(output, proof)
        success = True
        return proof
    finally:
        if source_process is not None:
            stop(base, source_process, None)
        if restored_process is not None:
            stop(base, restored_process, None)
        if success and not keep:
            for path in (work_root, transport_root, key_root):
                shutil.rmtree(path, ignore_errors=False)


def main(arguments=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--transport-root", type=Path, required=True)
    parser.add_argument("--key-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--restic", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--web", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18097)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(arguments)
    try:
        need(args.confirm == CONFIRM, f"Confirmation must equal {CONFIRM}")
        value = run(args.work_root, args.transport_root, args.key_root,
                    args.output, args.restic.resolve(), args.binary.resolve(),
                    args.web.resolve(), args.ffmpeg.resolve(), args.port,
                    args.keep)
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    except (ConfigError, OSError, subprocess.SubprocessError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
