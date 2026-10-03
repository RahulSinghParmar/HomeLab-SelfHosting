"""Synthetic file-module executor. Deliberately no Docker, shell jobs or network."""

import hashlib
import hmac
from pathlib import Path
import re
import secrets
import uuid

from .config import canonical, keys, need
from .doctor import host_platform
from .privatefs import (atomic_json, create_lock_file, create_private_directory, operation_lock,
                        read_private, safe_path, sync_directory, verify_private)

CONTRACT = 'synthetic-files-v1'
CONTENT = 'Synthetic homelab content. No personal data.\n'
OPERATIONS = ['claim-storage', 'ensure-secret', 'write-synthetic-content', 'activate-and-verify']
STATES = {'applying', 'ready', 'retiring', 'retired'}


def digest(value: dict) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def make_plan(root: Path, data_root: Path, backup_root: Path) -> dict:
    paths = {key: str(safe_path(value)) for key, value in
             (('installation', root), ('data', data_root), ('backup', backup_root))}
    values = [Path(value) for value in paths.values()]
    for index, path in enumerate(values):
        need(path.parent.is_dir(), "Create the selected storage parent first")
        for other in values[index + 1:]:
            need(not path.is_relative_to(other) and not other.is_relative_to(path), "Sandbox storage roots overlap")
    result = {'kind': 'homelab-sandbox-plan', 'schema_version': 1, 'contract': CONTRACT,
              'platform': host_platform(), 'module': 'synthetic-files', 'paths': paths,
              'operations': list(OPERATIONS), 'secret_references': ['installation/secret.json'],
              'network': False, 'docker': False, 'deletion': 'owned-activation-record-only'}
    result['plan_id'] = digest(result)
    return result


def validate_plan(plan: dict) -> dict:
    keys(plan, {'kind', 'schema_version', 'contract', 'platform', 'module', 'paths', 'operations',
                'secret_references', 'network', 'docker', 'deletion', 'plan_id'}, 'sandbox plan')
    keys(plan['paths'], {'installation', 'data', 'backup'}, 'sandbox paths')
    expected = make_plan(*(Path(plan['paths'][role]) for role in ('installation', 'data', 'backup')))
    need(canonical(plan) == canonical(expected), "Sandbox plan changed, targets another host platform or uses an unsupported contract")
    return plan


def public_plan(plan: dict) -> dict:
    return {**plan, 'paths': {role: '<' + role + '-root>' for role in plan['paths']}}


def state_read(root: Path, plan: dict) -> dict:
    state = read_private(root / 'state.json')
    keys(state, {'kind', 'owner', 'plan_id', 'status', 'secret_digest', 'events'}, 'owned state')
    need(state['kind'] == CONTRACT and state['plan_id'] == plan['plan_id'], "Installation belongs to another plan; no adoption")
    need(isinstance(state['owner'], str) and bool(re.fullmatch('[0-9a-f]{32}', state['owner'])), "Invalid installation owner")
    need(state['status'] in STATES, "Invalid installation state")
    need(state['secret_digest'] is None or (isinstance(state['secret_digest'], str) and bool(re.fullmatch('[0-9a-f]{64}', state['secret_digest']))), "Invalid secret fingerprint")
    events = state['events']
    need(isinstance(events, list) and 1 <= len(events) <= 32, "Invalid journal length")
    for sequence, event in enumerate(events, 1):
        keys(event, {'sequence', 'event'}, 'journal event')
        need(type(event['sequence']) is int and event['sequence'] == sequence and event['event'] in
             {'initialized', 'storage-verified', 'secret-created', 'content-verified', 'ready', 'retiring', 'retired'}, "Invalid journal sequence/event")
    transitions = ['initialized', 'storage-verified', 'secret-created', 'content-verified', 'ready', 'retiring', 'retired']
    need([event['event'] for event in events] == transitions[:len(events)], "Invalid journal transition order")
    need(state['status'] == ({5: 'ready', 6: 'retiring', 7: 'retired'}.get(len(events), 'applying')), "State/journal mismatch")
    need((state['secret_digest'] is not None) == (len(events) >= 3), "Secret/journal mismatch")
    return state


def record(root: Path, state: dict, event: str) -> None:
    state['events'].append({'sequence': len(state['events']) + 1, 'event': event})
    atomic_json(root / 'state.json', state, replace=True)


def marker(state: dict, role: str) -> dict:
    return {'kind': CONTRACT, 'owner': state['owner'], 'plan_id': state['plan_id'], 'role': role}


def verify_marker(path: Path, state: dict, role: str) -> None:
    verify_private(path, directory=True)
    need(read_private(path / 'owner.json') == marker(state, role), "Storage ownership mismatch; no adoption")


def pending_guard(path: Path) -> None:
    need(not any(path.glob('.pending-*')), "Interrupted atomic publication found; retain files and request manual review")


def initialize(plan: dict) -> None:
    root = Path(plan['paths']['installation'])
    if root.exists():
        verify_private(root, directory=True)
        state_read(root, plan)  # Empty or foreign directories are NOT adopted.
        return
    # Preflight all selected roots before the first mutation.
    for value in plan['paths'].values():
        need(not Path(value).exists(), "A selected fresh-install root already exists; no changes made")
    create_private_directory(root)
    create_lock_file(root / 'operation.lock')
    state = {'kind': CONTRACT, 'owner': uuid.uuid4().hex, 'plan_id': plan['plan_id'],
             'status': 'applying', 'secret_digest': None, 'events': [{'sequence': 1, 'event': 'initialized'}]}
    atomic_json(root / 'state.json', state)


def ensure_storage(plan: dict, state: dict, *, create: bool) -> None:
    for role in ('data', 'backup'):
        path = Path(plan['paths'][role])
        if not path.exists():
            need(create and not any(e['event'] == 'storage-verified' for e in state['events']), "Owned storage is missing; automatic recreation refused")
            create_private_directory(path)
            atomic_json(path / 'owner.json', marker(state, role))
        verify_marker(path, state, role)
        pending_guard(path)


def secret_file(root: Path, state: dict, *, create: bool) -> dict:
    path = root / 'secret.json'
    if not path.exists():
        need(create and state['secret_digest'] is None, "Secret missing; refusing implicit rotation")
        value = {**marker(state, 'secret'), 'token': secrets.token_hex(32)}
        atomic_json(path, value)
    value = read_private(path)
    keys(value, {'kind', 'owner', 'plan_id', 'role', 'token'}, 'secret reference')
    need({key: value[key] for key in marker(state, 'secret')} == marker(state, 'secret'), "Secret belongs to another installation")
    need(isinstance(value['token'], str) and bool(re.fullmatch('[0-9a-f]{64}', value['token'])), "Invalid stored secret; do not replace it automatically")
    fingerprint = digest(value)
    need(state['secret_digest'] in (None, fingerprint), "Secret fingerprint mismatch; manual recovery required")
    if state['secret_digest'] is None:
        need(create, "Secret creation was interrupted; run apply with the same plan to reconcile")
        state['secret_digest'] = fingerprint
        record(root, state, 'secret-created')
    return value


def payload(state: dict) -> dict:
    return {**marker(state, 'content'), 'text': CONTENT}


def receipt(state: dict, secret: dict) -> dict:
    proof = hmac.new(bytes.fromhex(secret['token']), canonical(payload(state)).encode(), hashlib.sha256).hexdigest()
    return {**marker(state, 'activation'), 'content_sha256': digest(payload(state)), 'proof': proof}


def verify_content(plan: dict, state: dict, secret: dict, *, active: bool) -> None:
    need(read_private(Path(plan['paths']['data']) / 'synthetic.json') == payload(state), "Synthetic content changed or missing; no overwrite")
    if active:
        need(read_private(Path(plan['paths']['installation']) / 'active.json') == receipt(state, secret), "Activation verification failed; no repair/adoption")


def summary(state: dict) -> dict:
    return {'kind': 'homelab-sandbox-status', 'module': 'synthetic-files', 'status': state['status'],
            'plan_id': state['plan_id'], 'journal_events': len(state['events']),
            'secret_value': 'never-displayed', 'production_modules_deployed': False}


def apply(plan: dict, confirmation: str, *, checkpoint=lambda _: None) -> dict:
    validate_plan(plan)
    need(confirmation == plan['plan_id'], "Full reviewed plan ID confirmation is required")
    initialize(plan)
    root = Path(plan['paths']['installation'])
    with operation_lock(root / 'operation.lock'):
        pending_guard(root)
        state = state_read(root, plan)
        need(state['status'] not in ('retiring', 'retired'), "Retired installations are preserved; no implicit reactivation")
        ensure_storage(plan, state, create=state['status'] == 'applying')
        if not any(e['event'] == 'storage-verified' for e in state['events']):
            record(root, state, 'storage-verified')
        checkpoint('storage')
        secret = secret_file(root, state, create=state['status'] == 'applying')
        checkpoint('secret')
        content = Path(plan['paths']['data']) / 'synthetic.json'
        if not content.exists():
            need(state['status'] == 'applying' and not any(e['event'] == 'content-verified' for e in state['events']), "Recorded content is missing; automatic recreation refused")
            atomic_json(content, payload(state))
        need(read_private(content) == payload(state), "Existing content differs; refusing overwrite")
        if not any(e['event'] == 'content-verified' for e in state['events']):
            record(root, state, 'content-verified')
        checkpoint('content')
        activation = root / 'active.json'
        if not activation.exists():
            need(state['status'] == 'applying', "Activation missing; automatic recreation refused")
            atomic_json(activation, receipt(state, secret))
        verify_content(plan, state, secret, active=True)
        checkpoint('activation')
        if state['status'] != 'ready':
            state['status'] = 'ready'
            record(root, state, 'ready')
        return summary(state)


def status(plan: dict) -> dict:
    validate_plan(plan)
    root = Path(plan['paths']['installation'])
    verify_private(root, directory=True)
    with operation_lock(root / 'operation.lock'):
        pending_guard(root)
        state = state_read(root, plan)
        if state['status'] in ('ready', 'retired'):
            ensure_storage(plan, state, create=False)
            secret = secret_file(root, state, create=False)
            verify_content(plan, state, secret, active=state['status'] == 'ready')
            if state['status'] == 'retired':
                need(not (root / 'active.json').exists(), "Retired activation unexpectedly exists")
        return summary(state)


def retire(plan: dict, confirmation: str, *, checkpoint=lambda _: None) -> dict:
    validate_plan(plan)
    need(confirmation == plan['plan_id'], "Full reviewed plan ID confirmation is required")
    root = Path(plan['paths']['installation'])
    verify_private(root, directory=True)
    with operation_lock(root / 'operation.lock'):
        pending_guard(root)
        state = state_read(root, plan)
        need(state['status'] in ('ready', 'retiring', 'retired'), "Only a verified activation can be retired")
        ensure_storage(plan, state, create=False)
        secret = secret_file(root, state, create=False)
        verify_content(plan, state, secret, active=False)
        activation = root / 'active.json'
        if activation.exists():
            need(state['status'] != 'retired', "Unexpected activation after retirement")
            need(read_private(activation) == receipt(state, secret), "Unrecognized activation; refusing removal")
            if state['status'] != 'retiring':
                state['status'] = 'retiring'
                record(root, state, 'retiring')
            activation.unlink()  # Exact verified owned file only; never data or credentials.
            sync_directory(root)
        else:
            need(state['status'] != 'ready', "Activation already missing without retirement intent")
        checkpoint('retirement')
        if state['status'] != 'retired':
            state['status'] = 'retired'
            record(root, state, 'retired')
        return summary(state)
