"""Isolated Vaultwarden lifecycle, browser-encrypted fixture and consistent recovery."""
from __future__ import annotations

import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tarfile
import time
import uuid

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .doctor import host_platform
from .glance import docker, local_runtime, port_free
from .privatefs import (atomic_json, create_lock_file, create_private_directory,
                        operation_lock, read_private, safe_path, verify_private,
                        windows_acl)
from .sandbox import digest, pending_guard


MODULE = ROOT / 'modules/vaultwarden'
SERVICE = 'app'
MEMORY_MIB = 384
CPUS = 1.0
PIDS = 256
FIXTURE_EMAIL = 'phase5-vaultwarden@example.invalid'
FIXTURE_TITLE = 'HomeLab Vaultwarden Phase 5 recovery marker v1'
FIXTURE_BODY = 'Synthetic decrypted note survives backup and fresh restore.'
FIXTURE_ATTACHMENT = 'phase5-vaultwarden-attachment.txt'
FIXTURE_ATTACHMENT_BODY = b'HomeLab Vaultwarden Phase 5 attachment marker v1\n'
BACKUP_AREAS = ('attachments', 'sends')


def images():
    return load_json(MODULE / 'images.json')


def browser_specification():
    return load_json(MODULE / 'browser.json')


def runtime_user():
    if host_platform() == 'linux':
        need(hasattr(os, 'getuid') and hasattr(os, 'getgid'),
             'Linux Vaultwarden execution requires numeric host ownership')
        return {'uid': os.getuid(), 'gid': os.getgid(), 'source': 'host-owner'}
    return {'uid': 0, 'gid': 0, 'source': 'container-root'}


def make_plan(root, port, runtime, backup=None):
    root = safe_path(Path(root))
    need(root.parent.is_dir() and '$' not in str(root),
         'Choose an absent installation under an existing local parent without interpolation characters')
    need(type(port) is int and 1024 <= port <= 65535, 'Choose an unprivileged TCP port')
    keys(runtime, {'context', 'endpoint', 'engine_id'}, 'local runtime')
    recovery = None
    if backup is not None:
        source = safe_path(Path(backup))
        need(not source.is_relative_to(root) and not root.is_relative_to(source),
             'Backup and installation must not overlap')
        manifest = verify_backup(source)
        recovery = {'path': str(source), 'manifest_id': digest(manifest),
                    'method': 'sqlite-vacuum-filesystem-restore'}
    plan = {
        'kind': 'homelab-vaultwarden-plan',
        'contract': 'vaultwarden-isolated-recovery-v1',
        'platform': host_platform(), 'root': str(root), 'port': port,
        'runtime_user': runtime_user(),
        'runtime': runtime, 'images': images(), 'recovery': recovery,
        'limits': {'memory_mib': MEMORY_MIB, 'cpus': CPUS, 'pids': PIDS},
        'access': 'loopback', 'network': 'internal-dedicated-bridge',
        'docker_socket': False, 'admin': 'disabled', 'mail': 'disabled',
        'registration': 'synthetic-loopback-trial-only',
        'recovery_method': 'sqlite-vacuum-filesystem-restore',
        'authoritative_material': ['sqlite-vacuum-snapshot', 'rsa-keys',
                                   'attachments', 'sends', 'private-credentials'],
        'derived_material': ['container-image', 'web-vault-assets', 'icon-cache',
                             'temporary-files', 'sqlite-wal', 'sqlite-shm'],
    }
    plan['plan_id'] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'root', 'port', 'runtime_user',
                'runtime', 'images',
                'recovery', 'limits', 'access', 'network', 'docker_socket', 'admin',
                'mail', 'registration', 'recovery_method', 'authoritative_material',
                'derived_material', 'plan_id'}, 'Vaultwarden plan')
    backup = plan['recovery']['path'] if plan['recovery'] is not None else None
    need(canonical(plan) == canonical(make_plan(plan['root'], plan['port'],
                                                plan['runtime'], backup)),
         'Plan/image/recovery drift; review a new plan')
    return plan


def project(plan):
    return 'hl-vaultwarden-' + plan['plan_id'][:16]


def tags(plan, owner):
    return {'org.homelab.owner': owner, 'org.homelab.plan': plan['plan_id'],
            'org.homelab.module': 'vaultwarden'}


def new_credentials():
    return {'fixture_email': FIXTURE_EMAIL,
            'fixture_password': 'Vw1-' + secrets.token_urlsafe(24)}


def validate_credentials(value):
    keys(value, {'fixture_email', 'fixture_password'}, 'Vaultwarden credentials')
    need(value['fixture_email'] == FIXTURE_EMAIL,
         'Vaultwarden fixture must use the synthetic invalid-domain account')
    password = value['fixture_password']
    need(isinstance(password, str) and password.startswith('Vw1-')
         and 32 <= len(password) <= 64 and '\n' not in password and '\r' not in password,
         'Invalid private Vaultwarden fixture credential')
    return value


def compose(plan, owner):
    environment = {
        'DOMAIN': 'https://localhost:' + str(plan['port']),
        'SIGNUPS_ALLOWED': 'true', 'INVITATIONS_ALLOWED': 'false',
        'SHOW_PASSWORD_HINT': 'false', 'DISABLE_ADMIN_TOKEN': 'true',
        'PUSH_ENABLED': 'false', 'SENDS_ALLOWED': 'true',
        'ICON_SERVICE': 'internal', 'ICON_CACHE_TTL': '0',
        'ICON_CACHE_NEGTTL': '0', 'LOG_LEVEL': 'warn',
        'EXTENDED_LOGGING': 'false', 'TZ': 'UTC',
    }
    uid = plan['runtime_user']['uid']
    gid = plan['runtime_user']['gid']
    service = {
        'image': plan['images']['app'], 'labels': tags(plan, owner),
        'user': f'{uid}:{gid}',
        'pull_policy': 'never', 'restart': 'unless-stopped', 'read_only': True,
        'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
        'pids_limit': PIDS, 'mem_limit': f'{MEMORY_MIB}m',
        'mem_reservation': '32m', 'memswap_limit': '512m', 'cpus': CPUS,
        'environment': environment,
        'tmpfs': [f'/tmp:rw,noexec,nosuid,size=64m,uid={uid},gid={gid},mode=0700'],
        'volumes': [{'type': 'bind', 'source': str(Path(plan['root']) / 'data'),
                     'target': '/data', 'bind': {'create_host_path': False}}],
        'ports': [{'target': 80, 'published': str(plan['port']),
                   'host_ip': '127.0.0.1', 'protocol': 'tcp'}],
        'healthcheck': {'test': ['CMD', 'curl', '-fsS', '--max-time', '10',
                                 'http://127.0.0.1/alive'],
                        'interval': '10s', 'timeout': '10s', 'retries': 18,
                        'start_period': '20s'},
        'logging': {'driver': 'json-file',
                    'options': {'max-size': '10m', 'max-file': '3'}},
    }
    return {'services': {SERVICE: service},
            'networks': {'default': {'driver': 'bridge', 'internal': True,
                                     'labels': tags(plan, owner)}}}


def compose_args(plan):
    root = Path(plan['root'])
    return ['compose', '--project-name', project(plan), '--project-directory', str(root),
            '-f', str(root / 'compose.json')]


def inventory(plan, owner):
    context = plan['runtime']['context']
    found = {'containers': {}, 'networks': []}
    ids = docker(['ps', '-aq', '--filter',
                  'label=com.docker.compose.project=' + project(plan)], context=context).split()
    need(len(ids) <= 1, 'Unexpected Vaultwarden project containers')
    rows = json.loads(docker(['inspect'] + ids, context=context)) if ids else []
    for row in rows:
        labels = row['Config'].get('Labels') or {}
        need(owner is not None and all(labels.get(key) == value
                                       for key, value in tags(plan, owner).items()),
             'Foreign Vaultwarden resource; no adoption or mutation')
        role = labels.get('com.docker.compose.service')
        need(role == SERVICE and role not in found['containers'],
             'Unexpected or duplicate Vaultwarden service')
        need(row['Config']['Image'] == plan['images']['app'], 'Vaultwarden image drift')
        need(row['Config'].get('User') ==
             f'{plan["runtime_user"]["uid"]}:{plan["runtime_user"]["gid"]}',
             'Vaultwarden runtime-user drift')
        host = row['HostConfig']
        need(host['ReadonlyRootfs'] and not host['Privileged']
             and host.get('CapDrop') == ['ALL'] and not host.get('CapAdd')
             and not host.get('Devices') and not host.get('DeviceRequests'),
             'Vaultwarden privilege/device drift')
        need('no-new-privileges:true' in host['SecurityOpt']
             and host['PidsLimit'] == PIDS, 'Vaultwarden security/process drift')
        need(host['Memory'] == MEMORY_MIB * 1024**2
             and host['MemoryReservation'] == 32 * 1024**2
             and host['MemorySwap'] == 512 * 1024**2
             and host['NanoCpus'] == int(CPUS * 1_000_000_000),
             'Vaultwarden resource drift')
        need(host['RestartPolicy']['Name'] == 'unless-stopped'
             and host['LogConfig'] == {'Type': 'json-file',
                                       'Config': {'max-size': '10m', 'max-file': '3'}},
             'Vaultwarden lifecycle/logging drift')
        expected_ports = {'80/tcp': [{'HostIp': '127.0.0.1',
                                      'HostPort': str(plan['port'])}]}
        need((host.get('PortBindings') or {}) == expected_ports,
             'Vaultwarden port binding drift')
        expected_tmpfs = ('rw,noexec,nosuid,size=64m,uid='
                          + str(plan['runtime_user']['uid']) + ',gid='
                          + str(plan['runtime_user']['gid']) + ',mode=0700')
        need(host.get('Tmpfs') == {'/tmp': expected_tmpfs},
             'Vaultwarden temporary-filesystem drift')
        mounts = [item for item in row['Mounts'] if item['Type'] != 'tmpfs']
        need(len(mounts) == 1 and mounts[0]['Type'] == 'bind'
             and Path(mounts[0]['Source']).resolve() == (Path(plan['root']) / 'data').resolve()
             and mounts[0]['Destination'] == '/data' and mounts[0]['RW'],
             'Vaultwarden data mount drift')
        need(set(row['NetworkSettings']['Networks']) == {project(plan) + '_default'},
             'Vaultwarden network drift')
        required = {f'{key}={value}' for key, value in
                    compose(plan, owner)['services'][SERVICE]['environment'].items()}
        need(required <= set(row['Config']['Env']), 'Vaultwarden environment drift')
        found['containers'][role] = row
    ids = docker(['network', 'ls', '-q', '--filter',
                  'label=com.docker.compose.project=' + project(plan)], context=context).split()
    need(len(ids) <= 1, 'Unexpected Vaultwarden project networks')
    networks = json.loads(docker(['network', 'inspect'] + ids, context=context)) if ids else []
    for row in networks:
        labels = row.get('Labels') or {}
        need(owner is not None and all(labels.get(key) == value
                                       for key, value in tags(plan, owner).items()),
             'Foreign Vaultwarden network; no adoption or mutation')
        need(row['Name'] == project(plan) + '_default' and row['Driver'] == 'bridge'
             and row['Internal'], 'Vaultwarden network drift')
    found['networks'] = networks
    return found


def state_read(plan):
    root = Path(plan['root'])
    verify_private(root, directory=True)
    pending_guard(root)
    state = read_private(root / 'state.json')
    keys(state, {'kind', 'owner', 'plan_id', 'status', 'recovery'}, 'Vaultwarden state')
    need(state['kind'] == 'vaultwarden-owned-v1' and state['plan_id'] == plan['plan_id'],
         'Vaultwarden ownership mismatch')
    need(isinstance(state['owner'], str) and re.fullmatch('[0-9a-f]{32}', state['owner']),
         'Invalid Vaultwarden owner')
    need(state['status'] in ('prepared', 'running', 'stopped', 'removing', 'removed'),
         'Invalid Vaultwarden state')
    validate_credentials(read_private(root / 'credentials.json'))
    need(read_private(root / 'compose.json') == compose(plan, state['owner']),
         'Vaultwarden Compose modified; refusing execution')
    return state


def protect_file(path):
    if os.name == 'nt':
        windows_acl(path, create=True)
    else:
        path.chmod(0o600)
    verify_private(path)


def copy_tree(source, destination):
    need(source.is_dir() and destination.is_dir(), 'Vaultwarden recovery tree is missing')
    shutil.copytree(source, destination, dirs_exist_ok=True)
    tree_files(destination, protect_new=True)


def prepare(plan):
    root = Path(plan['root'])
    if root.exists():
        return state_read(plan)
    inventory(plan, None)
    port_free(plan['port'])
    context = plan['runtime']['context']
    inspected = json.loads(docker(['image', 'inspect', plan['images']['app']],
                                  context=context))[0]
    need(inspected['Os'] == 'linux' and inspected['Architecture'] == 'amd64',
         'Reviewed linux/amd64 Vaultwarden image must be cached')
    browser = json.loads(docker(['image', 'inspect', browser_specification()['image']],
                                context=context))[0]
    need(browser['Os'] == 'linux' and browser['Architecture'] == 'amd64',
         'Reviewed linux/amd64 browser runtime must be cached')
    create_private_directory(root)
    create_lock_file(root / 'operation.lock')
    create_private_directory(root / 'data')
    if plan['recovery']:
        backup = Path(plan['recovery']['path'])
        credentials = validate_credentials(read_private(backup / 'credentials.json'))
        copy_tree(backup / 'data', root / 'data')
    else:
        credentials = new_credentials()
    owner = uuid.uuid4().hex
    state = {'kind': 'vaultwarden-owned-v1', 'owner': owner,
             'plan_id': plan['plan_id'], 'status': 'prepared', 'recovery': None}
    atomic_json(root / 'credentials.json', credentials)
    atomic_json(root / 'compose.json', compose(plan, owner))
    atomic_json(root / 'state.json', state)
    return state


def wait_health(plan, deadline_seconds=240):
    deadline = time.monotonic() + deadline_seconds
    context = plan['runtime']['context']
    while time.monotonic() < deadline:
        container = docker(compose_args(plan) + ['ps', '-q', SERVICE], context=context)
        if container:
            row = json.loads(docker(['inspect', container], context=context))[0]
            state = row['State']
            need(state['Status'] not in ('dead', 'removing', 'exited'),
                 'Vaultwarden exited before becoming healthy')
            if (state.get('Health') or {}).get('Status') == 'healthy':
                return
        time.sleep(2)
    raise ConfigError('Vaultwarden did not become healthy before the bounded deadline')


def browser_source_id():
    names = ('Dockerfile', 'package.json', 'package-lock.json', 'validate.mjs')
    values = {name: hashlib.sha256((MODULE / 'browser' / name).read_bytes()).hexdigest()
              for name in names}
    values['runtime'] = browser_specification()
    return digest(values)


def browser_image_tag():
    return 'homelab-vaultwarden-browser:' + browser_source_id()[:16]


def build_browser_image(plan):
    specification = browser_specification()
    inspected = json.loads(docker(['image', 'inspect', specification['image']],
                                  context=plan['runtime']['context']))[0]
    need(inspected['Os'] == 'linux' and inspected['Architecture'] == 'amd64',
         'Reviewed linux/amd64 browser runtime must be cached')
    docker(['build', '--pull=false', '--label',
            'org.homelab.module=vaultwarden-browser', '--label',
            'org.homelab.browser-source=' + browser_source_id(), '--tag',
            browser_image_tag(), str(MODULE / 'browser')],
           context=plan['runtime']['context'], timeout=900)
    return browser_image_tag()


def copy_browser_evidence(plan, container, source, target):
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('COMPOSE_')}
    environment['COMPOSE_DISABLE_ENV_FILE'] = 'true'
    for key in ('DOCKER_HOST', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
        need(not environment.get(key), 'Docker endpoint/TLS overrides require explicit review')
    command = ['docker', '--context', plan['runtime']['context'], 'cp',
               container + ':' + source, '-']
    try:
        result = subprocess.run(command, env=environment, capture_output=True,
                                timeout=120, shell=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ConfigError('Vaultwarden evidence copy unavailable or interrupted') from error
    need(result.returncode == 0, 'Vaultwarden evidence copy failed; retain state for review')
    try:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode='r:*') as archive:
            members = [item for item in archive.getmembers() if item.isfile()]
            need(len(members) == 1 and members[0].size <= 64 * 1024 * 1024,
                 'Vaultwarden evidence archive is invalid or too large')
            source_file = archive.extractfile(members[0])
            need(source_file is not None, 'Vaultwarden evidence archive is unreadable')
            content = source_file.read()
    except (tarfile.TarError, OSError) as error:
        raise ConfigError('Vaultwarden evidence archive is invalid') from error
    target = Path(target)
    with target.open('xb') as destination:
        destination.write(content)
    protect_file(target)


def parse_browser_output(output):
    rows = []
    for line in output.splitlines():
        if not line.startswith('{'):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if value.get('kind') == 'vaultwarden-browser-vault-v1':
            rows.append(value)
    need(len(rows) == 1, 'Vaultwarden browser returned no single bounded evidence result')
    value = rows[0]
    keys(value, {'kind', 'item_id', 'title', 'body', 'title_sha256', 'body_sha256',
                 'attachment', 'browser', 'headless', 'rendered_title', 'decrypted_body',
                 'attachment_downloaded', 'reload_persistence', 'independent_sessions'},
         'Vaultwarden browser evidence')
    keys(value['attachment'], {'filename', 'bytes', 'sha256'},
         'Vaultwarden browser attachment evidence')
    need(value['title'] == FIXTURE_TITLE and value['body'] == FIXTURE_BODY
         and value['title_sha256'] == hashlib.sha256(FIXTURE_TITLE.encode()).hexdigest()
         and value['body_sha256'] == hashlib.sha256(FIXTURE_BODY.encode()).hexdigest()
         and value['attachment'] == {
             'filename': FIXTURE_ATTACHMENT, 'bytes': len(FIXTURE_ATTACHMENT_BODY),
             'sha256': hashlib.sha256(FIXTURE_ATTACHMENT_BODY).hexdigest()}
         and value['browser'] == 'chromium' and value['headless'] is True
         and all(value[name] is True for name in
                 ('rendered_title', 'decrypted_body', 'attachment_downloaded',
                  'reload_persistence', 'independent_sessions')),
         'Vaultwarden browser semantic evidence is invalid')
    need(re.fullmatch('[0-9a-f-]{36}', value['item_id']) is not None,
         'Vaultwarden browser item identifier is invalid')
    return value


def browser_validate(plan, action, expected, evidence_name):
    need(action in ('seed', 'verify'), 'Unsupported Vaultwarden browser action')
    credentials = validate_credentials(read_private(Path(plan['root']) / 'credentials.json'))
    evidence_root = Path(plan['root']) / 'browser-evidence'
    if not evidence_root.exists():
        create_private_directory(evidence_root)
    image = build_browser_image(plan)
    screenshot = action + '-' + evidence_name + '.png'
    arguments = [
        'create', '--init', '--read-only', '--network', project(plan) + '_default',
        '--memory', '768m', '--cpus', '1', '--pids-limit', '256',
        '--security-opt', 'no-new-privileges:true', '--cap-drop', 'ALL',
        '--shm-size', '512m',
        '--tmpfs', '/tmp:rw,nosuid,size=256m,uid=1001,gid=1001,mode=0700',
        '--tmpfs', '/home/pwuser:rw,nosuid,size=64m,uid=1001,gid=1001,mode=0700',
        '--mount', 'type=volume,destination=/evidence',
        '--label', 'org.homelab.module=vaultwarden-browser',
        '--label', 'org.homelab.plan=' + plan['plan_id'],
        '--env', 'VAULTWARDEN_BROWSER_ACTION=' + action,
        '--env', 'VAULTWARDEN_BROWSER_EMAIL=' + credentials['fixture_email'],
        '--env', 'VAULTWARDEN_BROWSER_PASSWORD=' + credentials['fixture_password'],
        '--env', 'VAULTWARDEN_BROWSER_LOCAL_PORT=' + str(plan['port']),
        '--env', 'VAULTWARDEN_BROWSER_UPSTREAM_HOST=app',
        '--env', 'VAULTWARDEN_BROWSER_SCREENSHOT=/evidence/' + screenshot,
    ]
    container = docker(arguments + [image], context=plan['runtime']['context'], timeout=120)
    need(re.fullmatch('[0-9a-f]{64}', container) is not None,
         'Vaultwarden browser validation container identity is invalid')
    try:
        docker(['start', container], context=plan['runtime']['context'], timeout=120)
        exit_code = docker(['wait', container], context=plan['runtime']['context'], timeout=900)
        output = docker(['logs', '--tail', '100', container],
                        context=plan['runtime']['context'], timeout=120)
        if exit_code != '0':
            raise ConfigError('Vaultwarden browser validation failed: ' + output[-1000:])
        value = parse_browser_output(output)
        target = evidence_root / screenshot
        copy_browser_evidence(plan, container, '/evidence/' + screenshot, target)
    finally:
        try:
            docker(['rm', '-f', '-v', container], context=plan['runtime']['context'], timeout=120)
        except ConfigError:
            pass
    evidence = {**value, 'screenshot_sha256': file_hash(target),
                'browser_source_id': browser_source_id(),
                'browser_image': browser_specification()['image']}
    if action == 'verify':
        need(all(evidence[name] == expected[name]
                 for name in ('item_id', 'title', 'body', 'title_sha256', 'body_sha256',
                              'attachment')),
             'Recovered Vaultwarden content differs from saved evidence')
    return evidence


def operate(plan, action, confirmation=None):
    validate_plan(plan)
    need(action in ('up', 'status', 'stop', 'remove'), 'Unsupported Vaultwarden action')
    if action != 'status':
        need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    if action == 'up':
        prepare(plan)
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        containers = resources['containers']
        context = plan['runtime']['context']
        if action == 'up':
            need(state['status'] not in ('removing', 'removed'),
                 'Removed Vaultwarden deployments require a fresh root')
            if not containers:
                need(state['status'] == 'prepared',
                     'Recorded Vaultwarden resources missing; no silent recreation')
                port_free(plan['port'])
                docker(compose_args(plan) + ['create', '--pull', 'never', '--no-build'],
                       context=context, timeout=300)
                resources = inventory(plan, state['owner'])
                containers = resources['containers']
            need(set(containers) == {SERVICE}, 'Incomplete Vaultwarden creation')
            need(not containers[SERVICE]['State'].get('Paused'),
                 'Paused Vaultwarden state requires manual review')
            if not containers[SERVICE]['State']['Running']:
                port_free(plan['port'])
                docker(compose_args(plan) + ['start', SERVICE], context=context, timeout=180)
            wait_health(plan)
            if plan['recovery']:
                source = verify_backup(Path(plan['recovery']['path']))
                restored = browser_validate(plan, 'verify', source['browser'], 'restored')
                docker(compose_args(plan) + ['restart', SERVICE], context=context, timeout=180)
                wait_health(plan)
                persisted = browser_validate(plan, 'verify', source['browser'],
                                             'restored-restart')
                need(restored['item_id'] == persisted['item_id'],
                     'Restored Vaultwarden item did not persist across restart')
                state['recovery'] = {'manifest_id': plan['recovery']['manifest_id'],
                                     'verified': True,
                                     'browser_fingerprint': digest(source['browser'])}
            state['status'] = 'running'
        elif action == 'stop':
            need(set(containers) == {SERVICE}
                 and state['status'] not in ('removing', 'removed'),
                 'No complete owned Vaultwarden deployment to stop')
            need(not containers[SERVICE]['State'].get('Paused'),
                 'Paused Vaultwarden state requires manual review')
            if containers[SERVICE]['State']['Running']:
                docker(compose_args(plan) + ['stop', '--timeout', '30', SERVICE],
                       context=context, timeout=120)
            state['status'] = 'stopped'
        elif action == 'remove':
            need(not any(row['State']['Running'] for row in containers.values()),
                 'Stop the owned Vaultwarden service before removal')
            if state['status'] != 'removed':
                state['status'] = 'removing'
                atomic_json(root / 'state.json', state, replace=True)
                docker(compose_args(plan) + ['down', '--remove-orphans'],
                       context=context, timeout=180)
                state['status'] = 'removed'
        if action != 'status' and read_private(root / 'state.json') != state:
            atomic_json(root / 'state.json', state, replace=True)
        resources = inventory(plan, state['owner'])
        container = resources['containers'].get(SERVICE)
        health = ((container or {}).get('State', {}).get('Health') or {}).get('Status')
        return {'module': 'vaultwarden', 'state': state['status'],
                'service': container['State']['Status'] if container else 'removed',
                'health': health or 'not-available',
                'url': 'http://127.0.0.1:' + str(plan['port']),
                'web_vault_secure_context': 'ephemeral-browser-proxy',
                'data_root_retained': (Path(plan['root']) / 'data').exists(),
                'recovery': state['recovery']}


def exercise(plan, confirmation):
    validate_plan(plan)
    need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        need(state['status'] == 'running' and set(resources['containers']) == {SERVICE}
             and resources['containers'][SERVICE]['State']['Running'],
             'Start the complete owned Vaultwarden project before exercise')
        need(not (root / 'browser-fixture.json').exists(),
             'Vaultwarden synthetic exercise is single-use for a fresh project')
        browser = browser_validate(plan, 'seed', {}, 'source')
        atomic_json(root / 'browser-fixture.json', browser)
        docker(compose_args(plan) + ['restart', SERVICE],
               context=plan['runtime']['context'], timeout=180)
        wait_health(plan)
        persisted = browser_validate(plan, 'verify', browser, 'source-restart')
        need(persisted['item_id'] == browser['item_id'],
             'Vaultwarden synthetic item did not persist across restart')
        return {'operation': 'register-create-encrypt-attach-restart-decrypt-download',
                'status': 'passed', 'item_id': browser['item_id'],
                'browser_rendered': True, 'decrypted_body': True,
                'attachment_downloaded': True, 'independent_sessions': True,
                'restart_persistence': True,
                'title_sha256': browser['title_sha256'],
                'body_sha256': browser['body_sha256'],
                'attachment_sha256': browser['attachment']['sha256']}


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def tree_files(root, *, protect_new=False):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob('*')):
        need(not path.is_symlink(), 'Vaultwarden backup trees must not contain links')
        if path.is_file():
            if protect_new:
                protect_file(path)
            result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def backup_summary(manifest):
    return {'vault_items': 1,
            'attachment_bytes': manifest['browser']['attachment']['bytes'],
            'attachment_sha256': manifest['browser']['attachment']['sha256'],
            'data_files': len(manifest['data_tree']),
            'recovery_status': manifest['recovery_status']}


def verify_backup(root):
    root = safe_path(Path(root))
    verify_private(root, directory=True)
    manifest = read_private(root / 'manifest.json')
    keys(manifest, {'kind', 'created_utc', 'images', 'method', 'authoritative_material',
                    'derived_material', 'consistency', 'recovery_status',
                    'credentials_hash', 'configuration_sha256', 'database_sha256',
                    'database_bytes', 'data_tree', 'browser_sha256', 'browser', 'summary'},
         'Vaultwarden backup manifest')
    need(manifest['kind'] == 'vaultwarden-consistent-backup-v1'
         and manifest['images'] == images()
         and manifest['method'] == 'sqlite-vacuum-filesystem-restore',
         'Vaultwarden backup image/format mismatch')
    need(manifest['authoritative_material'] == ['sqlite-vacuum-snapshot', 'rsa-keys',
                                                'attachments', 'sends',
                                                'private-credentials']
         and manifest['derived_material'] == ['container-image', 'web-vault-assets',
                                              'icon-cache', 'temporary-files',
                                              'sqlite-wal', 'sqlite-shm']
         and manifest['consistency'] == {'sqlite_vacuum_exit_verified': True,
                                         'application_quiesced_for_copy': True,
                                         'rsa_keys_copied': True,
                                         'attachment_tree_copied': True,
                                         'send_tree_copied': True}
         and manifest['recovery_status'] == 'pending-independent-restore',
         'Vaultwarden backup consistency/recovery evidence is incomplete')
    credentials = validate_credentials(read_private(root / 'credentials.json'))
    need(digest(credentials) == manifest['credentials_hash'],
         'Vaultwarden backup credential checksum mismatch')
    database = root / 'data' / 'db.sqlite3'
    need(database.is_file() and database.read_bytes()[:16] == b'SQLite format 3\x00'
         and database.stat().st_size == manifest['database_bytes']
         and database.stat().st_size > 4096
         and file_hash(database) == manifest['database_sha256'],
         'Vaultwarden SQLite snapshot checksum, header or size mismatch')
    need((root / 'data' / 'rsa_key.pem').is_file(),
         'Vaultwarden RSA private key is missing')
    need(not (root / 'data' / 'db.sqlite3-wal').exists()
         and not (root / 'data' / 'db.sqlite3-shm').exists(),
         'Vaultwarden backup must not include transient SQLite WAL/SHM files')
    need(manifest['configuration_sha256'] == {
        'private': file_hash(root / 'compose.private.json'),
        'sanitized': file_hash(root / 'sanitized-config.json')},
         'Vaultwarden backup configuration checksum mismatch')
    need(tree_files(root / 'data') == manifest['data_tree'],
         'Vaultwarden data tree checksum mismatch')
    browser = read_private(root / 'browser-fixture.json')
    need(file_hash(root / 'browser-fixture.json') == manifest['browser_sha256']
         and browser == manifest['browser'],
         'Vaultwarden browser evidence checksum mismatch')
    parse_browser_output(json.dumps({key: browser[key] for key in (
        'kind', 'item_id', 'title', 'body', 'title_sha256', 'body_sha256',
        'attachment', 'browser', 'headless', 'rendered_title', 'decrypted_body',
        'attachment_downloaded', 'reload_persistence', 'independent_sessions')}))
    need(backup_summary(manifest) == manifest['summary'],
         'Vaultwarden backup summary mismatch')
    return manifest


def backup(plan, destination, confirmation):
    validate_plan(plan)
    need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    destination = safe_path(Path(destination))
    need(not destination.is_relative_to(root) and not root.is_relative_to(destination),
         'Backup and installation must not overlap')
    need(not destination.exists() and destination.parent.is_dir(),
         'Backup requires an absent destination under an existing parent')
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        need(state['status'] == 'running' and set(resources['containers']) == {SERVICE}
             and resources['containers'][SERVICE]['State']['Running'],
             'Start the complete owned Vaultwarden project before backup')
        browser = read_private(root / 'browser-fixture.json')
        cycle = uuid.uuid4().hex[:12]
        browser_validate(plan, 'verify', browser, 'pre-backup-' + cycle)
        context = plan['runtime']['context']
        data = root / 'data'
        before = set(data.glob('db_*.sqlite3'))
        create_private_directory(destination)
        create_private_directory(destination / 'data')
        stopped = False
        failed_stage = 'sqlite-vacuum'
        try:
            docker(compose_args(plan) + ['exec', '-T', SERVICE,
                                         '/vaultwarden', 'backup'],
                   context=context, timeout=300)
            created = set(data.glob('db_*.sqlite3')) - before
            need(len(created) == 1, 'Vaultwarden backup command did not create one snapshot')
            snapshot = created.pop()
            need(snapshot.read_bytes()[:16] == b'SQLite format 3\x00',
                 'Vaultwarden backup command produced an invalid SQLite snapshot')
            failed_stage = 'quiesce'
            docker(compose_args(plan) + ['stop', '--timeout', '30', SERVICE],
                   context=context, timeout=120)
            stopped = True
            failed_stage = 'data-copy'
            shutil.copy2(snapshot, destination / 'data' / 'db.sqlite3')
            for name in ('rsa_key.pem', 'rsa_key.pub.pem', 'rsa_key.der', 'config.json'):
                source = data / name
                if source.is_file():
                    shutil.copy2(source, destination / 'data' / name)
            for name in BACKUP_AREAS:
                create_private_directory(destination / 'data' / name)
                if (data / name).is_dir():
                    shutil.copytree(data / name, destination / 'data' / name,
                                    dirs_exist_ok=True)
            tree_files(destination / 'data', protect_new=True)
            failed_stage = 'metadata-copy'
            shutil.copy2(root / 'credentials.json', destination / 'credentials.json')
            shutil.copy2(root / 'compose.json', destination / 'compose.private.json')
            shutil.copy2(root / 'browser-fixture.json',
                         destination / 'browser-fixture.json')
            atomic_json(destination / 'sanitized-config.json', {
                'kind': 'vaultwarden-sanitized-configuration-v1',
                'images': plan['images'], 'limits': plan['limits'],
                'access': plan['access'], 'network': plan['network'],
                'admin': plan['admin'], 'mail': plan['mail'],
                'registration': plan['registration'],
                'recovery_method': plan['recovery_method'],
            })
            for name in ('credentials.json', 'compose.private.json',
                         'browser-fixture.json'):
                protect_file(destination / name)
            data_tree = tree_files(destination / 'data')
            database = destination / 'data' / 'db.sqlite3'
            saved_browser = read_private(destination / 'browser-fixture.json')
            manifest = {
                'kind': 'vaultwarden-consistent-backup-v1',
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'images': plan['images'], 'method': 'sqlite-vacuum-filesystem-restore',
                'authoritative_material': ['sqlite-vacuum-snapshot', 'rsa-keys',
                                           'attachments', 'sends', 'private-credentials'],
                'derived_material': ['container-image', 'web-vault-assets', 'icon-cache',
                                     'temporary-files', 'sqlite-wal', 'sqlite-shm'],
                'consistency': {'sqlite_vacuum_exit_verified': True,
                                'application_quiesced_for_copy': True,
                                'rsa_keys_copied': True,
                                'attachment_tree_copied': True,
                                'send_tree_copied': True},
                'recovery_status': 'pending-independent-restore',
                'credentials_hash': digest(read_private(destination / 'credentials.json')),
                'configuration_sha256': {
                    'private': file_hash(destination / 'compose.private.json'),
                    'sanitized': file_hash(destination / 'sanitized-config.json')},
                'database_sha256': file_hash(database),
                'database_bytes': database.stat().st_size,
                'data_tree': data_tree,
                'browser_sha256': file_hash(destination / 'browser-fixture.json'),
                'browser': saved_browser, 'summary': None,
            }
            manifest['summary'] = backup_summary(manifest)
            atomic_json(destination / 'manifest.json', manifest)
            failed_stage = 'manifest-verification'
            verify_backup(destination)
        except (ConfigError, OSError) as error:
            raise ConfigError('Vaultwarden backup failed during ' + failed_stage
                              + '; sensitive partial state was retained for review') from error
        finally:
            if stopped:
                docker(compose_args(plan) + ['start', SERVICE], context=context, timeout=180)
                wait_health(plan)
            if 'snapshot' in locals() and snapshot.exists():
                snapshot.unlink()
        browser_validate(plan, 'verify', browser, 'post-backup-' + cycle)
        return {'backup_complete': True, 'application_consistent': True,
                'encrypted': False, 'contains_credentials': True,
                'summary': manifest['summary'], 'recovery_verified': False,
                'note': ('Sensitive local staging backup; restore into a fresh project '
                         'before encrypted off-host retention')}
