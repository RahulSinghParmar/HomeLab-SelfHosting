"""Isolated Karakeep lifecycle and application-aware recovery proof."""
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
import sqlite3
import subprocess
import tarfile
import time
import uuid
import zipfile

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .doctor import host_platform
from .glance import docker, local_runtime, port_free
from .privatefs import (atomic_json, create_lock_file, create_private_directory,
                        operation_lock, read_private, safe_path, verify_private,
                        windows_acl)
from .sandbox import digest, pending_guard


MODULE = ROOT / 'modules/karakeep'
SERVICES = ('app', 'chrome', 'search')
FIXTURE_EMAIL = 'phase5-karakeep@example.invalid'
FIXTURE_TITLE = 'HomeLab Karakeep Phase 5 recovery marker v1'
FIXTURE_BODY = ('Synthetic searchable bookmark survives database and '
                'search-index recovery.')
FIXTURE_ASSET = 'phase5-karakeep-asset.png'
FIXTURE_ASSET_BODY = __import__('base64').b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z7j8AAAAASUVORK5CYII=')
LIMITS = {
    'app': {'memory_mib': 1024, 'memory_reservation_mib': 96, 'cpus': 2.0, 'pids': 512},
    'chrome': {'memory_mib': 512, 'memory_reservation_mib': 32, 'cpus': 1.0, 'pids': 256},
    'search': {'memory_mib': 512, 'memory_reservation_mib': 32, 'cpus': 1.0, 'pids': 256},
}


def images():
    return load_json(MODULE / 'images.json')


def browser_specification():
    return load_json(MODULE / 'browser.json')


def runtime_user():
    if host_platform() == 'linux':
        need(hasattr(os, 'getuid') and hasattr(os, 'getgid'),
             'Linux Karakeep execution requires numeric host ownership')
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
                    'method': 'sqlite-quiesced-assets-reindex-restore'}
    plan = {
        'kind': 'homelab-karakeep-plan', 'contract': 'karakeep-isolated-recovery-v1',
        'platform': host_platform(), 'root': str(root), 'port': port,
        'runtime_user': runtime_user(), 'runtime': runtime, 'images': images(),
        'recovery': recovery, 'limits': LIMITS, 'access': 'loopback',
        'network': 'internal-dedicated-bridge', 'docker_socket': False,
        'registration': 'synthetic-loopback-trial-only', 'mail': 'disabled',
        'ai': 'disabled', 'telemetry': 'disabled',
        'recovery_method': 'sqlite-quiesced-assets-reindex-restore',
        'authoritative_material': ['sqlite-database', 'asset-tree',
                                   'private-credentials'],
        'supplementary_material': ['application-logical-export'],
        'derived_material': ['queue-database', 'meilisearch-index', 'container-images',
                             'temporary-files', 'sqlite-wal', 'sqlite-shm'],
    }
    plan['plan_id'] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'root', 'port', 'runtime_user',
                'runtime', 'images', 'recovery', 'limits', 'access', 'network',
                'docker_socket', 'registration', 'mail', 'ai', 'telemetry',
                'recovery_method', 'authoritative_material',
                'supplementary_material', 'derived_material', 'plan_id'},
         'Karakeep plan')
    backup = plan['recovery']['path'] if plan['recovery'] else None
    need(canonical(plan) == canonical(make_plan(plan['root'], plan['port'],
                                                plan['runtime'], backup)),
         'Plan/image/recovery drift; review a new plan')
    return plan


def project(plan):
    return 'hl-karakeep-' + plan['plan_id'][:16]


def tags(plan, owner):
    return {'org.homelab.owner': owner, 'org.homelab.plan': plan['plan_id'],
            'org.homelab.module': 'karakeep'}


def new_credentials():
    return {'fixture_email': FIXTURE_EMAIL,
            'fixture_password': 'Kk1-' + secrets.token_urlsafe(24),
            'nextauth_secret': secrets.token_urlsafe(48),
            'meili_master_key': secrets.token_urlsafe(36),
            'api_key': None, 'identifiers': None}


def validate_credentials(value, *, seeded=None):
    keys(value, {'fixture_email', 'fixture_password', 'nextauth_secret',
                 'meili_master_key', 'api_key', 'identifiers'},
         'Karakeep credentials')
    need(value['fixture_email'] == FIXTURE_EMAIL,
         'Karakeep fixture must use the synthetic invalid-domain account')
    need(isinstance(value['fixture_password'], str)
         and value['fixture_password'].startswith('Kk1-')
         and 32 <= len(value['fixture_password']) <= 64,
         'Invalid private Karakeep fixture password')
    need(isinstance(value['nextauth_secret'], str) and len(value['nextauth_secret']) >= 48
         and isinstance(value['meili_master_key'], str)
         and len(value['meili_master_key']) >= 36,
         'Invalid private Karakeep service secret')
    if seeded is True:
        need(isinstance(value['api_key'], str) and len(value['api_key']) >= 24,
             'Karakeep recovery API key is unavailable')
        keys(value['identifiers'], {'textId', 'assetId', 'assetBookmarkId'},
             'Karakeep fixture identifiers')
        need(all(isinstance(item, str) and re.fullmatch('[A-Za-z0-9_-]{8,64}', item)
                 for item in value['identifiers'].values()),
             'Invalid Karakeep fixture identifiers')
    elif seeded is False:
        need(value['api_key'] is None and value['identifiers'] is None,
             'Fresh Karakeep credentials must not contain fixture state')
    return value


def bounded(service, definition):
    limits = LIMITS[service]
    return {**definition, 'restart': 'unless-stopped', 'read_only': True,
            'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
            'pids_limit': limits['pids'], 'mem_limit': f"{limits['memory_mib']}m",
            'mem_reservation': f"{limits['memory_reservation_mib']}m",
            'memswap_limit': f"{limits['memory_mib']}m", 'cpus': limits['cpus'],
            'logging': {'driver': 'json-file',
                        'options': {'max-size': '10m', 'max-file': '3'}}}


def compose(plan, owner, credentials):
    validate_credentials(credentials)
    uid, gid = plan['runtime_user']['uid'], plan['runtime_user']['gid']
    app_environment = {
        'DATA_DIR': '/data', 'NEXTAUTH_URL': f"http://127.0.0.1:{plan['port']}",
        'NEXTAUTH_SECRET': credentials['nextauth_secret'], 'AUTH_TRUSTED_ORIGINS': '*',
        'MEILI_ADDR': 'http://search:7700',
        'MEILI_MASTER_KEY': credentials['meili_master_key'],
        'BROWSER_WEB_URL': 'http://chrome:9222', 'DISABLE_SIGNUPS': 'false',
        'DISABLE_PASSWORD_AUTH': 'false', 'EMAIL_VERIFICATION_REQUIRED': 'false',
        'INFERENCE_ENABLE_AUTO_TAGGING': 'false',
        'INFERENCE_ENABLE_AUTO_SUMMARIZATION': 'false',
        'EMBEDDING_ENABLE_AUTO_INDEXING': 'false', 'OCR_USE_LLM': 'false',
        'TZ': 'UTC',
    }
    app = bounded('app', {
        'image': plan['images']['app'], 'pull_policy': 'never',
        'labels': tags(plan, owner), 'user': f'{uid}:{gid}',
        'environment': app_environment,
        'tmpfs': [f'/tmp:rw,noexec,nosuid,size=128m,uid={uid},gid={gid},mode=0700',
                  f'/run:rw,exec,nosuid,size=32m,uid={uid},gid={gid},mode=0700'],
        'volumes': [{'type': 'bind', 'source': str(Path(plan['root']) / 'data'),
                     'target': '/data', 'bind': {'create_host_path': False}}],
        'networks': {'default': {'aliases': ['karakeep-web']}},
        'ports': [{'target': 3000, 'published': str(plan['port']),
                   'host_ip': '127.0.0.1', 'protocol': 'tcp'}],
        'depends_on': {'search': {'condition': 'service_healthy'},
                       'chrome': {'condition': 'service_started'}},
        'healthcheck': {'test': ['CMD', 'wget', '--spider', '-q',
                                 'http://127.0.0.1:3000/api/health'],
                        'interval': '10s', 'timeout': '10s', 'retries': 24,
                        'start_period': '30s'},
    })
    chrome = bounded('chrome', {
        'image': plan['images']['chrome'], 'pull_policy': 'never', 'init': True,
        'labels': tags(plan, owner), 'user': '65534:65534',
        'command': ['--disable-gpu', '--disable-dev-shm-usage', '--hide-scrollbars',
                    '--disable-blink-features=AutomationControlled',
                    '--window-size=1440,900'],
        'tmpfs': ['/tmp:rw,noexec,nosuid,size=128m,uid=65534,gid=65534,mode=0700'],
    })
    search = bounded('search', {
        'image': plan['images']['search'], 'pull_policy': 'never',
        'labels': tags(plan, owner), 'user': f'{uid}:{gid}',
        'environment': {'MEILI_MASTER_KEY': credentials['meili_master_key'],
                        'MEILI_NO_ANALYTICS': 'true', 'MEILI_ENV': 'production'},
        'tmpfs': [f'/tmp:rw,noexec,nosuid,size=64m,uid={uid},gid={gid},mode=0700'],
        'volumes': [{'type': 'bind', 'source': str(Path(plan['root']) / 'search'),
                     'target': '/meili_data', 'bind': {'create_host_path': False}}],
        'healthcheck': {'test': ['CMD', 'wget', '--spider', '-q',
                                 'http://127.0.0.1:7700/health'],
                        'interval': '10s', 'timeout': '5s', 'retries': 18,
                        'start_period': '10s'},
    })
    return {'services': {'app': app, 'chrome': chrome, 'search': search},
            'networks': {'default': {'driver': 'bridge', 'internal': True,
                                     'labels': tags(plan, owner)}}}


def compose_args(plan):
    root = Path(plan['root'])
    return ['compose', '--project-name', project(plan), '--project-directory', str(root),
            '-f', str(root / 'compose.json')]


def inventory(plan, owner):
    context = plan['runtime']['context']
    ids = docker(['ps', '-aq', '--filter',
                  'label=com.docker.compose.project=' + project(plan)], context=context).split()
    need(len(ids) <= 3, 'Unexpected Karakeep project containers')
    rows = json.loads(docker(['inspect'] + ids, context=context)) if ids else []
    found = {}
    expected = compose(plan, owner, validate_credentials(
        read_private(Path(plan['root']) / 'credentials.json'))) if owner else None
    for row in rows:
        labels = row['Config'].get('Labels') or {}
        need(owner is not None and all(labels.get(key) == value
                                       for key, value in tags(plan, owner).items()),
             'Foreign Karakeep resource; no adoption or mutation')
        role = labels.get('com.docker.compose.service')
        need(role in SERVICES and role not in found, 'Unexpected or duplicate Karakeep service')
        service = expected['services'][role]
        need(row['Config']['Image'] == plan['images'][role], 'Karakeep image drift')
        host = row['HostConfig']
        need(host['ReadonlyRootfs'] and not host['Privileged']
             and host.get('CapDrop') == ['ALL'] and not host.get('CapAdd')
             and not host.get('Devices') and not host.get('DeviceRequests')
             and 'no-new-privileges:true' in host['SecurityOpt'],
             'Karakeep privilege/device drift')
        limit = LIMITS[role]
        need(host['Memory'] == limit['memory_mib'] * 1024**2
             and host['MemoryReservation'] == limit['memory_reservation_mib'] * 1024**2
             and host['MemorySwap'] == limit['memory_mib'] * 1024**2
             and host['NanoCpus'] == int(limit['cpus'] * 1_000_000_000)
             and host['PidsLimit'] == limit['pids'], 'Karakeep resource drift')
        expected_ports = ({'3000/tcp': [{'HostIp': '127.0.0.1',
                                         'HostPort': str(plan['port'])}]}
                          if role == 'app' else {})
        need((host.get('PortBindings') or {}) == expected_ports, 'Karakeep port drift')
        need(set(row['NetworkSettings']['Networks']) == {project(plan) + '_default'},
             'Karakeep network drift')
        required = {f'{key}={value}' for key, value in service.get('environment', {}).items()}
        need(required <= set(row['Config']['Env']), 'Karakeep environment drift')
        found[role] = row
    network_ids = docker(['network', 'ls', '-q', '--filter',
                          'label=com.docker.compose.project=' + project(plan)],
                         context=context).split()
    need(len(network_ids) <= 1, 'Unexpected Karakeep project networks')
    networks = json.loads(docker(['network', 'inspect'] + network_ids,
                                 context=context)) if network_ids else []
    for row in networks:
        labels = row.get('Labels') or {}
        need(owner is not None and all(labels.get(key) == value
                                       for key, value in tags(plan, owner).items())
             and row['Name'] == project(plan) + '_default'
             and row['Driver'] == 'bridge' and row['Internal'],
             'Karakeep network ownership or isolation drift')
    return {'containers': found, 'networks': networks}


def protect_file(path):
    if os.name == 'nt':
        windows_acl(path, create=True)
    else:
        Path(path).chmod(0o600)
    verify_private(path)


def tree_files(root, *, protect_new=False):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob('*')):
        need(not path.is_symlink(), 'Karakeep backup trees must not contain links')
        if path.is_file():
            if protect_new:
                protect_file(path)
            result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def copy_tree(source, destination):
    need(source.is_dir() and destination.is_dir(), 'Karakeep recovery tree is missing')
    shutil.copytree(source, destination, dirs_exist_ok=True)
    tree_files(destination, protect_new=True)


def state_read(plan):
    root = Path(plan['root'])
    verify_private(root, directory=True)
    pending_guard(root)
    state = read_private(root / 'state.json')
    keys(state, {'kind', 'owner', 'plan_id', 'status', 'recovery'}, 'Karakeep state')
    need(state['kind'] == 'karakeep-owned-v1' and state['plan_id'] == plan['plan_id']
         and isinstance(state['owner'], str) and re.fullmatch('[0-9a-f]{32}', state['owner']),
         'Karakeep ownership mismatch')
    need(state['status'] in ('prepared', 'running', 'stopped', 'removing', 'removed'),
         'Invalid Karakeep state')
    credentials = validate_credentials(read_private(root / 'credentials.json'))
    need(read_private(root / 'compose.json') == compose(plan, state['owner'], credentials),
         'Karakeep Compose modified; refusing execution')
    return state


def prepare(plan):
    root = Path(plan['root'])
    if root.exists():
        return state_read(plan)
    inventory(plan, None)
    port_free(plan['port'])
    context = plan['runtime']['context']
    for image in [*plan['images'].values(), browser_specification()['image']]:
        inspected = json.loads(docker(['image', 'inspect', image], context=context))[0]
        need(inspected['Os'] == 'linux' and inspected['Architecture'] == 'amd64',
             'Reviewed linux/amd64 Karakeep image must be cached')
    create_private_directory(root)
    create_lock_file(root / 'operation.lock')
    for name in ('data', 'search'):
        create_private_directory(root / name)
    if plan['recovery']:
        backup_root = Path(plan['recovery']['path'])
        credentials = validate_credentials(read_private(backup_root / 'credentials.json'),
                                           seeded=True)
        copy_tree(backup_root / 'data', root / 'data')
    else:
        credentials = validate_credentials(new_credentials(), seeded=False)
    owner = uuid.uuid4().hex
    state = {'kind': 'karakeep-owned-v1', 'owner': owner,
             'plan_id': plan['plan_id'], 'status': 'prepared', 'recovery': None}
    atomic_json(root / 'credentials.json', credentials)
    atomic_json(root / 'compose.json', compose(plan, owner, credentials))
    atomic_json(root / 'state.json', state)
    return state


def wait_health(plan, deadline_seconds=300):
    deadline = time.monotonic() + deadline_seconds
    context = plan['runtime']['context']
    while time.monotonic() < deadline:
        container = docker(compose_args(plan) + ['ps', '-q', 'app'], context=context)
        if container:
            row = json.loads(docker(['inspect', container], context=context))[0]
            state = row['State']
            need(state['Status'] not in ('dead', 'removing', 'exited'),
                 'Karakeep exited before becoming healthy')
            if (state.get('Health') or {}).get('Status') == 'healthy':
                return
        time.sleep(2)
    raise ConfigError('Karakeep did not become healthy before the bounded deadline')


def browser_source_id():
    names = ('Dockerfile', 'validate.mjs')
    values = {name: hashlib.sha256((MODULE / 'browser' / name).read_bytes()).hexdigest()
              for name in names}
    for name in ('package.json', 'package-lock.json'):
        values[name] = hashlib.sha256(
            (ROOT / 'modules/vaultwarden/browser' / name).read_bytes()).hexdigest()
    values['runtime'] = browser_specification()
    return digest(values)


def browser_image_tag():
    return 'homelab-karakeep-browser:' + browser_source_id()[:16]


def build_browser_image(plan):
    docker(['build', '--pull=false', '--label', 'org.homelab.module=karakeep-browser',
            '--label', 'org.homelab.browser-source=' + browser_source_id(),
            '--file', str(MODULE / 'browser' / 'Dockerfile'), '--tag',
            browser_image_tag(), str(ROOT / 'modules')],
           context=plan['runtime']['context'], timeout=900)
    return browser_image_tag()


def copy_container_file(plan, container, source, target, max_bytes=64 * 1024 * 1024):
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('COMPOSE_')}
    environment['COMPOSE_DISABLE_ENV_FILE'] = 'true'
    command = ['docker', '--context', plan['runtime']['context'], 'cp',
               container + ':' + source, '-']
    result = subprocess.run(command, env=environment, capture_output=True,
                            timeout=120, shell=False)
    need(result.returncode == 0, 'Karakeep evidence copy failed; retain state for review')
    try:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode='r:*') as archive:
            members = [item for item in archive.getmembers() if item.isfile()]
            need(len(members) == 1 and members[0].size <= max_bytes,
                 'Karakeep evidence archive is invalid or too large')
            source_file = archive.extractfile(members[0])
            need(source_file is not None, 'Karakeep evidence archive is unreadable')
            content = source_file.read()
    except (tarfile.TarError, OSError) as error:
        raise ConfigError('Karakeep evidence archive is invalid') from error
    target = Path(target)
    with target.open('xb') as destination:
        destination.write(content)
    protect_file(target)


def parse_browser_output(output):
    rows = []
    for line in output.splitlines():
        if line.startswith('{'):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if value.get('kind') == 'karakeep-browser-bookmarks-v1':
                rows.append(value)
    need(len(rows) == 1, 'Karakeep browser returned no single bounded evidence result')
    value = rows[0]
    keys(value, {'kind', 'text_id', 'asset_id', 'asset_bookmark_id', 'title', 'body',
                 'title_sha256', 'body_sha256', 'asset', 'rendered_title',
                 'full_text_search', 'asset_downloaded', 'search_reindexed',
                 'browser', 'headless', 'application_export'}, 'Karakeep browser evidence')
    keys(value['asset'], {'filename', 'bytes', 'sha256'}, 'Karakeep asset evidence')
    need(value['title'] == FIXTURE_TITLE and value['body'] == FIXTURE_BODY
         and value['title_sha256'] == hashlib.sha256(FIXTURE_TITLE.encode()).hexdigest()
         and value['body_sha256'] == hashlib.sha256(FIXTURE_BODY.encode()).hexdigest()
         and value['asset'] == {'filename': FIXTURE_ASSET,
                                'bytes': len(FIXTURE_ASSET_BODY),
                                'sha256': hashlib.sha256(FIXTURE_ASSET_BODY).hexdigest()}
         and value['browser'] == 'chromium' and value['headless'] is True
         and all(value[name] is True for name in
                 ('rendered_title', 'full_text_search', 'asset_downloaded')),
         'Karakeep browser semantic evidence is invalid')
    return value


def browser_validate(plan, action, expected, evidence_name):
    need(action in ('seed', 'verify', 'restore'), 'Unsupported Karakeep browser action')
    root = Path(plan['root'])
    evidence_root = root / 'browser-evidence'
    if not evidence_root.exists():
        create_private_directory(evidence_root)
    image = build_browser_image(plan)
    screenshot = action + '-' + evidence_name + '.png'
    args = ['create', '--init', '--read-only', '--network', project(plan) + '_default',
            '--memory', '768m', '--cpus', '1', '--pids-limit', '256',
            '--security-opt', 'no-new-privileges:true', '--cap-drop', 'ALL',
            '--shm-size', '512m',
            '--tmpfs', '/tmp:rw,nosuid,size=256m,uid=1001,gid=1001,mode=0700',
            '--tmpfs', '/home/pwuser:rw,nosuid,size=64m,uid=1001,gid=1001,mode=0700',
            '--mount', 'type=volume,destination=/evidence',
            '--mount', 'type=bind,source=' + str(root)
            + ',destination=/credentials,readonly,bind-propagation=rprivate',
            '--label', 'org.homelab.module=karakeep-browser',
            '--label', 'org.homelab.plan=' + plan['plan_id'],
            '--env', 'KARAKEEP_BROWSER_ACTION=' + action,
            '--env', 'KARAKEEP_BROWSER_BASE_URL=http://karakeep-web:3000',
            '--env', 'KARAKEEP_BROWSER_SCREENSHOT=/evidence/' + screenshot, image]
    container = docker(args, context=plan['runtime']['context'], timeout=120)
    try:
        docker(['start', container], context=plan['runtime']['context'], timeout=120)
        exit_code = docker(['wait', container], context=plan['runtime']['context'], timeout=900)
        output = docker(['logs', '--tail', '100', container],
                        context=plan['runtime']['context'], timeout=120)
        if exit_code != '0':
            raise ConfigError('Karakeep browser validation failed: ' + output[-1000:])
        value = parse_browser_output(output)
        screenshot_target = evidence_root / screenshot
        copy_container_file(plan, container, '/evidence/' + screenshot,
                            screenshot_target)
        if action == 'seed':
            private_output = evidence_root / ('private-' + uuid.uuid4().hex + '.json')
            copy_container_file(plan, container, '/evidence/private-credentials.json',
                                private_output, 64 * 1024)
            seeded = validate_credentials(read_private(private_output), seeded=True)
            atomic_json(root / 'credentials.json', seeded, replace=True)
            private_output.unlink()
            export = root / 'application-export.zip'
            copy_container_file(plan, container, '/evidence/application-export.zip', export)
    finally:
        try:
            docker(['rm', '-f', '-v', container], context=plan['runtime']['context'], timeout=120)
        except ConfigError:
            pass
    evidence = {**value, 'screenshot_sha256': file_hash(screenshot_target),
                'browser_source_id': browser_source_id(),
                'browser_image': browser_specification()['image']}
    if action != 'seed':
        need(all(evidence[name] == expected[name] for name in
                 ('text_id', 'asset_id', 'asset_bookmark_id', 'title', 'body',
                  'title_sha256', 'body_sha256', 'asset')),
             'Recovered Karakeep content differs from saved evidence')
    return evidence


def operate(plan, action, confirmation=None):
    validate_plan(plan)
    need(action in ('up', 'status', 'stop', 'remove'), 'Unsupported Karakeep action')
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
                 'Removed Karakeep deployments require a fresh root')
            if not containers:
                need(state['status'] == 'prepared',
                     'Recorded Karakeep resources missing; no silent recreation')
                port_free(plan['port'])
                docker(compose_args(plan) + ['create', '--pull', 'never', '--no-build'],
                       context=context, timeout=300)
                containers = inventory(plan, state['owner'])['containers']
            need(set(containers) == set(SERVICES), 'Incomplete Karakeep creation')
            need(not any(row['State'].get('Paused') for row in containers.values()),
                 'Paused Karakeep state requires manual review')
            if not all(row['State']['Running'] for row in containers.values()):
                port_free(plan['port'])
                docker(compose_args(plan) + ['start'], context=context, timeout=240)
            wait_health(plan)
            if plan['recovery']:
                source = verify_backup(Path(plan['recovery']['path']))
                restored = browser_validate(plan, 'restore', source['browser'], 'restored')
                docker(compose_args(plan) + ['restart'], context=context, timeout=240)
                wait_health(plan)
                persisted = browser_validate(plan, 'verify', source['browser'],
                                             'restored-restart')
                need(restored['text_id'] == persisted['text_id'],
                     'Restored Karakeep bookmark did not persist across restart')
                state['recovery'] = {'manifest_id': plan['recovery']['manifest_id'],
                                     'verified': True, 'search_rebuilt': True,
                                     'browser_fingerprint': digest(source['browser'])}
            state['status'] = 'running'
        elif action == 'stop':
            need(set(containers) == set(SERVICES)
                 and state['status'] not in ('removing', 'removed'),
                 'No complete owned Karakeep deployment to stop')
            if any(row['State']['Running'] for row in containers.values()):
                docker(compose_args(plan) + ['stop', '--timeout', '45'],
                       context=context, timeout=180)
            state['status'] = 'stopped'
        elif action == 'remove':
            need(not any(row['State']['Running'] for row in containers.values()),
                 'Stop the owned Karakeep services before removal')
            if state['status'] != 'removed':
                state['status'] = 'removing'
                atomic_json(root / 'state.json', state, replace=True)
                docker(compose_args(plan) + ['down', '--remove-orphans'],
                       context=context, timeout=180)
                state['status'] = 'removed'
        if action != 'status' and read_private(root / 'state.json') != state:
            atomic_json(root / 'state.json', state, replace=True)
        resources = inventory(plan, state['owner'])
        return {'module': 'karakeep', 'state': state['status'],
                'services': {name: row['State']['Status']
                             for name, row in resources['containers'].items()},
                'health': (((resources['containers'].get('app') or {}).get('State', {})
                            .get('Health') or {}).get('Status') or 'not-available'),
                'url': 'http://127.0.0.1:' + str(plan['port']),
                'data_root_retained': (root / 'data').exists(),
                'search_is_derived': True, 'recovery': state['recovery']}


def exercise(plan, confirmation):
    validate_plan(plan)
    need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        need(state['status'] == 'running' and set(resources['containers']) == set(SERVICES)
             and all(row['State']['Running'] for row in resources['containers'].values()),
             'Start the complete owned Karakeep project before exercise')
        if (root / 'browser-fixture.json').exists():
            browser = read_private(root / 'browser-fixture.json')
            parse_browser_output(json.dumps({key: browser[key] for key in (
                'kind', 'text_id', 'asset_id', 'asset_bookmark_id', 'title', 'body',
                'title_sha256', 'body_sha256', 'asset', 'rendered_title',
                'full_text_search', 'asset_downloaded', 'search_reindexed', 'browser',
                'headless', 'application_export')}))
            validate_credentials(read_private(root / 'credentials.json'), seeded=True)
            verify_logical_export(root / 'application-export.zip')
            resumed = True
        else:
            browser = browser_validate(plan, 'seed', {}, 'source')
            atomic_json(root / 'browser-fixture.json', browser)
            atomic_json(root / 'compose.json',
                        compose(plan, state['owner'], read_private(root / 'credentials.json')),
                        replace=True)
            resumed = False
        docker(compose_args(plan) + ['restart'], context=plan['runtime']['context'],
               timeout=240)
        wait_health(plan)
        persisted = browser_validate(plan, 'verify', browser, 'source-restart')
        need(persisted['text_id'] == browser['text_id'],
             'Karakeep fixture did not persist across restart')
        verify_logical_export(root / 'application-export.zip')
        return {'operation': 'register-key-bookmarks-search-export-restart',
                'status': 'passed', 'resumed_after_interruption': resumed,
                'text_id': browser['text_id'],
                'asset_id': browser['asset_id'], 'browser_rendered': True,
                'full_text_search': True, 'asset_downloaded': True,
                'application_export_verified': True, 'restart_persistence': True,
                'title_sha256': browser['title_sha256'],
                'body_sha256': browser['body_sha256'],
                'asset_sha256': browser['asset']['sha256']}


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def sqlite_check(path):
    path = Path(path)
    need(path.is_file() and path.read_bytes()[:16] == b'SQLite format 3\x00'
         and path.stat().st_size > 4096, 'Karakeep SQLite database is invalid')
    try:
        connection = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)
        try:
            result = connection.execute('PRAGMA quick_check').fetchall()
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise ConfigError('Karakeep SQLite integrity check failed') from error
    need(result == [('ok',)], 'Karakeep SQLite quick_check did not pass')
    return True


def verify_logical_export(path):
    path = Path(path)
    need(path.is_file() and 100 < path.stat().st_size <= 128 * 1024 * 1024,
         'Karakeep application export is missing or invalid')
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            need(names and all(not name.startswith('/') and '..' not in Path(name).parts
                               for name in names),
                 'Karakeep application export contains unsafe paths')
            json_names = [name for name in names if name.endswith('.json')]
            need(json_names, 'Karakeep application export has no logical JSON data')
            decoded = []
            for name in json_names:
                need(archive.getinfo(name).file_size <= 32 * 1024 * 1024,
                     'Karakeep application export JSON is too large')
                decoded.append(json.loads(archive.read(name)))
    except (zipfile.BadZipFile, OSError, json.JSONDecodeError) as error:
        raise ConfigError('Karakeep application export is unreadable') from error
    text = json.dumps(decoded, sort_keys=True)
    need(FIXTURE_TITLE in text and FIXTURE_BODY in text,
         'Karakeep logical export does not contain the synthetic text bookmark')
    return {'json_files': len(json_names), 'entries': len(names),
            'text_bookmark_verified': True, 'binary_assets_in_scope': False}


def backup_summary(manifest):
    return {'bookmarks': 2, 'asset_bytes': manifest['browser']['asset']['bytes'],
            'asset_sha256': manifest['browser']['asset']['sha256'],
            'data_files': len(manifest['data_tree']),
            'application_export_bytes': manifest['application_export']['bytes'],
            'recovery_status': manifest['recovery_status']}


def verify_backup(root):
    root = safe_path(Path(root))
    verify_private(root, directory=True)
    manifest = read_private(root / 'manifest.json')
    keys(manifest, {'kind', 'created_utc', 'images', 'method',
                    'authoritative_material', 'supplementary_material',
                    'derived_material', 'consistency', 'recovery_status',
                    'credentials_hash', 'configuration_sha256', 'database_sha256',
                    'database_bytes', 'data_tree', 'application_export',
                    'browser_sha256', 'browser', 'summary'}, 'Karakeep backup manifest')
    need(manifest['kind'] == 'karakeep-consistent-backup-v1'
         and manifest['images'] == images()
         and manifest['method'] == 'sqlite-quiesced-assets-reindex-restore',
         'Karakeep backup image/format mismatch')
    need(manifest['authoritative_material'] == ['sqlite-database', 'asset-tree',
                                                'private-credentials']
         and manifest['supplementary_material'] == ['application-logical-export']
         and manifest['derived_material'] == ['queue-database', 'meilisearch-index',
                                              'container-images', 'temporary-files',
                                              'sqlite-wal', 'sqlite-shm']
         and manifest['consistency'] == {'application_quiesced_for_copy': True,
                                         'sqlite_quick_check_verified': True,
                                         'asset_tree_copied': True,
                                         'queue_database_excluded': True,
                                         'search_index_excluded': True,
                                         'logical_export_verified': True}
         and manifest['recovery_status'] == 'pending-independent-restore',
         'Karakeep backup consistency/recovery evidence is incomplete')
    credentials = validate_credentials(read_private(root / 'credentials.json'), seeded=True)
    need(digest(credentials) == manifest['credentials_hash'],
         'Karakeep backup credential checksum mismatch')
    database = root / 'data' / 'db.db'
    sqlite_check(database)
    need(database.stat().st_size == manifest['database_bytes']
         and file_hash(database) == manifest['database_sha256'],
         'Karakeep SQLite checksum or size mismatch')
    need(not any((root / 'data' / name).exists()
                 for name in ('queue.db', 'db.db-wal', 'db.db-shm')),
         'Karakeep backup includes derived queue or transient SQLite files')
    need((root / 'data' / 'assets').is_dir(), 'Karakeep asset tree is missing')
    need(tree_files(root / 'data') == manifest['data_tree'],
         'Karakeep data tree checksum mismatch')
    need(manifest['configuration_sha256'] == {
        'private': file_hash(root / 'compose.private.json'),
        'sanitized': file_hash(root / 'sanitized-config.json')},
         'Karakeep backup configuration checksum mismatch')
    export = root / 'application-export.zip'
    verify_logical_export(export)
    need(manifest['application_export'] == {'bytes': export.stat().st_size,
                                            'sha256': file_hash(export)},
         'Karakeep application export checksum mismatch')
    browser = read_private(root / 'browser-fixture.json')
    need(file_hash(root / 'browser-fixture.json') == manifest['browser_sha256']
         and browser == manifest['browser'], 'Karakeep browser evidence checksum mismatch')
    parse_browser_output(json.dumps({key: browser[key] for key in (
        'kind', 'text_id', 'asset_id', 'asset_bookmark_id', 'title', 'body',
        'title_sha256', 'body_sha256', 'asset', 'rendered_title',
        'full_text_search', 'asset_downloaded', 'search_reindexed', 'browser',
        'headless', 'application_export')}))
    need(backup_summary(manifest) == manifest['summary'],
         'Karakeep backup summary mismatch')
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
        need(state['status'] == 'running' and set(resources['containers']) == set(SERVICES)
             and all(row['State']['Running'] for row in resources['containers'].values()),
             'Start the complete owned Karakeep project before backup')
        browser = read_private(root / 'browser-fixture.json')
        cycle = uuid.uuid4().hex[:12]
        browser_validate(plan, 'verify', browser, 'pre-backup-' + cycle)
        stopped = False
        failed_stage = 'quiesce'
        try:
            docker(compose_args(plan) + ['stop', '--timeout', '45'],
                   context=plan['runtime']['context'], timeout=180)
            stopped = True
            failed_stage = 'integrity-check'
            sqlite_check(root / 'data' / 'db.db')
            create_private_directory(destination)
            create_private_directory(destination / 'data')
            create_private_directory(destination / 'data' / 'assets')
            failed_stage = 'authoritative-copy'
            shutil.copy2(root / 'data' / 'db.db', destination / 'data' / 'db.db')
            if (root / 'data' / 'assets').is_dir():
                shutil.copytree(root / 'data' / 'assets', destination / 'data' / 'assets',
                                dirs_exist_ok=True)
            tree_files(destination / 'data', protect_new=True)
            failed_stage = 'metadata-copy'
            for source, target in (
                    (root / 'credentials.json', destination / 'credentials.json'),
                    (root / 'compose.json', destination / 'compose.private.json'),
                    (root / 'browser-fixture.json', destination / 'browser-fixture.json'),
                    (root / 'application-export.zip', destination / 'application-export.zip')):
                shutil.copy2(source, target)
                protect_file(target)
            atomic_json(destination / 'sanitized-config.json', {
                'kind': 'karakeep-sanitized-configuration-v1',
                'images': plan['images'], 'limits': plan['limits'],
                'access': plan['access'], 'network': plan['network'],
                'registration': plan['registration'], 'mail': plan['mail'],
                'ai': plan['ai'], 'telemetry': plan['telemetry'],
                'recovery_method': plan['recovery_method'],
                'search_recovery': 'rebuild-from-authoritative-database',
            })
            saved_browser = read_private(destination / 'browser-fixture.json')
            database = destination / 'data' / 'db.db'
            export = destination / 'application-export.zip'
            verify_logical_export(export)
            manifest = {
                'kind': 'karakeep-consistent-backup-v1',
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'images': plan['images'],
                'method': 'sqlite-quiesced-assets-reindex-restore',
                'authoritative_material': ['sqlite-database', 'asset-tree',
                                           'private-credentials'],
                'supplementary_material': ['application-logical-export'],
                'derived_material': ['queue-database', 'meilisearch-index',
                                     'container-images', 'temporary-files',
                                     'sqlite-wal', 'sqlite-shm'],
                'consistency': {'application_quiesced_for_copy': True,
                                'sqlite_quick_check_verified': True,
                                'asset_tree_copied': True,
                                'queue_database_excluded': True,
                                'search_index_excluded': True,
                                'logical_export_verified': True},
                'recovery_status': 'pending-independent-restore',
                'credentials_hash': digest(read_private(destination / 'credentials.json')),
                'configuration_sha256': {
                    'private': file_hash(destination / 'compose.private.json'),
                    'sanitized': file_hash(destination / 'sanitized-config.json')},
                'database_sha256': file_hash(database),
                'database_bytes': database.stat().st_size,
                'data_tree': tree_files(destination / 'data'),
                'application_export': {'bytes': export.stat().st_size,
                                       'sha256': file_hash(export)},
                'browser_sha256': file_hash(destination / 'browser-fixture.json'),
                'browser': saved_browser, 'summary': None,
            }
            manifest['summary'] = backup_summary(manifest)
            atomic_json(destination / 'manifest.json', manifest)
            failed_stage = 'manifest-verification'
            verify_backup(destination)
        except (ConfigError, OSError) as error:
            raise ConfigError('Karakeep backup failed during ' + failed_stage
                              + '; sensitive partial state was retained for review') from error
        finally:
            if stopped:
                docker(compose_args(plan) + ['start'],
                       context=plan['runtime']['context'], timeout=240)
                wait_health(plan)
        browser_validate(plan, 'verify', browser, 'post-backup-' + cycle)
        return {'backup_complete': True, 'application_consistent': True,
                'search_index_excluded': True, 'logical_export_supplementary': True,
                'encrypted': False, 'contains_credentials': True,
                'summary': manifest['summary'], 'recovery_verified': False,
                'note': ('Sensitive local staging backup; restore into a fresh project '
                         'before encrypted off-host retention')}
