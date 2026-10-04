"""Experimental isolated Kuma with stopped-volume backups; never adopts services."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import uuid

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .doctor import host_platform
from .glance import docker, local_runtime, port_free
from .privatefs import (atomic_json, create_lock_file, create_private_directory,
                        operation_lock, read_private, safe_path, verify_private, windows_acl)
from .sandbox import digest, pending_guard

MODULE = ROOT / 'modules/uptime-kuma'
FIXTURE = "require('http').createServer((q,s)=>{s.writeHead(200,{'Content-Type':'text/plain'});s.end('Synthetic fixture OK');}).listen(8080,'0.0.0.0');"


def make_plan(root, port, runtime, backup=None):
    root = safe_path(Path(root))
    need(root.parent.is_dir() and '$' not in str(root), 'Choose an absent installation under an existing local parent without interpolation characters')
    need(type(port) is int and 1024 <= port <= 65535, 'Choose an unprivileged TCP port')
    keys(runtime, {'context', 'endpoint', 'engine_id'}, 'local runtime')
    recovery = None
    if backup is not None:
        source = safe_path(Path(backup))
        need(not source.is_relative_to(root) and not root.is_relative_to(source), 'Backup and installation must not overlap')
        manifest = verify_backup(source)
        recovery = {'path': str(source), 'manifest_id': digest(manifest)}
    plan = {'kind': 'homelab-kuma-plan', 'contract': 'kuma-isolated-v1', 'platform': host_platform(),
            'root': str(root), 'port': port, 'runtime': runtime,
            'image': load_json(MODULE / 'image.json')['image'], 'recovery': recovery,
            'limits': {'kuma_memory_mib': 512, 'fixture_memory_mib': 64, 'kuma_cpus': 1, 'fixture_cpus': 0.25},
            'access': 'loopback', 'network': 'dedicated-bridge-outbound-allowed', 'docker_socket': False}
    plan['plan_id'] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'root', 'port', 'runtime', 'image', 'recovery', 'limits', 'access', 'network', 'docker_socket', 'plan_id'}, 'Kuma plan')
    backup = plan['recovery']['path'] if plan['recovery'] is not None else None
    need(canonical(plan) == canonical(make_plan(plan['root'], plan['port'], plan['runtime'], backup)), 'Plan/image/recovery drift; review a new plan')
    return plan


def project(plan):
    return 'hl-kuma-' + plan['plan_id'][:16]


def tags(plan, owner):
    return {'org.homelab.owner': owner, 'org.homelab.plan': plan['plan_id'], 'org.homelab.module': 'uptime-kuma'}


def compose(plan, owner):
    common = {'image': plan['image'], 'labels': tags(plan, owner), 'pull_policy': 'never',
              'restart': 'unless-stopped', 'read_only': True, 'cap_drop': ['ALL'],
              'security_opt': ['no-new-privileges:true'], 'pids_limit': 150,
              'logging': {'driver': 'json-file', 'options': {'max-size': '5m', 'max-file': '2'}}}
    return {'services': {
        'kuma': {**common, 'mem_limit': '512m', 'cpus': 1,
                 'environment': {'UPTIME_KUMA_DB_TYPE': 'sqlite', 'TZ': 'UTC'},
                 'tmpfs': ['/tmp:rw,noexec,nosuid,size=64m'],
                 'volumes': [{'type': 'volume', 'source': 'data', 'target': '/app/data', 'volume': {'nocopy': True}}],
                 'ports': [{'target': 3001, 'published': str(plan['port']), 'host_ip': '127.0.0.1', 'protocol': 'tcp'}]},
        'fixture': {**common, 'mem_limit': '64m', 'cpus': 0.25,
                    'command': ['node', '-e', FIXTURE], 'healthcheck': {'disable': True}}
    }, 'volumes': {'data': {'labels': tags(plan, owner)}},
        'networks': {'default': {'driver': 'bridge', 'labels': tags(plan, owner)}}}


def inventory(plan, owner):
    context = plan['runtime']['context']
    found = {'containers': {}, 'networks': [], 'volumes': []}
    for kind, query, inspect in (
        ('containers', ['ps', '-aq'], ['inspect']),
        ('networks', ['network', 'ls', '-q'], ['network', 'inspect']),
        ('volumes', ['volume', 'ls', '-q'], ['volume', 'inspect'])):
        ids = docker(query + ['--filter', 'label=com.docker.compose.project=' + project(plan)], context=context).split()
        need(len(ids) <= (2 if kind == 'containers' else 1), 'Unexpected project resources')
        rows = json.loads(docker(inspect + ids, context=context)) if ids else []
        for row in rows:
            labels = (row['Config']['Labels'] if kind == 'containers' else row['Labels']) or {}
            need(owner is not None and all(labels.get(k) == v for k, v in tags(plan, owner).items()), 'Foreign resource; no adoption or mutation')
            if kind == 'containers':
                role = labels.get('com.docker.compose.service')
                need(role in ('kuma', 'fixture') and role not in found[kind], 'Unexpected or duplicate service')
                need(row['Config']['Image'] == plan['image'], 'Image drift')
                host = row['HostConfig']
                need(host['ReadonlyRootfs'] and not host['Privileged'] and host['CapDrop'] == ['ALL'] and not host.get('CapAdd') and not host.get('Devices') and not host.get('DeviceRequests'), 'Privilege/device drift')
                need('no-new-privileges:true' in host['SecurityOpt'] and host['PidsLimit'] == 150, 'Security/process drift')
                need(host['Memory'] == (512 if role == 'kuma' else 64) * 1024**2 and host['NanoCpus'] == (1000000000 if role == 'kuma' else 250000000), 'Resource drift')
                need(host['RestartPolicy']['Name'] == 'unless-stopped' and host['LogConfig'] == {'Type': 'json-file', 'Config': {'max-size': '5m', 'max-file': '2'}}, 'Lifecycle/logging drift')
                expected_ports = {'3001/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(plan['port'])}]} if role == 'kuma' else {}
                need((host['PortBindings'] or {}) == expected_ports, 'Port binding drift')
                if role == 'kuma' and row['State']['Running']:
                    need(row['NetworkSettings']['Ports'].get('3001/tcp') == expected_ports['3001/tcp'], 'Requested port not actually published')
                need(set(row['NetworkSettings']['Networks']) == {project(plan) + '_default'}, 'Unexpected network')
                mounts = row['Mounts']
                volumes = [m for m in mounts if m['Type'] != 'tmpfs']
                if role == 'kuma':
                    need(len(volumes) == 1 and volumes[0]['Type'] == 'volume' and volumes[0]['Name'] == project(plan) + '_data' and volumes[0]['Destination'] == '/app/data' and volumes[0]['RW'], 'Data volume drift')
                    need(host.get('Tmpfs') == {'/tmp': 'rw,noexec,nosuid,size=64m'}, 'Temporary storage drift')
                    need(set(m['Destination'] for m in mounts) <= {'/app/data', '/tmp'}, 'Unexpected mount')
                    need('UPTIME_KUMA_DB_TYPE=sqlite' in row['Config']['Env'], 'Database mode drift')
                else:
                    need(not mounts and not host.get('Tmpfs') and row['Config']['Cmd'] == ['node', '-e', FIXTURE], 'Fixture specification drift')
                found[kind][role] = row
            elif kind == 'networks':
                need(row['Name'] == project(plan) + '_default' and not row['Internal'] and row['Driver'] == 'bridge', 'Network drift')
                need(set(row.get('Containers') or {}) <= {c['Id'] for c in found['containers'].values()}, 'Foreign network attachment')
                found[kind].append(row)
            else:
                need(row['Name'] == project(plan) + '_data' and row['Driver'] == 'local' and not row.get('Options'), 'Volume drift')
                attached = docker(['ps', '-aq', '--no-trunc', '--filter', 'volume=' + row['Name']], context=context).split()
                need(set(attached) <= {c['Id'] for c in found['containers'].values()}, 'Foreign volume attachment')
                found[kind].append(row)
    return found


def state_read(plan):
    root = Path(plan['root'])
    verify_private(root, directory=True)
    pending_guard(root)
    state = read_private(root / 'state.json')
    keys(state, {'kind', 'owner', 'plan_id', 'status', 'credential_hash'}, 'Kuma state')
    need(state['kind'] == 'kuma-owned-v1' and state['plan_id'] == plan['plan_id'], 'Ownership mismatch')
    need(isinstance(state['owner'], str) and re.fullmatch('[0-9a-f]{32}', state['owner']), 'Invalid owner')
    need(state['status'] in ('prepared', 'restore-copying', 'ready', 'running', 'stopped', 'removing', 'removed'), 'Invalid state')
    need(read_private(root / 'compose.json') == compose(plan, state['owner']), 'Compose modified; refusing execution')
    need(digest(read_private(root / 'credentials.json')) == state['credential_hash'], 'Credential drift; no implicit regeneration')
    return state


def prepare(plan):
    root = Path(plan['root'])
    if root.exists():
        return state_read(plan)
    inventory(plan, None)
    # Catch same-name resources without Compose labels before Compose can adopt them.
    context = plan['runtime']['context']
    for query, name in ((['network', 'ls', '--format', '{{.Name}}'], project(plan) + '_default'),
                        (['volume', 'ls', '--format', '{{.Name}}'], project(plan) + '_data')):
        need(name not in docker(query, context=context).splitlines(), 'Unowned resource name collision')
    port_free(plan['port'])
    image = json.loads(docker(['image', 'inspect', plan['image']], context=context))[0]
    need(image['Os'] == 'linux' and image['Architecture'] == 'amd64', 'Reviewed linux/amd64 image must be cached')
    create_private_directory(root)
    create_lock_file(root / 'operation.lock')
    credentials = (read_private(Path(plan['recovery']['path']) / 'credentials.json') if plan['recovery'] else
                   {'username': 'blueprint-admin', 'password': secrets.token_urlsafe(32)})
    state = {'kind': 'kuma-owned-v1', 'owner': uuid.uuid4().hex, 'plan_id': plan['plan_id'], 'status': 'prepared', 'credential_hash': digest(credentials)}
    atomic_json(root / 'credentials.json', credentials)
    atomic_json(root / 'compose.json', compose(plan, state['owner']))
    atomic_json(root / 'state.json', state)
    return state


def operate(plan, action, confirmation=None):
    validate_plan(plan)
    need(action in ('up', 'status', 'stop', 'remove', 'seed', 'inspect-monitors', 'fixture-down', 'fixture-up'), 'Unsupported Kuma action')
    if action not in ('status', 'inspect-monitors'):
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
        need(state['status'] != 'restore-copying', 'Interrupted restore copy; preserve evidence and use a fresh target')
        need(state['status'] != 'removed' or not containers and not resources['networks'], 'Resources reappeared after removal')
        if action == 'up':
            need(state['status'] not in ('removing', 'removed'), 'Removed deployments require a new recovery root')
            if not containers:
                need(state['status'] == 'prepared' and (not resources['volumes'] or plan['recovery'] is None), 'Recorded resources missing; no silent recreation')
                port_free(plan['port'])
                docker(['compose', '--project-name', project(plan), '--project-directory', str(root), '-f', str(root / 'compose.json'), 'create', '--pull', 'never', '--no-build'], context=context)
                resources = inventory(plan, state['owner'])
                containers = resources['containers']
            need(set(containers) == {'kuma', 'fixture'}, 'Incomplete service creation; retain state for review')
            if plan['recovery'] and state['status'] == 'prepared':
                need(not any(c['State']['Running'] for c in containers.values()), 'Recovery must target never-started containers')
                state['status'] = 'restore-copying'
                atomic_json(root / 'state.json', state, replace=True)
                docker(['cp', str(Path(plan['recovery']['path']) / 'data') + '/.', containers['kuma']['Id'] + ':/app/data/'], context=context)
                state['status'] = 'ready'
                atomic_json(root / 'state.json', state, replace=True)
            for role in ('fixture', 'kuma'):
                container = containers[role]
                need(not container['State'].get('Paused'), 'Paused container needs explicit review')
                if not container['State']['Running']:
                    if role == 'kuma':
                        port_free(plan['port'])
                    docker(['start', container['Id']], context=context)
            state['status'] = 'running'
        elif action == 'stop':
            need(bool(containers) and state['status'] not in ('removing', 'removed'), 'No owned deployment to stop')
            for container in containers.values():
                need(not container['State'].get('Paused'), 'Paused state requires review')
                if container['State']['Running']:
                    docker(['stop', '--time', '30', container['Id']], context=context)
            state['status'] = 'stopped'
        elif action == 'remove':
            need(not any(c['State']['Running'] for c in containers.values()), 'Stop all owned services before removal')
            if state['status'] != 'removed':
                state['status'] = 'removing'
                atomic_json(root / 'state.json', state, replace=True)
                for container in containers.values():
                    docker(['rm', container['Id']], context=context)
                for network in inventory(plan, state['owner'])['networks']:
                    docker(['network', 'rm', network['Id']], context=context)
                state['status'] = 'removed'  # Deliberately keep the data volume.
        elif action in ('fixture-up', 'fixture-down'):
            need(state['status'] == 'running' and set(containers) == {'kuma', 'fixture'} and containers['kuma']['State']['Running'], 'Fixture exercise requires a running owned deployment')
            container = containers['fixture']
            need(not container['State'].get('Paused'), 'Paused fixture needs review')
            if container['State']['Running'] != (action == 'fixture-up'):
                docker((['start'] if action == 'fixture-up' else ['stop', '--time', '10']) + [container['Id']], context=context)
        elif action in ('seed', 'inspect-monitors'):
            need(state['status'] == 'running' and set(containers) == {'kuma', 'fixture'} and containers['kuma']['State']['Running'], 'Kuma is not running')
            request = {**read_private(root / 'credentials.json'), 'action': action}
            return json.loads(docker(['exec', '-i', containers['kuma']['Id'], 'node', '-e', (MODULE / 'seed.cjs').read_text(encoding='utf-8')], context=context, input_text=json.dumps(request)))
        if action != 'status' and read_private(root / 'state.json') != state:
            atomic_json(root / 'state.json', state, replace=True)
        resources = inventory(plan, state['owner'])
        return {'module': 'uptime-kuma', 'state': state['status'], 'services': {role: c['State']['Status'] for role, c in resources['containers'].items()},
                'url': 'http://127.0.0.1:' + str(plan['port']), 'application_health': 'requires-application-verification', 'data_volume_retained': bool(resources['volumes'])}


def file_hash(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def tree_files(root, *, protect_new=False):
    verify_private(root, directory=True)
    result = {}
    for path in sorted(root.rglob('*')):
        safe_path(path)
        info = path.stat()
        need(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), 'Unexpected backup resource')
        need(path.is_dir() or info.st_nlink == 1, 'Hard-linked backup files refused')
        if protect_new:  # Only exclusively created snapshot output, never existing user data.
            if os.name == 'nt':
                windows_acl(path, create=True)
            else:
                path.chmod(0o700 if path.is_dir() else 0o600)
        verify_private(path, directory=path.is_dir())
        if path.is_file():
            result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def database_summary(data):
    try:
        return _database_summary(data)
    except sqlite3.Error as error:
        raise ConfigError('SQLite snapshot cannot be validated; retain private evidence') from error


def _database_summary(data):
    db = data / 'kuma.db'
    need(db.is_file(), 'Snapshot has no Kuma database')
    # Read-only connection; backup is taken only after both containers stop.
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as connection:
        need(connection.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'SQLite integrity check failed')
        monitors = connection.execute('SELECT name,type,url FROM monitor ORDER BY name').fetchall()
        need(monitors == [('Blueprint fixture', 'http', 'http://fixture:8080'), ('Blueprint self-check', 'http', 'http://127.0.0.1:3001')], 'This milestone restores only the synthetic monitor set')
        need(connection.execute('SELECT COUNT(*) FROM notification').fetchone()[0] == 0, 'Notifications are outside isolated recovery scope')
        need(connection.execute('SELECT username FROM user').fetchall() == [('blueprint-admin',)], 'Unexpected account set')
        need(connection.execute('SELECT slug FROM status_page').fetchall() == [('blueprint',)], 'Unexpected status page set')
        beats = connection.execute('SELECT status,COUNT(*) FROM heartbeat GROUP BY status ORDER BY status').fetchall()
        need(sum(row[1] for row in beats) > 0, 'Nonempty heartbeat history required')
        return {'monitor_count': len(monitors), 'user_count': 1, 'status_page_count': 1, 'heartbeats': {str(s): n for s, n in beats}}


def verify_backup(root):
    root = safe_path(root)
    verify_private(root, directory=True)
    manifest = read_private(root / 'manifest.json')
    keys(manifest, {'kind', 'image', 'files', 'credential_hash', 'summary'}, 'Kuma backup manifest')
    need(manifest['kind'] == 'kuma-stopped-backup-v1' and manifest['image'] == load_json(MODULE / 'image.json')['image'], 'Backup image/format mismatch')
    need(tree_files(root / 'data') == manifest['files'], 'Backup content checksum mismatch')
    need(digest(read_private(root / 'credentials.json')) == manifest['credential_hash'], 'Backup credential mismatch')
    need(database_summary(root / 'data') == manifest['summary'], 'Backup content evidence mismatch')
    return manifest


def backup(plan, destination, confirmation):
    validate_plan(plan)
    need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    destination = safe_path(destination)
    need(not destination.is_relative_to(root) and not root.is_relative_to(destination), 'Backup and installation must not overlap')
    need(not destination.exists() and destination.parent.is_dir(), 'Backup requires an absent destination under an existing parent')
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        need(state['status'] == 'stopped' and set(resources['containers']) == {'kuma', 'fixture'} and not any(c['State']['Running'] for c in resources['containers'].values()), 'Stop both owned services before backup')
        create_private_directory(destination)
        create_private_directory(destination / 'data')
        docker(['cp', resources['containers']['kuma']['Id'] + ':/app/data/.', str(destination / 'data')], context=plan['runtime']['context'])
        tree_files(destination / 'data', protect_new=True)
        summary = database_summary(destination / 'data')
        credentials = read_private(root / 'credentials.json')
        atomic_json(destination / 'credentials.json', credentials)
        atomic_json(destination / 'manifest.json', {'kind': 'kuma-stopped-backup-v1', 'image': plan['image'],
                    'files': tree_files(destination / 'data'), 'credential_hash': digest(credentials), 'summary': summary})
        verify_backup(destination)
        return {'backup_complete': True, 'encrypted': False, 'contains_credentials': True, 'summary': summary,
                'recovery_verified': False, 'note': 'Restore into a fresh project and verify rendered content before considering recovery tested'}
