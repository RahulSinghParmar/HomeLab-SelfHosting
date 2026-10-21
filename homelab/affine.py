"""Isolated AFFiNE lifecycle, synthetic sync exercise and consistent recovery."""
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
from .paperless import tree_files
from .privatefs import (atomic_json, create_lock_file, create_private_directory,
                        operation_lock, read_private, safe_path, verify_private,
                        windows_acl)
from .sandbox import digest, pending_guard


MODULE = ROOT / 'modules/affine'
SERVICES = ('redis', 'postgres', 'migration', 'affine')
VOLUMES = ('redis-data', 'database-data')
LIMITS = {
    'redis': {'memory_mib': 160, 'cpus': 0.25, 'pids': 96},
    'postgres': {'memory_mib': 512, 'cpus': 0.75, 'pids': 128},
    'migration': {'memory_mib': 768, 'cpus': 1.0, 'pids': 256},
    'affine': {'memory_mib': 1536, 'cpus': 2.0, 'pids': 512},
}
MARKER = 'HomeLab AFFiNE Phase 5 recovery marker v1'
BROWSER_TITLE = 'AFFiNE browser recovery proof'
BROWSER_BODY = 'Browser-rendered synthetic document survives encrypted off-host recovery.'


def images():
    return load_json(MODULE / 'images.json')


def browser_specification():
    return load_json(MODULE / 'browser.json')


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
                    'method': 'postgres-config-storage'}
    plan = {
        'kind': 'homelab-affine-plan', 'contract': 'affine-isolated-recovery-v1',
        'platform': host_platform(), 'root': str(root), 'port': port, 'runtime': runtime,
        'images': images(), 'recovery': recovery, 'limits': LIMITS,
        'access': 'loopback', 'networks': ['frontend', 'internal-backend'],
        'docker_socket': False, 'mail': 'disabled', 'signups': False,
        'ai': 'disabled', 'indexer': 'disabled', 'deployment_type': 'selfhosted',
        'fixture_mode': 'isolated-first-admin',
        'recovery_material': ['postgres-custom-dump', 'config', 'storage'],
    }
    plan['plan_id'] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'root', 'port', 'runtime', 'images',
                'recovery', 'limits', 'access', 'networks', 'docker_socket', 'mail',
                'signups', 'ai', 'indexer', 'deployment_type', 'fixture_mode',
                'recovery_material', 'plan_id'}, 'AFFiNE plan')
    backup = plan['recovery']['path'] if plan['recovery'] is not None else None
    need(canonical(plan) == canonical(make_plan(plan['root'], plan['port'], plan['runtime'], backup)),
         'Plan/image/recovery drift; review a new plan')
    return plan


def project(plan):
    return 'hl-affine-' + plan['plan_id'][:16]


def tags(plan, owner):
    return {'org.homelab.owner': owner, 'org.homelab.plan': plan['plan_id'],
            'org.homelab.module': 'affine'}


def new_credentials():
    return {'database_password': secrets.token_hex(32),
            'redis_password': secrets.token_hex(32),
            'fixture_password': 'Aa1-' + secrets.token_hex(12)}


def validate_credentials(value):
    keys(value, {'database_password', 'redis_password', 'fixture_password'},
         'AFFiNE credentials')
    need(all(isinstance(value[name], str) and re.fullmatch('[0-9a-f]{64}', value[name])
             for name in ('database_password', 'redis_password')),
         'Invalid private database/cache credential material')
    need(isinstance(value['fixture_password'], str)
         and re.fullmatch('Aa1-[0-9a-f]{24}', value['fixture_password']),
         'Invalid private AFFiNE fixture credential material')
    return value


def compose(plan, owner, credentials):
    validate_credentials(credentials)
    label = tags(plan, owner)
    common = {'labels': label, 'pull_policy': 'never',
              'security_opt': ['no-new-privileges:true'],
              'logging': {'driver': 'json-file',
                          'options': {'max-size': '10m', 'max-file': '3'}}}
    redis = {
        **common, 'image': plan['images']['cache'], 'restart': 'unless-stopped',
        'command': ['sh', '-ec', 'exec redis-server --appendonly yes --requirepass "$$REDIS_PASSWORD"'],
        'environment': {'REDIS_PASSWORD': credentials['redis_password']},
        'volumes': [{'type': 'volume', 'source': 'redis-data', 'target': '/data'}],
        'networks': ['backend'],
        'healthcheck': {'test': ['CMD-SHELL', 'redis-cli -a "$$REDIS_PASSWORD" ping | grep -q PONG'],
                        'interval': '10s', 'timeout': '5s', 'retries': 12,
                        'start_period': '10s'},
        'mem_limit': '160m', 'mem_reservation': '32m', 'memswap_limit': '224m',
        'cpus': 0.25, 'pids_limit': 96,
    }
    postgres = {
        **common, 'image': plan['images']['database'], 'restart': 'unless-stopped',
        'environment': {'POSTGRES_USER': 'affine', 'POSTGRES_DB': 'affine',
                        'POSTGRES_PASSWORD': credentials['database_password'],
                        'POSTGRES_INITDB_ARGS': '--data-checksums'},
        'volumes': [{'type': 'volume', 'source': 'database-data',
                     'target': '/var/lib/postgresql/data'}],
        'networks': ['backend'], 'shm_size': '128m',
        'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U affine -d affine'],
                        'interval': '10s', 'timeout': '5s', 'retries': 12,
                        'start_period': '20s'},
        'mem_limit': '512m', 'mem_reservation': '128m', 'memswap_limit': '768m',
        'cpus': 0.75, 'pids_limit': 128,
    }
    app_environment = {
        'NODE_ENV': 'production', 'AFFINE_ENV': 'production',
        'DEPLOYMENT_TYPE': 'selfhosted', 'REDIS_SERVER_HOST': 'redis',
        'REDIS_SERVER_PASSWORD': credentials['redis_password'],
        'DATABASE_URL': ('postgresql://affine:' + credentials['database_password']
                         + '@postgres:5432/affine'),
        'AFFINE_SERVER_EXTERNAL_URL': 'http://127.0.0.1:' + str(plan['port']),
        'AFFINE_INDEXER_ENABLED': 'false',
        'HOMELAB_FIXTURE_PASSWORD': credentials['fixture_password'],
    }
    persistent_mounts = [
        {'type': 'bind', 'source': str(Path(plan['root']) / 'config'),
         'target': '/root/.affine/config', 'bind': {'create_host_path': False}},
        {'type': 'bind', 'source': str(Path(plan['root']) / 'storage'),
         'target': '/root/.affine/storage', 'bind': {'create_host_path': False}},
    ]
    migration = {
        **common, 'image': plan['images']['affine'], 'restart': 'no',
        'command': ['sh', '-c', 'node ./scripts/self-host-predeploy.js'],
        'environment': app_environment, 'volumes': persistent_mounts,
        'depends_on': {'redis': {'condition': 'service_healthy'},
                       'postgres': {'condition': 'service_healthy'}},
        'networks': ['backend'], 'stop_grace_period': '60s',
        'mem_limit': '768m', 'mem_reservation': '128m', 'memswap_limit': '1024m',
        'cpus': 1.0, 'pids_limit': 256,
    }
    affine = {
        **common, 'image': plan['images']['affine'], 'restart': 'unless-stopped',
        'environment': app_environment,
        'depends_on': {'redis': {'condition': 'service_healthy'},
                       'postgres': {'condition': 'service_healthy'},
                       'migration': {'condition': 'service_completed_successfully'}},
        'ports': [{'target': 3010, 'published': str(plan['port']),
                   'host_ip': '127.0.0.1', 'protocol': 'tcp'}],
        'volumes': [*persistent_mounts,
                    {'type': 'bind', 'source': str(MODULE / 'fixture.mjs'),
                     'target': '/homelab/fixture.mjs', 'read_only': True,
                     'bind': {'create_host_path': False}}],
        'networks': ['frontend', 'backend'],
        'healthcheck': {'test': ['CMD', 'node', '-e',
                                 "fetch('http://127.0.0.1:3010/').then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))"],
                        'interval': '10s', 'timeout': '10s', 'retries': 30,
                        'start_period': '60s'},
        'stop_grace_period': '60s', 'mem_limit': '1536m',
        'mem_reservation': '384m', 'memswap_limit': '2048m',
        'cpus': 2.0, 'pids_limit': 512,
    }
    return {
        'services': {'redis': redis, 'postgres': postgres,
                     'migration': migration, 'affine': affine},
        'volumes': {name: {'labels': label} for name in VOLUMES},
        'networks': {'frontend': {'driver': 'bridge', 'labels': label},
                     'backend': {'driver': 'bridge', 'internal': True, 'labels': label}},
    }


def compose_args(plan):
    root = Path(plan['root'])
    return ['compose', '--project-name', project(plan), '--project-directory', str(root),
            '-f', str(root / 'compose.json')]


def inventory(plan, owner):
    context = plan['runtime']['context']
    found = {'containers': {}, 'networks': [], 'volumes': []}
    ids = docker(['ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project(plan)],
                 context=context).split()
    need(len(ids) <= len(SERVICES), 'Unexpected AFFiNE project containers')
    rows = json.loads(docker(['inspect'] + ids, context=context)) if ids else []
    image_roles = {'redis': 'cache', 'postgres': 'database',
                   'migration': 'affine', 'affine': 'affine'}
    for row in rows:
        labels = row['Config'].get('Labels') or {}
        need(owner is not None and all(labels.get(key) == value
                                       for key, value in tags(plan, owner).items()),
             'Foreign AFFiNE resource; no adoption or mutation')
        role = labels.get('com.docker.compose.service')
        need(role in SERVICES and role not in found['containers'],
             'Unexpected or duplicate AFFiNE service')
        need(row['Config']['Image'] == plan['images'][image_roles[role]], 'AFFiNE image drift')
        host = row['HostConfig']
        need(not host['Privileged'] and not host.get('Devices') and not host.get('DeviceRequests'),
             'AFFiNE privilege/device drift')
        need('no-new-privileges:true' in host['SecurityOpt'], 'AFFiNE security option drift')
        limit = LIMITS[role]
        need(host['Memory'] == limit['memory_mib'] * 1024**2
             and host['NanoCpus'] == int(limit['cpus'] * 1_000_000_000)
             and host['PidsLimit'] == limit['pids'], 'AFFiNE resource drift')
        expected_restart = 'no' if role == 'migration' else 'unless-stopped'
        need(host['RestartPolicy']['Name'] == expected_restart, 'AFFiNE lifecycle drift')
        expected_ports = ({'3010/tcp': [{'HostIp': '127.0.0.1',
                                        'HostPort': str(plan['port'])}]}
                          if role == 'affine' else {})
        need((host.get('PortBindings') or {}) == expected_ports, 'AFFiNE port binding drift')
        expected_networks = ({project(plan) + '_backend', project(plan) + '_frontend'}
                             if role == 'affine' else {project(plan) + '_backend'})
        need(set(row['NetworkSettings']['Networks']) == expected_networks,
             'AFFiNE network drift')
        found['containers'][role] = row
    for kind, listing, inspect, maximum in (
            ('networks', ['network', 'ls', '-q'], ['network', 'inspect'], 2),
            ('volumes', ['volume', 'ls', '-q'], ['volume', 'inspect'], len(VOLUMES))):
        resource_ids = docker(listing + ['--filter', 'label=com.docker.compose.project=' + project(plan)],
                              context=context).split()
        need(len(resource_ids) <= maximum, 'Unexpected AFFiNE project resources')
        values = json.loads(docker(inspect + resource_ids, context=context)) if resource_ids else []
        for row in values:
            labels = row.get('Labels') or {}
            need(owner is not None and all(labels.get(key) == value
                                           for key, value in tags(plan, owner).items()),
                 'Foreign AFFiNE resource; no adoption or mutation')
        found[kind] = values
    return found


def state_read(plan):
    root = Path(plan['root'])
    verify_private(root, directory=True)
    pending_guard(root)
    state = read_private(root / 'state.json')
    keys(state, {'kind', 'owner', 'plan_id', 'status', 'recovery'}, 'AFFiNE state')
    need(state['kind'] == 'affine-owned-v1' and state['plan_id'] == plan['plan_id'],
         'AFFiNE ownership mismatch')
    need(isinstance(state['owner'], str) and re.fullmatch('[0-9a-f]{32}', state['owner']),
         'Invalid AFFiNE owner')
    need(state['status'] in ('prepared', 'restoring', 'running', 'stopped',
                             'removing', 'removed'), 'Invalid AFFiNE state')
    credentials = validate_credentials(read_private(root / 'credentials.json'))
    need(read_private(root / 'compose.json') == compose(plan, state['owner'], credentials),
         'AFFiNE Compose modified; refusing execution')
    return state


def copy_tree(source, destination):
    need(source.is_dir() and destination.is_dir(), 'AFFiNE recovery tree is missing')
    shutil.copytree(source, destination, dirs_exist_ok=True)


def prepare(plan):
    root = Path(plan['root'])
    if root.exists():
        return state_read(plan)
    inventory(plan, None)
    port_free(plan['port'])
    context = plan['runtime']['context']
    for image in plan['images'].values():
        inspected = json.loads(docker(['image', 'inspect', image], context=context))[0]
        need(inspected['Os'] == 'linux' and inspected['Architecture'] == 'amd64',
             'Reviewed linux/amd64 AFFiNE images must be cached')
    create_private_directory(root)
    create_lock_file(root / 'operation.lock')
    create_private_directory(root / 'config')
    create_private_directory(root / 'storage')
    credentials = (read_private(Path(plan['recovery']['path']) / 'credentials.json')
                   if plan['recovery'] else new_credentials())
    validate_credentials(credentials)
    if plan['recovery']:
        source = Path(plan['recovery']['path'])
        copy_tree(source / 'config', root / 'config')
        copy_tree(source / 'storage', root / 'storage')
    else:
        atomic_json(root / 'config' / 'config.json', {
            '$schema': 'https://github.com/toeverything/AFFiNE/releases/latest/download/config.schema.json',
            'server': {'externalUrl': 'http://127.0.0.1:' + str(plan['port']),
                       'name': 'HomeLab AFFiNE Recovery Trial'},
            'auth': {'allowSignup': False, 'allowSignupForOauth': False,
                     'requireEmailVerification': False},
            'flags': {'allowGuestDemoWorkspace': False},
            'metrics': {'enabled': False}, 'indexer': {'enabled': False},
            'copilot': {'enabled': False, 'byok': {'enabled': False}},
        })
    owner = uuid.uuid4().hex
    state = {'kind': 'affine-owned-v1', 'owner': owner, 'plan_id': plan['plan_id'],
             'status': 'prepared', 'recovery': None}
    atomic_json(root / 'credentials.json', credentials)
    atomic_json(root / 'compose.json', compose(plan, owner, credentials))
    atomic_json(root / 'state.json', state)
    return state


def container_state(context, container):
    return json.loads(docker(['inspect', '--format',
                              '{"status":{{json .State.Status}},"exit":{{.State.ExitCode}},"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}}}',
                              container], context=context))


def wait_health(plan, deadline_seconds=360):
    deadline = time.monotonic() + deadline_seconds
    context = plan['runtime']['context']
    while time.monotonic() < deadline:
        ids = {role: docker(compose_args(plan) + ['ps', '-aq', role], context=context)
               for role in SERVICES}
        if all(ids.values()):
            states = {role: container_state(context, value) for role, value in ids.items()}
            need(not any(value['status'] in ('dead', 'removing') for value in states.values()),
                 'AFFiNE service failed before becoming ready')
            migration_ok = (states['migration']['status'] == 'exited'
                            and states['migration']['exit'] == 0)
            healthy = all(states[role]['health'] == 'healthy'
                          for role in ('redis', 'postgres', 'affine'))
            if migration_ok and healthy:
                return
            need(not (states['migration']['status'] == 'exited'
                      and states['migration']['exit'] != 0), 'AFFiNE migration failed')
            need(not any(states[role]['status'] == 'exited'
                         for role in ('redis', 'postgres', 'affine')),
                 'AFFiNE long-running service exited before becoming healthy')
        time.sleep(2)
    raise ConfigError('AFFiNE services did not become healthy before the bounded deadline')


def wait_foundation(plan, deadline_seconds=180):
    deadline = time.monotonic() + deadline_seconds
    context = plan['runtime']['context']
    while time.monotonic() < deadline:
        values = []
        for role in ('redis', 'postgres'):
            container = docker(compose_args(plan) + ['ps', '-q', role], context=context)
            values.append(container_state(context, container) if container else {})
        if values and all(value.get('health') == 'healthy' for value in values):
            return
        time.sleep(2)
    raise ConfigError('AFFiNE database/cache did not become healthy before the bounded deadline')


def parse_fixture_output(output):
    rows = []
    for line in output.splitlines():
        if line.startswith('{'):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if value.get('kind') == 'affine-synthetic-document-v1':
                rows.append(value)
    need(len(rows) == 1, 'AFFiNE fixture returned no single bounded evidence result')
    value = rows[0]
    need(value.get('marker') == MARKER and value.get('independent_sessions') is True,
         'AFFiNE fixture semantic evidence is invalid')
    need(re.fullmatch('[0-9a-f]{64}', value.get('marker_sha256', '')) is not None
         and re.fullmatch('[0-9a-f]{64}', value.get('state_sha256', '')) is not None,
         'AFFiNE fixture checksum evidence is invalid')
    need(isinstance(value.get('workspace_id'), str) and value['workspace_id']
         and isinstance(value.get('doc_id'), str) and value['doc_id'],
         'AFFiNE fixture identifiers are invalid')
    return value


def parse_browser_output(output):
    rows = []
    for line in output.splitlines():
        if line.startswith('{'):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if value.get('kind') == 'affine-browser-document-v1':
                rows.append(value)
    need(len(rows) == 1, 'AFFiNE browser returned no single bounded evidence result')
    value = rows[0]
    required = {'kind', 'workspace_id', 'doc_id', 'title', 'body', 'title_sha256',
                'body_sha256', 'browser', 'headless', 'rendered_title',
                'rendered_body', 'reload_persistence', 'independent_sessions'}
    keys(value, required, 'AFFiNE browser evidence')
    need(value['title'] == BROWSER_TITLE and value['body'] == BROWSER_BODY
         and value['title_sha256'] == hashlib.sha256(BROWSER_TITLE.encode()).hexdigest()
         and value['body_sha256'] == hashlib.sha256(BROWSER_BODY.encode()).hexdigest()
         and value['browser'] == 'chromium' and value['headless'] is True
         and value['rendered_title'] is True and value['rendered_body'] is True
         and value['reload_persistence'] is True
         and value['independent_sessions'] is True,
         'AFFiNE browser-rendered semantic evidence is invalid')
    need(isinstance(value['workspace_id'], str) and value['workspace_id']
         and isinstance(value['doc_id'], str) and value['doc_id'],
         'AFFiNE browser document identifiers are invalid')
    return value


def browser_source_id():
    names = ('Dockerfile', 'package.json', 'package-lock.json', 'validate.mjs')
    values = {name: hashlib.sha256((MODULE / 'browser' / name).read_bytes()).hexdigest()
              for name in names}
    values['runtime'] = browser_specification()
    return digest(values)


def browser_image_tag():
    return 'homelab-affine-browser:' + browser_source_id()[:16]


def build_browser_image(plan):
    specification = browser_specification()
    inspected = json.loads(docker(['image', 'inspect', specification['image']],
                                  context=plan['runtime']['context']))[0]
    need(inspected['Os'] == 'linux' and inspected['Architecture'] == 'amd64',
         'Reviewed linux/amd64 browser runtime must be cached')
    docker(['build', '--pull=false', '--label', 'org.homelab.module=affine-browser',
            '--label', 'org.homelab.browser-source=' + browser_source_id(),
            '--tag', browser_image_tag(), str(MODULE / 'browser')],
           context=plan['runtime']['context'], timeout=900)
    return browser_image_tag()


def copy_browser_evidence(plan, container, source, target):
    target = Path(target)
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
        raise ConfigError('Docker evidence copy unavailable or interrupted') from error
    need(result.returncode == 0,
         'Docker evidence copy command failed; no raw logs exposed; retain state for review')
    try:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode='r:*') as archive:
            members = [member for member in archive.getmembers() if member.isfile()]
            need(len(members) == 1,
                 'Docker evidence archive regular-file count is ' + str(len(members)))
            need(members[0].size <= 64 * 1024 * 1024,
                 'Docker evidence archive file exceeds the 64 MiB bound')
            source_file = archive.extractfile(members[0])
            need(source_file is not None, 'Docker evidence archive is unreadable')
            content = source_file.read()
            need(len(content) == members[0].size,
                 'Docker evidence archive is incomplete')
    except (tarfile.TarError, OSError) as error:
        raise ConfigError('Docker evidence archive is invalid') from error
    try:
        with target.open('xb') as destination:
            destination.write(content)
    except OSError as error:
        raise ConfigError('Docker evidence destination write failed') from error
    try:
        protect_file(target)
    except (ConfigError, OSError) as error:
        raise ConfigError('Docker evidence private-file protection failed') from error


def browser_validate(plan, action, fixture, screenshot_name):
    need(action in ('seed', 'verify'), 'Unsupported AFFiNE browser validation action')
    validate_credentials(read_private(Path(plan['root']) / 'credentials.json'))
    credentials = read_private(Path(plan['root']) / 'credentials.json')
    evidence_root = Path(plan['root']) / 'browser-evidence'
    if not evidence_root.exists():
        create_private_directory(evidence_root)
    try:
        image = build_browser_image(plan)
    except ConfigError as error:
        raise ConfigError('AFFiNE browser validation failed during image-build') from error
    screenshot = action + '-' + screenshot_name + '.png'
    arguments = [
        'create', '--init', '--read-only', '--network', project(plan) + '_frontend',
        '--memory', '768m', '--cpus', '1', '--pids-limit', '256',
        '--security-opt', 'no-new-privileges:true', '--cap-drop', 'ALL',
        '--shm-size', '512m',
        '--tmpfs', '/tmp:rw,nosuid,size=256m,uid=1001,gid=1001,mode=0700',
        '--tmpfs', '/home/pwuser:rw,nosuid,size=64m,uid=1001,gid=1001,mode=0700',
        '--mount', 'type=volume,destination=/evidence',
        '--label', 'org.homelab.module=affine-browser',
        '--label', 'org.homelab.plan=' + plan['plan_id'],
        '--env', 'AFFINE_BROWSER_BASE_URL=http://127.0.0.1:' + str(plan['port']),
        '--env', 'AFFINE_BROWSER_LOCAL_PORT=' + str(plan['port']),
        '--env', 'AFFINE_BROWSER_UPSTREAM_HOST=affine',
        '--env', 'AFFINE_BROWSER_PASSWORD=' + credentials['fixture_password'],
        '--env', 'AFFINE_BROWSER_WORKSPACE_ID=' + fixture['workspace_id'],
        '--env', 'AFFINE_BROWSER_ACTION=' + action,
        '--env', 'AFFINE_BROWSER_SCREENSHOT=/evidence/' + screenshot,
    ]
    if action == 'seed':
        arguments.extend(['--env', 'AFFINE_BROWSER_SOURCE_DOC_ID=' + fixture['doc_id']])
    else:
        arguments.extend(['--env', 'AFFINE_BROWSER_EXPECTED_DOC_ID=' + fixture['doc_id']])
    try:
        container = docker(arguments + [image], context=plan['runtime']['context'], timeout=120)
    except ConfigError as error:
        raise ConfigError('AFFiNE browser validation failed during container-create') from error
    need(re.fullmatch('[0-9a-f]{64}', container) is not None,
         'AFFiNE browser validation container identity is invalid')
    failed_stage = 'container-start'
    try:
        docker(['start', container], context=plan['runtime']['context'], timeout=120)
        failed_stage = 'container-wait'
        exit_code = docker(['wait', container], context=plan['runtime']['context'], timeout=900)
        failed_stage = 'container-logs'
        output = docker(['logs', '--tail', '100', container],
                        context=plan['runtime']['context'], timeout=120)
        if exit_code != '0':
            failed_stage = 'error-evidence-copy'
            diagnostic = evidence_root / ('error-' + screenshot)
            try:
                copy_browser_evidence(plan, container, '/evidence/' + screenshot, diagnostic)
            except ConfigError:
                pass
            raise ConfigError('AFFiNE browser validation failed: ' + output[-1000:])
        failed_stage = 'browser-output-parse'
        value = parse_browser_output(output)
        target = evidence_root / screenshot
        failed_stage = 'success-evidence-copy'
        copy_browser_evidence(plan, container, '/evidence/' + screenshot, target)
    except ConfigError as error:
        if str(error).startswith('AFFiNE browser validation failed:'):
            raise
        if str(error).startswith('Docker evidence'):
            raise ConfigError('AFFiNE browser validation failed during '
                              + failed_stage + ': ' + str(error)) from error
        raise ConfigError('AFFiNE browser validation failed during ' + failed_stage) from error
    finally:
        try:
            docker(['rm', '-f', '-v', container], context=plan['runtime']['context'], timeout=120)
        except ConfigError:
            pass
    evidence = {**value, 'screenshot_sha256': file_hash(target),
                'browser_source_id': browser_source_id(),
                'browser_image': browser_specification()['image']}
    if action == 'verify':
        need(all(evidence[name] == fixture[name]
                 for name in ('workspace_id', 'doc_id', 'title', 'body',
                              'title_sha256', 'body_sha256')),
             'Recovered browser-rendered AFFiNE document differs from saved evidence')
    return evidence


def verify_fixture(plan, evidence):
    output = docker(compose_args(plan) + ['exec', '-T', 'affine', 'node',
                    '/homelab/fixture.mjs', 'verify', evidence['workspace_id'], evidence['doc_id']],
                    context=plan['runtime']['context'], timeout=120)
    value = parse_fixture_output(output)
    need(value['marker_sha256'] == evidence['marker_sha256']
         and value['state_sha256'] == evidence['state_sha256'],
         'AFFiNE recovered document state differs from saved evidence')
    return {key: value[key] for key in ('kind', 'workspace_id', 'doc_id', 'marker',
                                        'marker_sha256', 'state_sha256',
                                        'independent_sessions')}


def content_inventory(plan):
    evidence = read_private(Path(plan['root']) / 'fixture.json')
    return verify_fixture(plan, evidence)


def restore_database(plan, backup, postgres_container):
    context = plan['runtime']['context']
    target = '/tmp/affine-' + uuid.uuid4().hex + '.dump'
    docker(['cp', str(backup / 'affine-postgres.dump'), postgres_container + ':' + target],
           context=context, timeout=180)
    try:
        docker(['exec', postgres_container, 'pg_restore', '--clean', '--if-exists',
                '--no-owner', '--no-privileges', '-U', 'affine', '-d', 'affine', target],
               context=context, timeout=600)
    finally:
        docker(['exec', postgres_container, 'rm', '-f', target], context=context)


def operate(plan, action, confirmation=None):
    validate_plan(plan)
    need(action in ('up', 'status', 'stop', 'remove'), 'Unsupported AFFiNE action')
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
        need(state['status'] != 'restoring',
             'Interrupted AFFiNE restore requires manual evidence review and a fresh target')
        if action == 'up':
            need(state['status'] not in ('removing', 'removed'),
                 'Removed AFFiNE deployments require a fresh root')
            if not containers:
                need(state['status'] == 'prepared' and (not resources['volumes'] or not plan['recovery']),
                     'Recorded AFFiNE resources missing; no silent recreation')
                port_free(plan['port'])
                docker(compose_args(plan) + ['create', '--pull', 'never', '--no-build'],
                       context=context, timeout=300)
                resources = inventory(plan, state['owner'])
                containers = resources['containers']
            need(set(containers) == set(SERVICES) and len(resources['volumes']) == len(VOLUMES),
                 'Incomplete AFFiNE creation; retain state for review')
            need(not any(row['State'].get('Paused') for row in containers.values()),
                 'Paused AFFiNE state requires manual review')
            if plan['recovery'] and state['status'] == 'prepared':
                need(not any(row['State']['Running'] for row in containers.values()),
                     'AFFiNE recovery must target never-started containers')
                state['status'] = 'restoring'
                atomic_json(root / 'state.json', state, replace=True)
                docker(compose_args(plan) + ['start', 'redis', 'postgres'], context=context, timeout=120)
                wait_foundation(plan)
                restore_database(plan, Path(plan['recovery']['path']), containers['postgres']['Id'])
                docker(['start', '-a', containers['migration']['Id']], context=context, timeout=600)
                migration = container_state(context, containers['migration']['Id'])
                need(migration['status'] == 'exited' and migration['exit'] == 0,
                     'AFFiNE migration failed after database restore')
                state['status'] = 'prepared'
                atomic_json(root / 'state.json', state, replace=True)
            port_free(plan['port'])
            docker(compose_args(plan) + ['up', '-d', '--no-build', '--pull', 'never'],
                   context=context, timeout=600)
            wait_health(plan)
            if plan['recovery']:
                source = verify_backup(Path(plan['recovery']['path']))
                fixture = source['inventory']
                fixture_path = root / 'fixture.json'
                if fixture_path.exists():
                    need(read_private(fixture_path) == fixture,
                         'Existing recovered AFFiNE fixture differs from backup evidence')
                else:
                    atomic_json(fixture_path, fixture)
                restored = content_inventory(plan)
                need(restored == fixture, 'Restored AFFiNE document differs from backup evidence')
                recovery_cycle = ('restored' if state['recovery'] is None else
                                  'restarted-' + uuid.uuid4().hex[:12])
                browser = browser_validate(plan, 'verify', source['browser'], recovery_cycle)
                browser_path = root / 'browser-fixture.json'
                if browser_path.exists():
                    existing_browser = read_private(browser_path)
                    need(all(existing_browser[name] == source['browser'][name]
                             for name in ('workspace_id', 'doc_id', 'title', 'body',
                                          'title_sha256', 'body_sha256')),
                         'Existing recovered browser evidence differs from backup evidence')
                    atomic_json(browser_path, browser, replace=True)
                else:
                    atomic_json(browser_path, browser)
                docker(compose_args(plan) + ['restart', 'affine'], context=context, timeout=180)
                wait_health(plan)
                need(content_inventory(plan) == fixture,
                     'Restored AFFiNE document did not persist across restart')
                persisted_browser = browser_validate(
                    plan, 'verify', source['browser'], recovery_cycle + '-application-restart')
                need(all(persisted_browser[name] == source['browser'][name]
                         for name in ('workspace_id', 'doc_id', 'title_sha256', 'body_sha256')),
                     'Browser-rendered AFFiNE document did not persist across restart')
                state['recovery'] = {'manifest_id': plan['recovery']['manifest_id'],
                                     'verified': True,
                                     'content_fingerprint': digest(fixture),
                                     'browser_fingerprint': digest(source['browser'])}
            state['status'] = 'running'
        elif action == 'stop':
            need(set(containers) == set(SERVICES)
                 and state['status'] not in ('removing', 'removed'),
                 'No complete owned AFFiNE deployment to stop')
            need(not any(row['State'].get('Paused') for row in containers.values()),
                 'Paused AFFiNE state requires manual review')
            docker(compose_args(plan) + ['stop', '--timeout', '60'],
                   context=context, timeout=180)
            state['status'] = 'stopped'
        elif action == 'remove':
            need(not any(row['State']['Running'] for row in containers.values()),
                 'Stop all owned AFFiNE services before removal')
            if state['status'] != 'removed':
                state['status'] = 'removing'
                atomic_json(root / 'state.json', state, replace=True)
                docker(compose_args(plan) + ['down', '--remove-orphans'],
                       context=context, timeout=180)
                state['status'] = 'removed'
        if action != 'status' and read_private(root / 'state.json') != state:
            atomic_json(root / 'state.json', state, replace=True)
        resources = inventory(plan, state['owner'])
        health = {}
        for role, row in resources['containers'].items():
            health[role] = (row['State'].get('Health') or {}).get('Status', row['State']['Status'])
        return {'module': 'affine', 'state': state['status'], 'health': health,
                'url': 'http://127.0.0.1:' + str(plan['port']),
                'migration_expected_state': 'exited-0',
                'data_volumes_retained': len(resources['volumes']),
                'recovery': state['recovery']}


def exercise(plan, confirmation):
    validate_plan(plan)
    need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        need(state['status'] == 'running' and set(resources['containers']) == set(SERVICES),
             'Start the complete owned AFFiNE project before exercise')
        need(not (root / 'fixture.json').exists(),
             'AFFiNE synthetic exercise is single-use for a fresh project')
        initialized = docker(compose_args(plan) + ['exec', '-T', 'affine', 'node',
                             '/homelab/fixture.mjs', 'init'],
                             context=plan['runtime']['context'], timeout=120)
        need('{"kind":"affine-admin-initialized-v1"}' in initialized,
             'AFFiNE synthetic first-admin initialization failed')
        browser = browser_validate(
            plan, 'seed', {'workspace_id': 'bootstrap', 'doc_id': 'bootstrap'}, 'source')
        atomic_json(root / 'browser-fixture.json', browser)
        output = docker(compose_args(plan) + ['exec', '-T', 'affine', 'node',
                        '/homelab/fixture.mjs', 'seed'],
                        context=plan['runtime']['context'], timeout=180)
        value = parse_fixture_output(output)
        evidence = {key: value[key] for key in ('kind', 'workspace_id', 'doc_id', 'marker',
                                                'marker_sha256', 'state_sha256',
                                                'independent_sessions')}
        atomic_json(root / 'fixture.json', evidence)
        docker(compose_args(plan) + ['restart', 'affine'],
               context=plan['runtime']['context'], timeout=180)
        wait_health(plan)
        need(content_inventory(plan) == evidence,
             'AFFiNE synthetic document did not persist across application restart')
        persisted_browser = browser_validate(plan, 'verify', browser, 'source-restart')
        need(all(persisted_browser[name] == browser[name]
                 for name in ('workspace_id', 'doc_id', 'title_sha256', 'body_sha256')),
             'AFFiNE browser-rendered document did not persist across application restart')
        return {'operation': 'create-edit-sync-restart-read', 'status': 'passed',
                'workspace_id': value['workspace_id'], 'doc_id': value['doc_id'],
                'independent_sessions': True, 'restart_persistence': True,
                'marker_sha256': value['marker_sha256'],
                'state_sha256': value['state_sha256'],
                'browser_rendered': True, 'browser_doc_id': browser['doc_id'],
                'browser_title_sha256': browser['title_sha256'],
                'browser_body_sha256': browser['body_sha256']}


def file_hash(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def backup_summary(manifest):
    return {'documents': 1, 'workspaces': 1,
            'marker_sha256': manifest['inventory']['marker_sha256'],
            'state_sha256': manifest['inventory']['state_sha256'],
            'content_fingerprint': digest(manifest['inventory']),
            'browser_documents': 1,
            'browser_title_sha256': manifest['browser']['title_sha256'],
            'browser_body_sha256': manifest['browser']['body_sha256'],
            'browser_fingerprint': digest(manifest['browser'])}


def verify_backup(root):
    root = safe_path(Path(root))
    verify_private(root, directory=True)
    manifest = read_private(root / 'manifest.json')
    keys(manifest, {'kind', 'created_utc', 'images', 'method', 'material',
                    'consistency', 'recovery_status', 'credentials_hash',
                    'configuration_sha256', 'database_sha256', 'browser_sha256',
                    'trees', 'inventory', 'browser', 'summary'}, 'AFFiNE backup manifest')
    need(manifest['kind'] == 'affine-consistent-backup-v1'
         and manifest['images'] == images()
         and manifest['method'] == 'postgres-config-storage',
         'AFFiNE backup image/format mismatch')
    need(manifest['material'] == ['postgres-custom-dump', 'config', 'storage',
                                  'browser-rendered-evidence']
         and manifest['consistency'] == {'application_quiesced': True,
                                         'migration_completed': True,
                                         'postgres_archive_readable': True,
                                         'config_copy_complete': True,
                                         'storage_copy_complete': True}
         and manifest['recovery_status'] == 'pending-independent-restore',
         'AFFiNE backup consistency/recovery evidence is incomplete')
    credentials = validate_credentials(read_private(root / 'credentials.json'))
    need(digest(credentials) == manifest['credentials_hash'],
         'AFFiNE backup credential checksum mismatch')
    need(file_hash(root / 'affine-postgres.dump') == manifest['database_sha256'],
         'AFFiNE PostgreSQL dump checksum mismatch')
    need(file_hash(root / 'browser-fixture.json') == manifest['browser_sha256']
         and read_private(root / 'browser-fixture.json') == manifest['browser'],
         'AFFiNE browser evidence checksum mismatch')
    need(manifest['configuration_sha256'] == {
        'private': file_hash(root / 'compose.private.json'),
        'sanitized': file_hash(root / 'sanitized-config.json')},
        'AFFiNE backup configuration checksum mismatch')
    expected = {'config': tree_files(root / 'config'),
                'storage': tree_files(root / 'storage')}
    need(expected == manifest['trees'], 'AFFiNE backup tree checksum mismatch')
    inventory_value = manifest['inventory']
    need(inventory_value.get('marker') == MARKER
         and inventory_value.get('independent_sessions') is True
         and manifest['browser'].get('rendered_title') is True
         and manifest['browser'].get('rendered_body') is True
         and manifest['browser'].get('reload_persistence') is True
         and manifest['browser'].get('independent_sessions') is True
         and backup_summary(manifest) == manifest['summary'],
         'AFFiNE backup lacks nonempty semantic recovery evidence')
    return manifest


def protect_file(path):
    if os.name == 'nt':
        windows_acl(path, create=True)
    else:
        path.chmod(0o600)
    verify_private(path)


def backup(plan, destination, confirmation):
    validate_plan(plan)
    need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    destination = safe_path(Path(destination))
    need(not destination.is_relative_to(root) and not root.is_relative_to(destination),
         'AFFiNE backup and installation must not overlap')
    need(not destination.exists() and destination.parent.is_dir(),
         'AFFiNE backup requires an absent destination under an existing parent')
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        need(state['status'] == 'running' and set(resources['containers']) == set(SERVICES)
             and all(resources['containers'][role]['State']['Running']
                     for role in ('redis', 'postgres', 'affine')),
             'Start the complete owned AFFiNE project before backup')
        inventory_value = content_inventory(plan)
        context = plan['runtime']['context']
        database = resources['containers']['postgres']['Id']
        dump_target = '/tmp/affine-' + uuid.uuid4().hex + '.dump'
        app_stopped = False
        failed_stage = 'quiesce'
        create_private_directory(destination)
        try:
            docker(compose_args(plan) + ['stop', '--timeout', '60', 'affine'],
                   context=context, timeout=180)
            app_stopped = True
            failed_stage = 'postgres-dump'
            docker(['exec', database, 'pg_dump', '-U', 'affine', '-d', 'affine',
                    '--format', 'custom', '--file', dump_target],
                   context=context, timeout=600)
            failed_stage = 'postgres-archive-check'
            docker(['exec', database, 'pg_restore', '--list', dump_target],
                   context=context, timeout=180)
            failed_stage = 'postgres-copy'
            docker(['cp', database + ':' + dump_target,
                    str(destination / 'affine-postgres.dump')],
                   context=context, timeout=180)
            docker(['exec', database, 'rm', '-f', dump_target], context=context)
            failed_stage = 'state-copy'
            create_private_directory(destination / 'config')
            create_private_directory(destination / 'storage')
            copy_tree(root / 'config', destination / 'config')
            copy_tree(root / 'storage', destination / 'storage')
            tree_files(destination / 'config', protect_new=True)
            tree_files(destination / 'storage', protect_new=True)
            shutil.copy2(root / 'credentials.json', destination / 'credentials.json')
            shutil.copy2(root / 'compose.json', destination / 'compose.private.json')
            shutil.copy2(root / 'browser-fixture.json', destination / 'browser-fixture.json')
            atomic_json(destination / 'sanitized-config.json', {
                'kind': 'affine-sanitized-configuration-v1', 'images': plan['images'],
                'limits': plan['limits'], 'access': plan['access'],
                'deployment_type': plan['deployment_type'], 'mail': plan['mail'],
                'signups': plan['signups'], 'ai': plan['ai'], 'indexer': plan['indexer'],
                'recovery_method': 'postgres-config-storage',
            })
            for path in (destination / 'credentials.json',
                         destination / 'compose.private.json',
                         destination / 'browser-fixture.json',
                         destination / 'affine-postgres.dump'):
                protect_file(path)
            trees = {'config': tree_files(destination / 'config'),
                     'storage': tree_files(destination / 'storage')}
            manifest = {'kind': 'affine-consistent-backup-v1',
                        'created_utc': datetime.now(timezone.utc).isoformat(),
                        'images': plan['images'], 'method': 'postgres-config-storage',
                        'material': ['postgres-custom-dump', 'config', 'storage',
                                     'browser-rendered-evidence'],
                        'consistency': {'application_quiesced': True,
                                        'migration_completed': True,
                                        'postgres_archive_readable': True,
                                        'config_copy_complete': True,
                                        'storage_copy_complete': True},
                        'recovery_status': 'pending-independent-restore',
                        'credentials_hash': digest(read_private(destination / 'credentials.json')),
                        'configuration_sha256': {
                            'private': file_hash(destination / 'compose.private.json'),
                            'sanitized': file_hash(destination / 'sanitized-config.json')},
                        'database_sha256': file_hash(destination / 'affine-postgres.dump'),
                        'browser_sha256': file_hash(destination / 'browser-fixture.json'),
                        'trees': trees, 'inventory': inventory_value,
                        'browser': read_private(destination / 'browser-fixture.json'),
                        'summary': None}
            manifest['summary'] = backup_summary(manifest)
            atomic_json(destination / 'manifest.json', manifest)
            failed_stage = 'manifest-verification'
            verify_backup(destination)
        except ConfigError as error:
            raise ConfigError('AFFiNE backup failed during ' + failed_stage
                              + '; sensitive partial state was retained for review') from error
        finally:
            try:
                docker(['exec', database, 'rm', '-f', dump_target], context=context)
            except ConfigError:
                pass
            if app_stopped:
                docker(compose_args(plan) + ['start', 'affine'], context=context, timeout=180)
                wait_health(plan)
        need(content_inventory(plan) == inventory_value,
             'AFFiNE document changed after backup restart; backup is not certified')
        return {'backup_complete': True, 'application_consistent': True,
                'encrypted': False, 'contains_credentials': True,
                'summary': manifest['summary'], 'recovery_verified': False,
                'note': ('Sensitive local staging backup; restore into a fresh project '
                         'before encrypted off-host retention')}
