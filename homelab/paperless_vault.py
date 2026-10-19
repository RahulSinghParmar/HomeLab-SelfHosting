"""Encrypted restic repository for verified Paperless application-aware backups."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
import stat
import subprocess
import uuid

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .doctor import host_architecture, host_platform
from .paperless import backup_summary, verify_backup
from .privatefs import (atomic_json, create_lock_file, create_private_directory,
                        operation_lock, read_private, safe_path, verify_private, windows_acl)
from .sandbox import digest, pending_guard


MODULE = ROOT / 'modules/paperless-ngx'
CONTRACT = 'paperless-restic-vault-v1'
RECOVERY_CONTRACT = 'paperless-portable-recovery-v1'
RECOVERY_PLAN_CONTRACT = 'paperless-off-host-restore-v1'
HOST = 'homelab-paperless'
TAGS = ('paperless-ngx', 'phase5-encrypted')
VERIFIED_TAG = 'recovery-verified'
RETENTION = {'daily': 7, 'weekly': 4, 'monthly': 3}


def specification():
    return load_json(MODULE / 'restic.json')


def file_sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def _clean_environment():
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.upper().startswith('RESTIC_'):
            environment.pop(name, None)
    return environment


def validate_tool(path):
    path = safe_path(Path(path))
    info = path.stat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 1_000_000 <= info.st_size <= 100_000_000,
         'Restic candidate must be one bounded regular file')
    reviewed = specification()
    system, architecture = host_platform(), host_architecture()
    target = system + '_' + architecture
    need(target in ('windows_amd64', 'linux_amd64') and target in reviewed,
         'This restic milestone is certified only on Windows amd64 and Linux amd64')
    need((system != 'windows' or path.suffix.lower() == '.exe')
         and (system == 'windows' or os.access(path, os.X_OK)),
         'Restic candidate is not executable on this platform')
    need(file_sha256(path) == reviewed[target]['executable_sha256'],
         'Restic executable checksum differs from the reviewed official archive')
    try:
        result = subprocess.run([str(path), 'version'], env=_clean_environment(), capture_output=True,
                                text=True, timeout=15, shell=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ConfigError('Restic candidate could not be executed') from error
    expected = 'restic ' + reviewed['version'] + ' '
    need(result.returncode == 0 and result.stdout.startswith(expected)
         and system + '/' + architecture in result.stdout, 'Restic version/platform mismatch')
    return {'path': str(path), 'version': reviewed['version'],
            'sha256': reviewed[target]['executable_sha256'],
            'archive_sha256': reviewed[target]['archive_sha256']}


def _key_bytes(path):
    path = safe_path(Path(path))
    verify_private(path)
    need(32 <= path.stat().st_size <= 512, 'Recovery key file has an invalid size')
    value = path.read_bytes()
    stripped = value.rstrip(b'\r\n')
    need(value in (stripped, stripped + b'\n', stripped + b'\r\n')
         and len(stripped) >= 32 and all(33 <= byte <= 126 for byte in stripped),
         'Recovery key file must contain one strong printable line')
    return stripped


def validate_key_custody(password_file, recovery_key_file):
    password_file = safe_path(Path(password_file))
    recovery_key_file = safe_path(Path(recovery_key_file))
    need(password_file != recovery_key_file, 'Operational and recovery key files must be distinct')
    need(password_file.parent != recovery_key_file.parent,
         'Operational and recovery key files must use different directories')
    first, second = _key_bytes(password_file), _key_bytes(recovery_key_file)
    need(hmac.compare_digest(first, second), 'Operational and recovery key files do not match')
    return {'password_file': str(password_file), 'recovery_key_file': str(recovery_key_file),
            'different_volumes': password_file.anchor.lower() != recovery_key_file.anchor.lower()}


def validate_recovery_key(path):
    path = safe_path(Path(path))
    _key_bytes(path)
    return str(path)


def create_keys(password_file, recovery_key_file, confirmation):
    need(confirmation == 'CREATE-PAPERLESS-RECOVERY-KEY',
         'Confirm CREATE-PAPERLESS-RECOVERY-KEY to generate key files')
    password_file = safe_path(Path(password_file))
    recovery_key_file = safe_path(Path(recovery_key_file))
    need(password_file != recovery_key_file and password_file.parent != recovery_key_file.parent,
         'Operational and recovery key files must use different directories')
    need(password_file.parent.is_dir() and recovery_key_file.parent.is_dir(),
         'Create both private key directories first')
    need(not password_file.exists() and not recovery_key_file.exists(),
         'Key generation requires two absent destination files')
    value = (secrets.token_urlsafe(64) + '\n').encode('ascii')
    created = []
    try:
        for path in (password_file, recovery_key_file):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                 | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            created.append(path)
            if os.name == 'nt':
                windows_acl(path, create=True)
            verify_private(path)
        validate_key_custody(password_file, recovery_key_file)
    except (OSError, ConfigError) as error:
        raise ConfigError('Recovery key generation failed; inspect both exact destinations') from error
    return {'created': True, 'secret_displayed': False,
            'password_file': str(password_file), 'recovery_key_file': str(recovery_key_file),
            'different_volumes': password_file.anchor.lower() != recovery_key_file.anchor.lower()}


def _separate(paths):
    for index, path in enumerate(paths):
        for other in paths[index + 1:]:
            need(not path.is_relative_to(other) and not other.is_relative_to(path),
                 'Vault storage, state and key paths must not overlap')


def make_plan(state_root, repository, password_file, recovery_key_file, restic_binary):
    state_root = safe_path(Path(state_root))
    repository = safe_path(Path(repository))
    tool = validate_tool(restic_binary)
    custody = validate_key_custody(password_file, recovery_key_file)
    key_paths = [Path(custody['password_file']), Path(custody['recovery_key_file'])]
    _separate([state_root, repository, *key_paths])
    need(state_root.parent.is_dir() and repository.parent.is_dir(),
         'Vault state and repository parents must already exist')
    plan = {'kind': 'homelab-paperless-vault-plan', 'contract': CONTRACT,
            'platform': host_platform(), 'state_root': str(state_root),
            'repository': str(repository), 'tool': tool, 'key_custody': custody,
            'host': HOST, 'tags': list(TAGS), 'verified_tag': VERIFIED_TAG,
            'retention': RETENTION, 'source_policy': 'verified-paperless-backup-only',
            'cache': 'disabled', 'off_host_verified': False}
    plan['plan_id'] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'state_root', 'repository', 'tool',
                'key_custody', 'host', 'tags', 'verified_tag', 'retention', 'source_policy',
                'cache', 'off_host_verified', 'plan_id'}, 'Paperless vault plan')
    need(plan['kind'] == 'homelab-paperless-vault-plan' and plan['contract'] == CONTRACT,
         'Unsupported Paperless vault plan')
    rebuilt = make_plan(plan['state_root'], plan['repository'],
                        plan['key_custody']['password_file'],
                        plan['key_custody']['recovery_key_file'], plan['tool']['path'])
    need(canonical(plan) == canonical(rebuilt), 'Vault plan/tool/key drift; review a new plan')
    return plan


def _restic(plan, arguments, *, cwd=None, timeout=900):
    environment = _clean_environment()
    environment['RESTIC_PASSWORD_FILE'] = plan['key_custody']['password_file']
    command = [plan['tool']['path'], '--repo', plan['repository'], '--no-cache', *arguments]
    try:
        result = subprocess.run(command, cwd=str(cwd) if cwd else None, env=environment,
                                capture_output=True, text=True, timeout=timeout, shell=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ConfigError('Restic operation was unavailable or interrupted; inspect vault state') from error
    need(result.returncode == 0, 'Restic operation failed; raw output is intentionally hidden')
    return result.stdout.strip()


def _repository_id(plan):
    try:
        value = json.loads(_restic(plan, ['cat', 'config'], timeout=60))
    except (json.JSONDecodeError, TypeError) as error:
        raise ConfigError('Restic repository configuration is invalid') from error
    identifier = value.get('id') if isinstance(value, dict) else None
    need(isinstance(identifier, str) and re.fullmatch('[0-9a-f]{64}', identifier),
         'Restic repository identifier is invalid')
    return identifier


def _state(plan):
    root = Path(plan['state_root'])
    verify_private(root, directory=True)
    pending_guard(root)
    state = read_private(root / 'state.json')
    keys(state, {'kind', 'owner', 'plan_id', 'status', 'repository_id', 'last_snapshot',
                 'last_verified', 'last_check_utc', 'last_checked_snapshot'},
         'Paperless vault state')
    need(state['kind'] == 'paperless-restic-vault-state-v1'
         and state['plan_id'] == plan['plan_id'] and state['status'] == 'ready',
         'Vault ownership or lifecycle state mismatch')
    need(isinstance(state['owner'], str) and re.fullmatch('[0-9a-f]{32}', state['owner']),
         'Vault owner is invalid')
    need(_repository_id(plan) == state['repository_id'], 'Restic repository identity changed')
    return state


def initialize(plan, confirmation):
    need(isinstance(plan, dict) and confirmation == plan.get('plan_id'),
         'Confirm the complete reviewed vault plan ID')
    validate_plan(plan)
    root, repository = Path(plan['state_root']), Path(plan['repository'])
    need(not root.exists() and not repository.exists(),
         'Initialization requires absent state and repository paths')
    create_private_directory(root)
    create_lock_file(root / 'operation.lock')
    state = {'kind': 'paperless-restic-vault-state-v1', 'owner': uuid.uuid4().hex,
             'plan_id': plan['plan_id'], 'status': 'initializing', 'repository_id': None,
             'last_snapshot': None, 'last_verified': None, 'last_check_utc': None,
             'last_checked_snapshot': None}
    atomic_json(root / 'state.json', state)
    try:
        _restic(plan, ['init'], timeout=120)
        state['repository_id'] = _repository_id(plan)
        state['status'] = 'ready'
        atomic_json(root / 'state.json', state, replace=True)
    except ConfigError as error:
        raise ConfigError('Vault initialization failed; partial state retained for review') from error
    return {'initialized': True, 'repository_id': state['repository_id'],
            'encrypted': True, 'off_host_verified': plan['off_host_verified']}


def make_snapshot_plan(vault_plan, source):
    validate_plan(vault_plan)
    _state(vault_plan)
    source = safe_path(Path(source))
    _separate([source, Path(vault_plan['state_root']), Path(vault_plan['repository']),
               Path(vault_plan['key_custody']['password_file']),
               Path(vault_plan['key_custody']['recovery_key_file'])])
    manifest = verify_backup(source)
    value = {'kind': 'homelab-paperless-vault-snapshot-plan',
             'contract': 'paperless-restic-snapshot-v1', 'vault_plan_id': vault_plan['plan_id'],
             'source': str(source), 'manifest_id': digest(manifest),
             'summary': backup_summary(manifest), 'host': HOST, 'tags': list(TAGS)}
    value['snapshot_plan_id'] = digest(value)
    return value


def validate_snapshot_plan(vault_plan, snapshot_plan):
    validate_snapshot_reference(vault_plan, snapshot_plan)
    rebuilt = make_snapshot_plan(vault_plan, snapshot_plan['source'])
    need(canonical(snapshot_plan) == canonical(rebuilt),
         'Snapshot plan/source backup drift; review a new plan')
    return snapshot_plan


def validate_snapshot_reference(vault_plan, snapshot_plan):
    keys(snapshot_plan, {'kind', 'contract', 'vault_plan_id', 'source', 'manifest_id',
                         'summary', 'host', 'tags', 'snapshot_plan_id'}, 'Vault snapshot plan')
    unsigned = {name: value for name, value in snapshot_plan.items()
                if name != 'snapshot_plan_id'}
    need(snapshot_plan['kind'] == 'homelab-paperless-vault-snapshot-plan'
         and snapshot_plan['contract'] == 'paperless-restic-snapshot-v1'
         and snapshot_plan['vault_plan_id'] == vault_plan['plan_id']
         and snapshot_plan['host'] == HOST and snapshot_plan['tags'] == list(TAGS)
         and snapshot_plan['snapshot_plan_id'] == digest(unsigned),
         'Snapshot plan identity or content is invalid')
    return snapshot_plan


def _json_lines(output):
    values = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith('{') or line.startswith('['):
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ConfigError('Restic JSON output was malformed') from error
    return values


def store(vault_plan, snapshot_plan, confirmation):
    need(isinstance(snapshot_plan, dict) and confirmation == snapshot_plan.get('snapshot_plan_id'),
         'Confirm the complete reviewed snapshot plan ID')
    validate_plan(vault_plan)
    validate_snapshot_plan(vault_plan, snapshot_plan)
    root = Path(vault_plan['state_root'])
    with operation_lock(root / 'operation.lock'):
        state = _state(vault_plan)
        arguments = ['backup', '--json', '--host', HOST]
        for tag in TAGS:
            arguments.extend(['--tag', tag])
        arguments.extend(['--tag', 'manifest-' + snapshot_plan['manifest_id'][:16], '.'])
        output = _restic(vault_plan, arguments, cwd=Path(snapshot_plan['source']))
        summaries = [value for value in _json_lines(output)
                     if isinstance(value, dict) and value.get('message_type') == 'summary']
        need(len(summaries) == 1, 'Restic backup did not return one final summary')
        snapshot_id = summaries[0].get('snapshot_id')
        need(isinstance(snapshot_id, str) and re.fullmatch('[0-9a-f]{64}', snapshot_id),
             'Restic snapshot identifier is invalid')
        state['last_snapshot'] = snapshot_id
        atomic_json(root / 'state.json', state, replace=True)
        return {'stored': True, 'encrypted': True, 'snapshot_id': snapshot_id,
                'manifest_id': snapshot_plan['manifest_id'], 'summary': snapshot_plan['summary']}


def check(vault_plan, confirmation):
    need(isinstance(vault_plan, dict) and confirmation == vault_plan.get('plan_id'),
         'Confirm the complete reviewed vault plan ID')
    validate_plan(vault_plan)
    root = Path(vault_plan['state_root'])
    with operation_lock(root / 'operation.lock'):
        state = _state(vault_plan)
        need(state['last_snapshot'] is not None,
             'Repository check requires at least one recorded snapshot')
        selected = _snapshots(vault_plan, state['last_snapshot'])
        need(len(selected) == 1 and selected[0].get('id') == state['last_snapshot'],
             'Latest recorded snapshot is unavailable')
        _restic(vault_plan, ['check', '--read-data'], timeout=1800)
        state['last_check_utc'] = datetime.now(timezone.utc).isoformat()
        state['last_checked_snapshot'] = state['last_snapshot']
        atomic_json(root / 'state.json', state, replace=True)
        return {'repository_check': 'passed', 'read_data': 'all',
                'checked_utc': state['last_check_utc'],
                'checked_snapshot': state['last_checked_snapshot']}


def _snapshots(vault_plan, *selection):
    try:
        value = json.loads(_restic(vault_plan, ['snapshots', '--json', *selection], timeout=120))
    except (json.JSONDecodeError, TypeError) as error:
        raise ConfigError('Restic snapshot inventory is invalid') from error
    need(isinstance(value, list), 'Restic snapshot inventory is invalid')
    return value


def _tag_snapshot(vault_plan, snapshot_id, *, add=None, remove=None):
    need((add is None) != (remove is None),
         'Exactly one snapshot tag operation is required')
    arguments = ['tag', '--json', '--add' if add is not None else '--remove',
                 add if add is not None else remove, snapshot_id]
    events = _json_lines(_restic(vault_plan, arguments, timeout=120))
    changed = [value for value in events
               if isinstance(value, dict) and value.get('message_type') == 'changed']
    summaries = [value for value in events
                 if isinstance(value, dict) and value.get('message_type') == 'summary']
    need(len(changed) == 1 and len(summaries) == 1
         and summaries[0].get('changed_snapshots') == 1
         and changed[0].get('old_snapshot_id') == snapshot_id,
         'Restic did not return one verified snapshot tag transition')
    replacement = changed[0].get('new_snapshot_id')
    need(isinstance(replacement, str) and re.fullmatch('[0-9a-f]{64}', replacement),
         'Restic replacement snapshot identifier is invalid')
    return replacement


def _locate_backup(target):
    candidates = []
    for manifest in Path(target).rglob('manifest.json'):
        parent = manifest.parent
        if ((parent / 'credentials.json').is_file()
                and (parent / 'paperless-postgres.dump').is_file()
                and (parent / 'document-export').is_dir()
                and (parent / 'filesystem').is_dir()):
            candidates.append(parent)
    need(len(candidates) == 1, 'Encrypted restore did not contain one Paperless recovery root')
    return candidates[0]


def restore(vault_plan, snapshot_plan, snapshot_id, target, confirmation):
    need(isinstance(snapshot_plan, dict) and confirmation == snapshot_plan.get('snapshot_plan_id'),
         'Confirm the complete reviewed snapshot plan ID')
    validate_plan(vault_plan)
    validate_snapshot_reference(vault_plan, snapshot_plan)
    need(isinstance(snapshot_id, str) and re.fullmatch('[0-9a-f]{64}', snapshot_id),
         'A complete restic snapshot ID is required')
    target = safe_path(Path(target))
    _separate([target, Path(vault_plan['state_root']), Path(vault_plan['repository']),
               Path(vault_plan['key_custody']['password_file']),
               Path(vault_plan['key_custody']['recovery_key_file'])])
    need(not target.exists() and target.parent.is_dir(),
         'Restore requires an absent destination under an existing parent')
    root = Path(vault_plan['state_root'])
    with operation_lock(root / 'operation.lock'):
        state = _state(vault_plan)
        selected = _snapshots(vault_plan, snapshot_id)
        need(len(selected) == 1 and selected[0].get('id') == snapshot_id,
             'Requested snapshot is unavailable')
        create_private_directory(target)
        _restic(vault_plan, ['restore', snapshot_id, '--target', str(target)], timeout=1800)
        restored_root = _locate_backup(target)
        manifest = verify_backup(restored_root)
        need(digest(manifest) == snapshot_plan['manifest_id']
             and backup_summary(manifest) == snapshot_plan['summary'],
             'Encrypted restore differs from reviewed application backup evidence')
        if VERIFIED_TAG in selected[0].get('tags', []):
            verified_snapshot = snapshot_id
        else:
            verified_snapshot = _tag_snapshot(
                vault_plan, snapshot_id, add=VERIFIED_TAG)
        previous = state['last_verified']
        if previous and previous not in (snapshot_id, verified_snapshot):
            previous_inventory = _snapshots(vault_plan, previous)
            if (previous_inventory
                    and VERIFIED_TAG in previous_inventory[0].get('tags', [])):
                _tag_snapshot(vault_plan, previous, remove=VERIFIED_TAG)
        if state['last_snapshot'] == snapshot_id:
            state['last_snapshot'] = verified_snapshot
        if state['last_checked_snapshot'] == snapshot_id:
            state['last_checked_snapshot'] = verified_snapshot
        state['last_verified'] = verified_snapshot
        atomic_json(root / 'state.json', state, replace=True)
        return {'restored': True, 'encrypted_source': True,
                'snapshot_id': verified_snapshot,
                'manifest_id': snapshot_plan['manifest_id'], 'summary': snapshot_plan['summary'],
                'restore_root': str(restored_root), 'recovery_verified': True}


def retention(vault_plan, *, apply=False, confirmation=None):
    if apply:
        need(isinstance(vault_plan, dict) and confirmation == vault_plan.get('plan_id'),
             'Confirm the complete reviewed vault plan ID')
    validate_plan(vault_plan)
    root = Path(vault_plan['state_root'])
    with operation_lock(root / 'operation.lock'):
        state = _state(vault_plan)
        need(state['last_verified'] is not None,
             'Retention is blocked until one encrypted restore is verified')
        need(state['last_snapshot'] is not None
             and state['last_checked_snapshot'] == state['last_snapshot'],
             'Retention is blocked until the latest snapshot passes a full data check')
        verified = _snapshots(vault_plan, state['last_verified'])
        need(len(verified) == 1 and verified[0].get('id') == state['last_verified']
             and VERIFIED_TAG in verified[0].get('tags', []),
             'Restore-verified snapshot or protection tag is missing')
        arguments = ['forget', '--host', HOST, '--tag', TAGS[0],
                     '--keep-daily', str(RETENTION['daily']),
                     '--keep-weekly', str(RETENTION['weekly']),
                     '--keep-monthly', str(RETENTION['monthly']),
                     '--keep-tag', VERIFIED_TAG]
        if apply:
            arguments.append('--prune')
        else:
            arguments.append('--dry-run')
        _restic(vault_plan, arguments, timeout=1800)
        return {'retention': RETENTION, 'mode': 'applied' if apply else 'preview',
                'verified_snapshot_protected': state['last_verified'],
                'prune_performed': apply}


def status(vault_plan):
    validate_plan(vault_plan)
    state = _state(vault_plan)
    snapshots = _snapshots(vault_plan, '--host', HOST, '--tag', TAGS[0])
    return {'status': state['status'], 'repository_id': state['repository_id'],
            'snapshots': len(snapshots), 'last_snapshot': state['last_snapshot'],
            'last_verified': state['last_verified'], 'last_check_utc': state['last_check_utc'],
            'last_checked_snapshot': state['last_checked_snapshot'],
            'retention': RETENTION, 'off_host_verified': vault_plan['off_host_verified']}


def make_recovery_manifest(vault_plan, snapshot_plan, snapshot_id):
    validate_plan(vault_plan)
    validate_snapshot_reference(vault_plan, snapshot_plan)
    need(isinstance(snapshot_id, str) and re.fullmatch('[0-9a-f]{64}', snapshot_id),
         'A complete restic snapshot ID is required')
    state = _state(vault_plan)
    need(state['last_verified'] == snapshot_id,
         'Portable recovery requires the selected restore-verified snapshot')
    need(state['last_snapshot'] == snapshot_id
         and state['last_checked_snapshot'] == snapshot_id
         and state['last_check_utc'] is not None,
         'Portable recovery requires a full data check of the selected latest snapshot')
    selected = _snapshots(vault_plan, snapshot_id)
    expected_tags = {*TAGS, VERIFIED_TAG,
                     'manifest-' + snapshot_plan['manifest_id'][:16]}
    need(len(selected) == 1 and selected[0].get('id') == snapshot_id
         and expected_tags.issubset(set(selected[0].get('tags', []))),
         'Portable recovery snapshot or protection tags are incomplete')
    value = {
        'kind': 'homelab-paperless-portable-recovery',
        'contract': RECOVERY_CONTRACT,
        'repository_id': state['repository_id'],
        'snapshot_id': snapshot_id,
        'manifest_id': snapshot_plan['manifest_id'],
        'summary_id': digest(snapshot_plan['summary']),
        'documents': snapshot_plan['summary']['documents'],
        'restic_version': vault_plan['tool']['version'],
        'required_tags': sorted(expected_tags),
        'full_data_check_utc': state['last_check_utc'],
    }
    value['recovery_manifest_id'] = digest(value)
    return value


def validate_recovery_manifest(value):
    keys(value, {'kind', 'contract', 'repository_id', 'snapshot_id', 'manifest_id',
                 'summary_id', 'documents', 'restic_version', 'required_tags',
                 'full_data_check_utc', 'recovery_manifest_id'},
         'Portable Paperless recovery manifest')
    unsigned = {name: item for name, item in value.items()
                if name != 'recovery_manifest_id'}
    need(value['kind'] == 'homelab-paperless-portable-recovery'
         and value['contract'] == RECOVERY_CONTRACT
         and value['restic_version'] == specification()['version']
         and all(isinstance(value[name], str) and re.fullmatch('[0-9a-f]{64}', value[name])
                 for name in ('repository_id', 'snapshot_id', 'manifest_id', 'summary_id'))
         and type(value['documents']) is int and value['documents'] > 0
         and value['required_tags'] == sorted({*TAGS, VERIFIED_TAG,
                                               'manifest-' + value['manifest_id'][:16]})
         and isinstance(value['full_data_check_utc'], str)
         and bool(value['full_data_check_utc'])
         and value['recovery_manifest_id'] == digest(unsigned),
         'Portable recovery manifest identity or content is invalid')
    return value


def _recovery_restic_plan(plan):
    return {
        'repository': plan['repository'],
        'tool': plan['tool'],
        'key_custody': {'password_file': plan['recovery_key_file']},
    }


def make_recovery_plan(repository, recovery_key_file, restic_binary, recovery_manifest):
    repository = safe_path(Path(repository))
    need(repository.is_dir(), 'Off-host repository directory is unavailable')
    recovery_key_file = validate_recovery_key(recovery_key_file)
    tool = validate_tool(restic_binary)
    validate_recovery_manifest(recovery_manifest)
    _separate([repository, Path(recovery_key_file), Path(tool['path'])])
    plan = {
        'kind': 'homelab-paperless-off-host-recovery-plan',
        'contract': RECOVERY_PLAN_CONTRACT,
        'platform': host_platform(),
        'architecture': host_architecture(),
        'repository': str(repository),
        'recovery_key_file': recovery_key_file,
        'tool': tool,
        'recovery_manifest': recovery_manifest,
        'full_data_check': True,
        'source_machine_state_required': False,
    }
    identity = _repository_id(_recovery_restic_plan(plan))
    need(identity == recovery_manifest['repository_id'],
         'Off-host repository identity differs from the recovery manifest')
    plan['plan_id'] = digest(plan)
    return plan


def validate_recovery_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'architecture', 'repository',
                'recovery_key_file', 'tool', 'recovery_manifest', 'full_data_check',
                'source_machine_state_required', 'plan_id'},
         'Off-host Paperless recovery plan')
    need(plan['kind'] == 'homelab-paperless-off-host-recovery-plan'
         and plan['contract'] == RECOVERY_PLAN_CONTRACT
         and plan['platform'] == host_platform()
         and plan['architecture'] == host_architecture()
         and plan['full_data_check'] is True
         and plan['source_machine_state_required'] is False,
         'Unsupported off-host Paperless recovery plan')
    rebuilt = make_recovery_plan(plan['repository'], plan['recovery_key_file'],
                                 plan['tool']['path'], plan['recovery_manifest'])
    need(canonical(plan) == canonical(rebuilt),
         'Off-host recovery plan/tool/key/repository drift; review a new plan')
    return plan


def recover_off_host(plan, target, confirmation):
    need(isinstance(plan, dict) and confirmation == plan.get('plan_id'),
         'Confirm the complete reviewed off-host recovery plan ID')
    validate_recovery_plan(plan)
    target = safe_path(Path(target))
    _separate([target, Path(plan['repository']), Path(plan['recovery_key_file']),
               Path(plan['tool']['path'])])
    need(not target.exists() and target.parent.is_dir(),
         'Off-host restore requires an absent destination under an existing parent')
    restic_plan = _recovery_restic_plan(plan)
    manifest = plan['recovery_manifest']
    _restic(restic_plan, ['check', '--read-data'], timeout=1800)
    selected = _snapshots(restic_plan, manifest['snapshot_id'])
    need(len(selected) == 1 and selected[0].get('id') == manifest['snapshot_id']
         and set(manifest['required_tags']).issubset(set(selected[0].get('tags', []))),
         'Required off-host snapshot or recovery tags are unavailable')
    create_private_directory(target)
    _restic(restic_plan, ['restore', manifest['snapshot_id'], '--target', str(target)],
            timeout=1800)
    restored_root = _locate_backup(target)
    restored_manifest = verify_backup(restored_root)
    summary = backup_summary(restored_manifest)
    need(digest(restored_manifest) == manifest['manifest_id']
         and digest(summary) == manifest['summary_id']
         and summary['documents'] == manifest['documents'],
         'Off-host restore differs from the portable recovery manifest')
    value = {
        'kind': 'homelab-paperless-off-host-recovery-proof',
        'contract': RECOVERY_PLAN_CONTRACT,
        'repository_id': manifest['repository_id'],
        'snapshot_id': manifest['snapshot_id'],
        'manifest_id': manifest['manifest_id'],
        'summary_id': manifest['summary_id'],
        'documents': manifest['documents'],
        'platform': host_platform(),
        'architecture': host_architecture(),
        'restic_version': plan['tool']['version'],
        'full_data_check': True,
        'encrypted_repository': True,
        'source_machine_state_used': False,
        'restored_utc': datetime.now(timezone.utc).isoformat(),
    }
    value['proof_id'] = digest(value)
    return {**value, 'restore_root': str(restored_root)}
