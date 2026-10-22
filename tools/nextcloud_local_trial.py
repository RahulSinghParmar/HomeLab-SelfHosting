"""Disposable local Nextcloud WebDAV backup and independent-restore rehearsal."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homelab import nextcloud
from homelab.config import ConfigError, need
from homelab.privatefs import atomic_json, create_private_directory, read_private
from homelab.sandbox import digest


def private_directory(parent: Path, name: str) -> Path:
    path = parent / name
    create_private_directory(path)
    return path


def remove(plan: dict) -> None:
    root = Path(plan['root'])
    if not root.exists():
        return
    try:
        status = nextcloud.operate(plan, 'status')
        if status['state'] == 'running':
            nextcloud.operate(plan, 'stop', plan['plan_id'])
        if status['state'] != 'removed':
            nextcloud.operate(plan, 'remove', plan['plan_id'])
    except ConfigError:
        pass
    try:
        nextcloud.docker(
            nextcloud.compose_args(plan) + ['down', '--volumes', '--remove-orphans'],
            context=plan['runtime']['context'], timeout=180)
    except ConfigError:
        pass


def progress(stage: str) -> None:
    print(json.dumps({'kind': 'nextcloud-local-trial-progress-v1', 'stage': stage}),
          flush=True, file=sys.stderr)


def run(work_root: Path) -> dict:
    work_root = work_root.resolve()
    need(not work_root.exists() and work_root.parent.is_dir(),
         'Local trial root must be absent under an existing parent')
    create_private_directory(work_root)
    source_parent = private_directory(work_root, 'source-parent')
    backup_parent = private_directory(work_root, 'backup-parent')
    recovered_parent = private_directory(work_root, 'recovered-parent')
    source = nextcloud.make_plan(source_parent / 'nextcloud-source', 18030,
                                 nextcloud.local_runtime())
    recovered = None
    try:
        progress('source-up')
        nextcloud.operate(source, 'up', source['plan_id'])
        progress('webdav-exercise')
        exercised = nextcloud.exercise(source, source['plan_id'])
        backup = backup_parent / 'nextcloud-backup'
        progress('consistent-backup')
        nextcloud.backup(source, backup, source['plan_id'])
        progress('backup-verification')
        manifest = nextcloud.verify_backup(backup)
        progress('source-stop')
        nextcloud.operate(source, 'stop', source['plan_id'])
        progress('recovery-plan')
        recovered = nextcloud.make_plan(
            recovered_parent / 'nextcloud-recovered', 18031,
            nextcloud.local_runtime(), backup)
        progress('independent-restore')
        first = nextcloud.operate(recovered, 'up', recovered['plan_id'])
        first_fixture = nextcloud.fixture_evidence(
            recovered, read_private(Path(recovered['root']) / 'credentials.json'))
        progress('recovered-stop')
        nextcloud.operate(recovered, 'stop', recovered['plan_id'])
        progress('recovered-restart')
        second = nextcloud.operate(recovered, 'up', recovered['plan_id'])
        second_fixture = nextcloud.fixture_evidence(
            recovered, read_private(Path(recovered['root']) / 'credentials.json'))
        need(first['recovery'] is not None and first['recovery']['verified']
             and second['recovery'] is not None and second['recovery']['verified'],
             'Local Nextcloud independent restore or restart verification failed')
        need(first_fixture == manifest['fixture'] == second_fixture,
             'Recovered WebDAV bytes changed across restart')
        proof = {
            'kind': 'homelab-nextcloud-local-recovery-proof',
            'webdav_upload_download': exercised['status'] == 'passed',
            'background_job_run': exercised['background_job_run'],
            'fixture_sha256': manifest['fixture']['sha256'],
            'application_consistent_backup': True,
            'independent_restore': True,
            'restart_persistence': True,
            'production_data_used': False,
        }
        proof['proof_id'] = digest(proof)
        atomic_json(work_root / 'local-proof.json', proof)
        progress('complete')
        return proof
    finally:
        progress('cleanup')
        if recovered is not None:
            remove(recovered)
        remove(source)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-root', type=Path, required=True)
    arguments = parser.parse_args()
    try:
        print(json.dumps(run(arguments.work_root), sort_keys=True, indent=2))
        return 0
    except ConfigError as error:
        print('ERROR: ' + str(error))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
