"""Run a disposable local Immich encrypted-vault integration rehearsal."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from homelab import immich, immich_vault
from homelab.config import ConfigError, need
from homelab.privatefs import atomic_json, create_private_directory
from homelab.sandbox import digest


def _remove(plan: dict | None) -> None:
    if not plan:
        return
    try:
        status = immich.operate(plan, "status")
        if status["state"] == "running":
            immich.operate(plan, "stop", plan["plan_id"])
        immich.operate(plan, "remove", plan["plan_id"])
    except (ConfigError, OSError):
        pass


def run(work_root: Path, restic: Path) -> dict:
    root = work_root.resolve()
    need(not root.exists() and root.parent.is_dir(),
         "Trial root must be absent under an existing parent")
    create_private_directory(root)
    directories = {}
    for name in ("source-parent", "staging-parent", "state-parent", "repository-parent",
                 "operational-key", "recovery-key", "recovered-parent"):
        directories[name] = root / name
        create_private_directory(directories[name])
    operational = directories["operational-key"] / "password.txt"
    recovery = directories["recovery-key"] / "password.txt"
    immich_vault.create_keys(operational, recovery, "CREATE-IMMICH-RECOVERY-KEY")

    source_plan = None
    recovered_plan = None
    try:
        runtime = immich.local_runtime()
        source_plan = immich.make_plan(
            directories["source-parent"] / "immich-source", 18064, runtime)
        immich.operate(source_plan, "up", source_plan["plan_id"])
        exercise = immich.exercise(source_plan, source_plan["plan_id"])
        backup_root = directories["staging-parent"] / "immich-backup"
        immich.backup(source_plan, backup_root, source_plan["plan_id"])

        vault_plan = immich_vault.make_plan(
            directories["state-parent"] / "vault-state",
            directories["repository-parent"] / "repository",
            operational, recovery, restic)
        immich_vault.initialize(vault_plan, vault_plan["plan_id"])
        snapshot_plan = immich_vault.make_snapshot_plan(vault_plan, backup_root)
        stored = immich_vault.store(
            vault_plan, snapshot_plan, snapshot_plan["snapshot_plan_id"])
        checked = immich_vault.check(vault_plan, vault_plan["plan_id"])
        local_restore = immich_vault.restore(
            vault_plan, snapshot_plan, stored["snapshot_id"], root / "local-decrypted",
            snapshot_plan["snapshot_plan_id"])
        portable = immich_vault.make_recovery_manifest(
            vault_plan, snapshot_plan, local_restore["snapshot_id"])
        atomic_json(root / "recovery-manifest.json", portable)

        # Do not keep two disposable Immich application stacks running at once
        # on a memory-bounded Docker Desktop host. The encrypted repository and
        # portable manifest are complete before the source project is removed.
        immich.operate(source_plan, "stop", source_plan["plan_id"])
        immich.operate(source_plan, "remove", source_plan["plan_id"])
        source_plan = None

        recovery_plan = immich_vault.make_recovery_plan(
            Path(vault_plan["repository"]), recovery, restic, portable)
        recovered = immich_vault.recover_off_host(
            recovery_plan, root / "off-host-decrypted", recovery_plan["plan_id"])
        recovered_backup = Path(recovered.pop("restore_root"))
        recovered_plan = immich.make_plan(
            directories["recovered-parent"] / "immich-recovered", 18065,
            runtime, recovered_backup)
        first = immich.operate(recovered_plan, "up", recovered_plan["plan_id"])
        immich.operate(recovered_plan, "stop", recovered_plan["plan_id"])
        second = immich.operate(recovered_plan, "up", recovered_plan["plan_id"])
        expected = immich.verify_backup(recovered_backup)["fixture"]["sha256"]
        need(first["recovery"]["verified"] and second["recovery"]["verified"]
             and first["recovery"]["original_sha256"] == expected
             and second["recovery"]["original_sha256"] == expected,
             "Decrypted Immich original or restart persistence differs")
        retention = immich_vault.retention(vault_plan)
        proof = {
            "kind": "homelab-immich-local-vault-proof",
            "contract": immich_vault.RECOVERY_PLAN_CONTRACT,
            "original_sha256": expected,
            "original_bytes": portable["original_bytes"],
            "full_repository_data_check": checked["read_data"] == "all",
            "encrypted_repository": recovered["encrypted_repository"],
            "source_machine_state_used_for_recovery": recovered["source_machine_state_used"],
            "application_restore_verified": True,
            "restart_persistence_verified": True,
            "derived_included": recovered["derived_included"],
            "ml_cache_included": recovered["ml_cache_included"],
            "retention_preview_only": retention["mode"] == "preview",
            "off_host_device_verified": False,
            "production_data_used": False,
            "production_deployment_touched": False,
        }
        proof["proof_id"] = digest(proof)
        atomic_json(root / "local-proof.json", proof)
        return proof
    finally:
        _remove(recovered_plan)
        _remove(source_plan)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--restic", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.work_root, args.restic), sort_keys=True, indent=2))
        return 0
    except ConfigError as error:
        print("ERROR: " + str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
