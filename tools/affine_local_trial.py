"""Disposable local AFFiNE browser, backup and independent-restore rehearsal."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from homelab import affine
from homelab.config import ConfigError, need
from homelab.privatefs import atomic_json, create_private_directory
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
        status = affine.operate(plan, 'status')
        if status['state'] == 'running':
            affine.operate(plan, 'stop', plan['plan_id'])
        if status['state'] != 'removed':
            affine.operate(plan, 'remove', plan['plan_id'])
    except ConfigError:
        pass
    try:
        affine.docker(affine.compose_args(plan) + ['down', '--volumes', '--remove-orphans'],
                      context=plan['runtime']['context'], timeout=180)
    except ConfigError:
        pass


def progress(stage: str) -> None:
    print(json.dumps({'kind': 'affine-local-trial-progress-v1', 'stage': stage}),
          flush=True, file=sys.stderr)


def run(work_root: Path) -> dict:
    work_root = work_root.resolve()
    need(not work_root.exists() and work_root.parent.is_dir(),
         'Local trial root must be absent under an existing parent')
    create_private_directory(work_root)
    source_parent = private_directory(work_root, 'source-parent')
    backup_parent = private_directory(work_root, 'backup-parent')
    recovered_parent = private_directory(work_root, 'recovered-parent')
    source = affine.make_plan(source_parent / 'affine-source', 18024,
                              affine.local_runtime())
    recovered = None
    try:
        progress('source-up')
        affine.operate(source, 'up', source['plan_id'])
        progress('browser-exercise')
        exercised = affine.exercise(source, source['plan_id'])
        backup = backup_parent / 'affine-backup'
        progress('consistent-backup')
        affine.backup(source, backup, source['plan_id'])
        progress('backup-verification')
        manifest = affine.verify_backup(backup)
        progress('recovery-plan')
        recovered = affine.make_plan(recovered_parent / 'affine-recovered', 18025,
                                     affine.local_runtime(), backup)
        progress('independent-restore')
        first = affine.operate(recovered, 'up', recovered['plan_id'])
        progress('recovered-stop')
        affine.operate(recovered, 'stop', recovered['plan_id'])
        progress('recovered-restart')
        second = affine.operate(recovered, 'up', recovered['plan_id'])
        need(first['recovery'] is not None and first['recovery']['verified']
             and second['recovery'] is not None and second['recovery']['verified'],
             'Local AFFiNE independent restore or restart verification failed')
        proof = {
            'kind': 'homelab-affine-local-browser-recovery-proof',
            'browser_rendered': exercised['browser_rendered'],
            'browser_independent_sessions': True,
            'browser_reload_persistence': True,
            'browser_title_sha256': manifest['browser']['title_sha256'],
            'browser_body_sha256': manifest['browser']['body_sha256'],
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
