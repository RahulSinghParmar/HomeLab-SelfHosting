"""Isolated AFFiNE lifecycle, synthetic sync exercise and consistent recovery."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
import shutil
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


def images():
    return load_json(MODULE / 'images.json')


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
                atomic_json(root / 'fixture.json', fixture)
                restored = content_inventory(plan)
                need(restored == fixture, 'Restored AFFiNE document differs from backup evidence')
                docker(compose_args(plan) + ['restart', 'affine'], context=context, timeout=180)
                wait_health(plan)
                need(content_inventory(plan) == fixture,
                     'Restored AFFiNE document did not persist across restart')
                state['recovery'] = {'manifest_id': plan['recovery']['manifest_id'],
                                     'verified': True,
                                     'content_fingerprint': digest(fixture)}
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
        return {'operation': 'create-edit-sync-restart-read', 'status': 'passed',
                'workspace_id': value['workspace_id'], 'doc_id': value['doc_id'],
                'independent_sessions': True, 'restart_persistence': True,
                'marker_sha256': value['marker_sha256'],
                'state_sha256': value['state_sha256']}


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
            'content_fingerprint': digest(manifest['inventory'])}


def verify_backup(root):
    root = safe_path(Path(root))
    verify_private(root, directory=True)
    manifest = read_private(root / 'manifest.json')
    keys(manifest, {'kind', 'created_utc', 'images', 'method', 'material',
                    'consistency', 'recovery_status', 'credentials_hash',
                    'configuration_sha256', 'database_sha256', 'trees',
                    'inventory', 'summary'}, 'AFFiNE backup manifest')
    need(manifest['kind'] == 'affine-consistent-backup-v1'
         and manifest['images'] == images()
         and manifest['method'] == 'postgres-config-storage',
         'AFFiNE backup image/format mismatch')
    need(manifest['material'] == ['postgres-custom-dump', 'config', 'storage']
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
            atomic_json(destination / 'sanitized-config.json', {
                'kind': 'affine-sanitized-configuration-v1', 'images': plan['images'],
                'limits': plan['limits'], 'access': plan['access'],
                'deployment_type': plan['deployment_type'], 'mail': plan['mail'],
                'signups': plan['signups'], 'ai': plan['ai'], 'indexer': plan['indexer'],
                'recovery_method': 'postgres-config-storage',
            })
            for path in (destination / 'credentials.json',
                         destination / 'compose.private.json',
                         destination / 'affine-postgres.dump'):
                protect_file(path)
            trees = {'config': tree_files(destination / 'config'),
                     'storage': tree_files(destination / 'storage')}
            manifest = {'kind': 'affine-consistent-backup-v1',
                        'created_utc': datetime.now(timezone.utc).isoformat(),
                        'images': plan['images'], 'method': 'postgres-config-storage',
                        'material': ['postgres-custom-dump', 'config', 'storage'],
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
                        'trees': trees, 'inventory': inventory_value, 'summary': None}
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
