"""Bounded GitHub-hosted Firefly encrypted recovery rehearsal."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from homelab import firefly, firefly_vault
from homelab.config import ConfigError, load_json, need
from homelab.doctor import host_architecture, host_platform
from homelab.privatefs import atomic_json, create_private_directory, verify_private
from homelab.sandbox import digest


SECRET_NAME = 'FIREFLY_DR_TEST_PASSWORD'


def private_root(path: Path) -> Path:
    path = path.resolve()
    need(not path.exists() and path.parent.is_dir(),
         'Trial root must be absent under an existing parent')
    create_private_directory(path)
    return path


def private_directory(parent: Path, name: str) -> Path:
    path = parent / name
    create_private_directory(path)
    return path


def write_secret(path: Path) -> None:
    value = os.environ.get(SECRET_NAME, '')
    need(len(value) >= 48 and len(value) <= 256
         and all(33 <= ord(character) <= 126 for character in value),
         'Synthetic recovery secret is unavailable or invalid')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'w', encoding='ascii', newline='\n') as stream:
        stream.write(value + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o600)
    verify_private(path)


def require_linux_runner() -> None:
    need(host_platform() == 'linux' and host_architecture() == 'amd64',
         'Hosted recovery rehearsal requires a clean Linux amd64 runner')


def progress(stage: str) -> None:
    print(json.dumps({'recovery_stage': stage}, sort_keys=True), flush=True)


def prepare(work_root: Path, artifact_root: Path, restic: Path) -> dict:
    require_linux_runner()
    root = private_root(work_root)
    artifact = private_root(artifact_root)
    source_parent = private_directory(root, 'source-parent')
    staging_parent = private_directory(root, 'staging-parent')
    state_parent = private_directory(root, 'state-parent')
    operational = private_directory(root, 'operational-key') / 'password.txt'
    recovery = private_directory(root, 'recovery-key') / 'password.txt'
    write_secret(operational)
    write_secret(recovery)

    progress('start-synthetic-source')
    runtime = firefly.local_runtime()
    source_plan = firefly.make_plan(
        source_parent / 'firefly-source', 18042, runtime)
    firefly.operate(source_plan, 'up', source_plan['plan_id'])
    progress('exercise-finance-fixture')
    exercise = firefly.exercise(source_plan, source_plan['plan_id'])
    progress('capture-application-backup')
    backup_root = staging_parent / 'firefly-backup'
    firefly.backup(source_plan, backup_root, source_plan['plan_id'])
    verified_backup = firefly.verify_backup(backup_root)

    progress('initialize-encrypted-repository')
    repository = artifact / 'repository'
    vault_plan = firefly_vault.make_plan(
        state_parent / 'vault-state', repository, operational, recovery, restic)
    firefly_vault.initialize(vault_plan, vault_plan['plan_id'])
    snapshot_plan = firefly_vault.make_snapshot_plan(vault_plan, backup_root)
    stored = firefly_vault.store(
        vault_plan, snapshot_plan, snapshot_plan['snapshot_plan_id'])
    progress('check-all-encrypted-data')
    firefly_vault.check(vault_plan, vault_plan['plan_id'])
    progress('verify-local-decryption')
    local_restore = firefly_vault.restore(
        vault_plan, snapshot_plan, stored['snapshot_id'], root / 'local-decrypted',
        snapshot_plan['snapshot_plan_id'])
    recovery_manifest = firefly_vault.make_recovery_manifest(
        vault_plan, snapshot_plan, local_restore['snapshot_id'])
    atomic_json(artifact / 'recovery-manifest.json', recovery_manifest)

    progress('remove-synthetic-source')
    firefly.operate(source_plan, 'stop', source_plan['plan_id'])
    firefly.operate(source_plan, 'remove', source_plan['plan_id'])
    return {
        'prepared': True,
        'transaction_groups': verified_backup['summary']['transaction_groups'],
        'attachment_bytes': verified_backup['summary']['attachment_bytes'],
        'attachment_sha256': verified_backup['summary']['attachment_sha256'],
        'upload_files': verified_backup['summary']['upload_files'],
        'export_files': verified_backup['summary']['export_files'],
        'finance_fixture_verified': exercise['status'] == 'passed',
        'background_job_run': exercise['background_job_run'],
        'snapshot_id': local_restore['snapshot_id'],
        'repository_id': recovery_manifest['repository_id'],
        'manifest_id': recovery_manifest['manifest_id'],
        'local_decryption_verified': local_restore['recovery_verified'],
        'encrypted_repository_only_in_artifact': True,
        'secret_in_artifact': False,
    }


def recover(work_root: Path, artifact_root: Path, restic: Path,
            proof_root: Path, artifact_digest: str, source_sha: str) -> dict:
    require_linux_runner()
    need(bool(re.fullmatch('[0-9a-f]{64}', artifact_digest)),
         'Immutable transport artifact digest is required')
    need(bool(re.fullmatch('[0-9a-f]{40}', source_sha)),
         'Exact source commit is required')
    root = private_root(work_root)
    proof_directory = private_root(proof_root)
    key_directory = private_directory(root, 'recovery-key')
    recovery_key = key_directory / 'password.txt'
    write_secret(recovery_key)

    progress('verify-encrypted-transport')
    repository = (artifact_root / 'repository').resolve()
    recovery_manifest = firefly_vault.validate_recovery_manifest(
        load_json(artifact_root / 'recovery-manifest.json'))
    recovery_plan = firefly_vault.make_recovery_plan(
        repository, recovery_key, restic, recovery_manifest)
    encrypted = firefly_vault.recover_off_host(
        recovery_plan, root / 'decrypted', recovery_plan['plan_id'])
    restored_backup = Path(encrypted.pop('restore_root'))

    progress('restore-application-backup')
    recovered_parent = private_directory(root, 'recovered-parent')
    application_plan = firefly.make_plan(
        recovered_parent / 'firefly-recovered', 18043,
        firefly.local_runtime(), restored_backup)
    first = firefly.operate(application_plan, 'up', application_plan['plan_id'])
    restored_manifest = firefly.verify_backup(restored_backup)
    expected = restored_manifest['fixture']
    first_fixture = firefly.fixture_evidence(application_plan)
    need(first['recovery'] is not None and first['recovery']['verified']
         and first_fixture == expected,
         'Recovered Firefly finance content did not match')

    progress('verify-restart-persistence')
    firefly.operate(application_plan, 'stop', application_plan['plan_id'])
    second = firefly.operate(application_plan, 'up', application_plan['plan_id'])
    second_fixture = firefly.fixture_evidence(application_plan)
    need(second['recovery'] is not None and second['recovery']['verified']
         and second_fixture == expected,
         'Recovered Firefly finance content did not persist across restart')
    firefly.operate(application_plan, 'stop', application_plan['plan_id'])
    firefly.operate(application_plan, 'remove', application_plan['plan_id'])

    progress('write-sanitized-proof')
    proof = {
        'kind': 'homelab-firefly-hosted-recovery-proof',
        'contract': firefly_vault.RECOVERY_PLAN_CONTRACT,
        'source_commit': source_sha,
        'transport': {
            'provider': 'github-actions-artifact',
            'sha256': artifact_digest,
            'contains_encrypted_repository': True,
            'contains_recovery_secret': False,
        },
        'clean_runner': True,
        'source_machine_state_used': False,
        'full_repository_data_check': encrypted['full_data_check'],
        'repository_id': encrypted['repository_id'],
        'snapshot_id': encrypted['snapshot_id'],
        'manifest_id': encrypted['manifest_id'],
        'summary_id': encrypted['summary_id'],
        'transaction_groups': encrypted['transaction_groups'],
        'attachment_bytes': encrypted['attachment_bytes'],
        'attachment_sha256': encrypted['attachment_sha256'],
        'upload_files': encrypted['upload_files'],
        'export_files': encrypted['export_files'],
        'recovery_platform': encrypted['platform'],
        'recovery_architecture': encrypted['architecture'],
        'restic_version': encrypted['restic_version'],
        'decryption_verified': True,
        'application_restore_verified': True,
        'finance_content_verified': first_fixture == expected,
        'restart_persistence_verified': second_fixture == expected,
        'production_data_used': False,
    }
    proof['proof_id'] = digest(proof)
    atomic_json(proof_directory / 'recovery-proof.json', proof)
    return proof


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    prepare_parser = actions.add_parser('prepare')
    prepare_parser.add_argument('--work-root', type=Path, required=True)
    prepare_parser.add_argument('--artifact-root', type=Path, required=True)
    prepare_parser.add_argument('--restic', type=Path, required=True)
    recover_parser = actions.add_parser('recover')
    recover_parser.add_argument('--work-root', type=Path, required=True)
    recover_parser.add_argument('--artifact-root', type=Path, required=True)
    recover_parser.add_argument('--restic', type=Path, required=True)
    recover_parser.add_argument('--proof-root', type=Path, required=True)
    recover_parser.add_argument('--artifact-digest', required=True)
    recover_parser.add_argument('--source-sha', required=True)
    arguments = parser.parse_args()
    try:
        result = (prepare(arguments.work_root, arguments.artifact_root, arguments.restic)
                  if arguments.action == 'prepare'
                  else recover(arguments.work_root, arguments.artifact_root,
                               arguments.restic, arguments.proof_root,
                               arguments.artifact_digest, arguments.source_sha))
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except ConfigError as error:
        print('ERROR: ' + str(error))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
