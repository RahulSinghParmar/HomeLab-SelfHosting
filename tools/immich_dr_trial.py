"""Bounded GitHub-hosted Immich encrypted recovery rehearsal."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from homelab import immich, immich_vault
from homelab.config import ConfigError, load_json, need
from homelab.doctor import host_architecture, host_platform
from homelab.privatefs import atomic_json, create_private_directory, verify_private
from homelab.sandbox import digest


SECRET_NAME = "IMMICH_DR_TEST_PASSWORD"


def private_root(path: Path) -> Path:
    path = path.resolve()
    need(not path.exists() and path.parent.is_dir(),
         "Trial root must be absent under an existing parent")
    create_private_directory(path)
    return path


def private_directory(parent: Path, name: str) -> Path:
    path = parent / name
    create_private_directory(path)
    return path


def write_secret(path: Path) -> None:
    value = os.environ.get(SECRET_NAME, "")
    need(48 <= len(value) <= 256
         and all(33 <= ord(character) <= 126 for character in value),
         "Synthetic recovery secret is unavailable or invalid")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
        stream.write(value + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o600)
    verify_private(path)


def require_linux_runner() -> None:
    need(host_platform() == "linux" and host_architecture() == "amd64",
         "Hosted recovery rehearsal requires a clean Linux amd64 runner")


def progress(stage: str) -> None:
    print(json.dumps({"recovery_stage": stage}, sort_keys=True), flush=True)


def prepare(work_root: Path, artifact_root: Path, restic: Path) -> dict:
    require_linux_runner()
    root = private_root(work_root)
    artifact = private_root(artifact_root)
    source_parent = private_directory(root, "source-parent")
    staging_parent = private_directory(root, "staging-parent")
    state_parent = private_directory(root, "state-parent")
    operational = private_directory(root, "operational-key") / "password.txt"
    recovery = private_directory(root, "recovery-key") / "password.txt"
    write_secret(operational)
    write_secret(recovery)

    runtime = immich.local_runtime()
    source_plan = immich.make_plan(source_parent / "immich-source", 18062, runtime)
    immich.operate(source_plan, "up", source_plan["plan_id"])
    exercise = immich.exercise(source_plan, source_plan["plan_id"])
    backup_root = staging_parent / "immich-backup"
    immich.backup(source_plan, backup_root, source_plan["plan_id"])

    repository = artifact / "repository"
    vault_plan = immich_vault.make_plan(
        state_parent / "vault-state", repository, operational, recovery, restic)
    immich_vault.initialize(vault_plan, vault_plan["plan_id"])
    snapshot_plan = immich_vault.make_snapshot_plan(vault_plan, backup_root)
    stored = immich_vault.store(vault_plan, snapshot_plan,
                                snapshot_plan["snapshot_plan_id"])
    immich_vault.check(vault_plan, vault_plan["plan_id"])
    local_restore = immich_vault.restore(
        vault_plan, snapshot_plan, stored["snapshot_id"], root / "local-decrypted",
        snapshot_plan["snapshot_plan_id"])
    recovery_manifest = immich_vault.make_recovery_manifest(
        vault_plan, snapshot_plan, local_restore["snapshot_id"])
    atomic_json(artifact / "recovery-manifest.json", recovery_manifest)

    immich.operate(source_plan, "stop", source_plan["plan_id"])
    immich.operate(source_plan, "remove", source_plan["plan_id"])
    return {
        "prepared": True,
        "original_sha256": exercise["sha256"],
        "original_bytes": exercise["bytes"],
        "snapshot_id": local_restore["snapshot_id"],
        "repository_id": recovery_manifest["repository_id"],
        "manifest_id": recovery_manifest["manifest_id"],
        "local_decryption_verified": local_restore["recovery_verified"],
        "derived_excluded": not recovery_manifest["derived_included"],
        "ml_cache_excluded": not recovery_manifest["ml_cache_included"],
        "encrypted_repository_only_in_artifact": True,
        "secret_in_artifact": False,
    }


def recover(work_root: Path, artifact_root: Path, restic: Path,
            proof_root: Path, artifact_digest: str, source_sha: str) -> dict:
    require_linux_runner()
    need(bool(re.fullmatch("[0-9a-f]{64}", artifact_digest)),
         "Immutable transport artifact digest is required")
    need(bool(re.fullmatch("[0-9a-f]{40}", source_sha)),
         "Exact source commit is required")
    root = private_root(work_root)
    proof_directory = private_root(proof_root)
    recovery_key = private_directory(root, "recovery-key") / "password.txt"
    write_secret(recovery_key)

    progress("verify-encrypted-transport")
    repository = (artifact_root / "repository").resolve()
    recovery_manifest = immich_vault.validate_recovery_manifest(
        load_json(artifact_root / "recovery-manifest.json"))
    recovery_plan = immich_vault.make_recovery_plan(
        repository, recovery_key, restic, recovery_manifest)
    encrypted = immich_vault.recover_off_host(
        recovery_plan, root / "decrypted", recovery_plan["plan_id"])
    restored_backup = Path(encrypted.pop("restore_root"))

    progress("restore-application")
    recovered_parent = private_directory(root, "recovered-parent")
    application_plan = immich.make_plan(
        recovered_parent / "immich-recovered", 18063,
        immich.local_runtime(), restored_backup)
    first = immich.operate(application_plan, "up", application_plan["plan_id"])
    expected = immich.verify_backup(restored_backup)["fixture"]
    need(first["recovery"] is not None and first["recovery"]["verified"]
         and first["recovery"]["original_sha256"] == expected["sha256"],
         "Recovered Immich original did not match")
    progress("verify-restart-persistence")
    immich.operate(application_plan, "stop", application_plan["plan_id"])
    second = immich.operate(application_plan, "up", application_plan["plan_id"])
    need(second["recovery"] is not None and second["recovery"]["verified"]
         and second["recovery"]["original_sha256"] == expected["sha256"],
         "Recovered Immich original did not persist across restart")
    immich.operate(application_plan, "stop", application_plan["plan_id"])
    immich.operate(application_plan, "remove", application_plan["plan_id"])

    progress("write-sanitized-proof")
    proof = {
        "kind": "homelab-immich-hosted-recovery-proof",
        "contract": immich_vault.RECOVERY_PLAN_CONTRACT,
        "source_commit": source_sha,
        "transport": {
            "provider": "github-actions-artifact",
            "sha256": artifact_digest,
            "contains_encrypted_repository": True,
            "contains_recovery_secret": False,
        },
        "clean_runner": True,
        "source_machine_state_used": False,
        "full_repository_data_check": encrypted["full_data_check"],
        "repository_id": encrypted["repository_id"],
        "snapshot_id": encrypted["snapshot_id"],
        "manifest_id": encrypted["manifest_id"],
        "summary_id": encrypted["summary_id"],
        "original_files": encrypted["original_files"],
        "original_bytes": encrypted["original_bytes"],
        "original_sha256": encrypted["fixture_sha256"],
        "derived_included": encrypted["derived_included"],
        "ml_cache_included": encrypted["ml_cache_included"],
        "recovery_platform": encrypted["platform"],
        "recovery_architecture": encrypted["architecture"],
        "restic_version": encrypted["restic_version"],
        "decryption_verified": True,
        "application_restore_verified": True,
        "restart_persistence_verified": True,
        "production_data_used": False,
    }
    proof["proof_id"] = digest(proof)
    atomic_json(proof_directory / "recovery-proof.json", proof)
    return proof


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    prepare_parser = actions.add_parser("prepare")
    prepare_parser.add_argument("--work-root", type=Path, required=True)
    prepare_parser.add_argument("--artifact-root", type=Path, required=True)
    prepare_parser.add_argument("--restic", type=Path, required=True)
    recover_parser = actions.add_parser("recover")
    recover_parser.add_argument("--work-root", type=Path, required=True)
    recover_parser.add_argument("--artifact-root", type=Path, required=True)
    recover_parser.add_argument("--restic", type=Path, required=True)
    recover_parser.add_argument("--proof-root", type=Path, required=True)
    recover_parser.add_argument("--artifact-digest", required=True)
    recover_parser.add_argument("--source-sha", required=True)
    arguments = parser.parse_args()
    try:
        result = (prepare(arguments.work_root, arguments.artifact_root, arguments.restic)
                  if arguments.action == "prepare"
                  else recover(arguments.work_root, arguments.artifact_root,
                               arguments.restic, arguments.proof_root,
                               arguments.artifact_digest, arguments.source_sha))
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except ConfigError as error:
        print("ERROR: " + str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
