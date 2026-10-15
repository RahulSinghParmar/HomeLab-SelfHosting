"""Bounded upstream Beszel trial. Never adopts a production hub or native agent."""
from contextlib import closing
import json
from pathlib import Path
import re
import secrets
import sqlite3
import urllib.error
import urllib.request
import uuid

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .doctor import host_platform
from .glance import docker, local_runtime, port_free
from .kuma import tree_files
from .privatefs import (atomic_json, create_lock_file, create_private_directory,
                        operation_lock, read_private, safe_path, verify_private)
from .sandbox import digest, pending_guard

MODULE = ROOT / 'modules/beszel'
EMAIL = 'admin@example.invalid'
SYSTEM = 'Blueprint Docker agent'
TARGETS = {'hub': '/beszel_data', 'agent': '/var/lib/beszel-agent'}


def make_plan(root, port, runtime, backup=None):
    root = safe_path(Path(root))
    need(root.parent.is_dir() and '$' not in str(root), 'Choose an absent installation under an existing local parent without interpolation characters')
    need(type(port) is int and 1024 <= port <= 65535, 'Choose an unprivileged TCP port')
    keys(runtime, {'context', 'endpoint', 'engine_id'}, 'local runtime')
    recovery = None
    if backup is not None:
        source = safe_path(Path(backup))
        need(not source.is_relative_to(root) and not root.is_relative_to(source), 'Backup and installation must not overlap')
        recovery = {'path': str(source), 'manifest_id': digest(verify_backup(source))}
    images = load_json(MODULE / 'image.json')
    plan = {'kind': 'homelab-beszel-plan', 'contract': 'beszel-isolated-v1', 'platform': host_platform(),
            'root': str(root), 'port': port, 'runtime': runtime, 'recovery': recovery,
            'images': {role: images[role] for role in TARGETS},
            'limits': {'hub_memory_mib': 256, 'agent_memory_mib': 128, 'cpus_per_service': 0.5},
            'access': 'loopback', 'network': 'dedicated-bridge-outbound-allowed',
            'docker_socket': False, 'metrics_scope': 'docker-linux-view-not-native-host'}
    plan['plan_id'] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'root', 'port', 'runtime', 'images', 'recovery', 'limits', 'access', 'network', 'docker_socket', 'metrics_scope', 'plan_id'}, 'Beszel plan')
    backup = plan['recovery']['path'] if plan['recovery'] is not None else None
    need(canonical(plan) == canonical(make_plan(plan['root'], plan['port'], plan['runtime'], backup)), 'Plan/image/recovery drift; review a new plan')
    return plan


def project(plan):
    return 'hl-beszel-' + plan['plan_id'][:16]


def tags(plan, owner):
    return {'org.homelab.owner': owner, 'org.homelab.plan': plan['plan_id'], 'org.homelab.module': 'beszel'}


def valid_key(value):
    need(isinstance(value, str) and re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]{68}(?: [a-zA-Z0-9@._-]+)?', value), 'Unexpected hub public key format')
    return value


def compose(plan, owner, public_key=None):
    if public_key is not None:
        valid_key(public_key)
    common = {'labels': tags(plan, owner), 'pull_policy': 'never', 'restart': 'unless-stopped',
              'read_only': True, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
              'pids_limit': 100, 'cpus': 0.5, 'tmpfs': ['/tmp:rw,noexec,nosuid,size=32m'],
              'logging': {'driver': 'json-file', 'options': {'max-size': '5m', 'max-file': '2'}}}
    services = {}
    for role in (TARGETS if public_key else ('hub',)):
        services[role] = {**common, 'image': plan['images'][role], 'mem_limit': '256m' if role == 'hub' else '128m',
                          'volumes': [{'type': 'volume', 'source': role + '-data', 'target': TARGETS[role], 'volume': {'nocopy': True}}]}
    services['hub'].update({'environment': {'APP_URL': 'http://127.0.0.1:' + str(plan['port']),
        'CHECK_UPDATES': 'false', 'USER_CREATION': 'false', 'CONTAINER_DETAILS': 'false', 'SYNC_SYSTEM_NAMES': 'false'},
        'ports': [{'target': 8090, 'published': str(plan['port']), 'host_ip': '127.0.0.1', 'protocol': 'tcp'}]})
    if public_key:
        services['agent']['environment'] = {'KEY': public_key, 'LISTEN': '45876'}
    return {'services': services,
            'volumes': {role + '-data': {'labels': tags(plan, owner)} for role in services},
            'networks': {'default': {'driver': 'bridge', 'labels': tags(plan, owner)}}}


def inventory(plan, owner, public_key=None):
    context = plan['runtime']['context']
    found = {'containers': {}, 'networks': [], 'volumes': []}
    spec = compose(plan, owner, public_key)['services']
    for kind, query, inspect in (
        ('containers', ['ps', '-aq'], ['inspect']),
        ('networks', ['network', 'ls', '-q'], ['network', 'inspect']),
        ('volumes', ['volume', 'ls', '-q'], ['volume', 'inspect'])):
        ids = docker(query + ['--filter', 'label=com.docker.compose.project=' + project(plan)], context=context).split()
        need(len(ids) <= (1 if kind == 'networks' else 2), 'Unexpected project resources')
        rows = json.loads(docker(inspect + ids, context=context)) if ids else []
        for row in rows:
            labels = (row['Config']['Labels'] if kind == 'containers' else row['Labels']) or {}
            need(owner is not None and all(labels.get(k) == v for k, v in tags(plan, owner).items()), 'Foreign resource; no adoption or mutation')
            if kind == 'containers':
                role = labels.get('com.docker.compose.service')
                need(role in spec and role not in found[kind], 'Unexpected or duplicate service')
                need(row['Config']['Image'] == plan['images'][role], 'Image drift')
                host = row['HostConfig']
                need(host['ReadonlyRootfs'] and not host['Privileged'] and host['CapDrop'] == ['ALL'] and not host.get('CapAdd') and not host.get('Devices') and not host.get('DeviceRequests'), 'Privilege/device drift')
                need(not host.get('PidMode') and not host.get('IpcMode') == 'host' and not host.get('UTSMode'), 'Host namespace drift')
                need('no-new-privileges:true' in host['SecurityOpt'] and host['PidsLimit'] == 100, 'Security/process drift')
                need(host['Memory'] == (256 if role == 'hub' else 128) * 1024**2 and host['NanoCpus'] == 500000000, 'Resource drift')
                need(host['RestartPolicy']['Name'] == 'unless-stopped' and host['LogConfig'] == {'Type': 'json-file', 'Config': {'max-size': '5m', 'max-file': '2'}}, 'Lifecycle/logging drift')
                ports = {'8090/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(plan['port'])}]} if role == 'hub' else {}
                need((host['PortBindings'] or {}) == ports, 'Port binding drift')
                if role == 'hub' and row['State']['Running']:
                    need(row['NetworkSettings']['Ports'].get('8090/tcp') == ports['8090/tcp'], 'Requested port not actually published')
                need(set(row['NetworkSettings']['Networks']) == {project(plan) + '_default'}, 'Unexpected network')
                mounts = [m for m in row['Mounts'] if m['Type'] != 'tmpfs']
                need(len(mounts) == 1 and mounts[0]['Type'] == 'volume' and mounts[0]['Name'] == project(plan) + '_' + role + '-data' and mounts[0]['Destination'] == TARGETS[role] and mounts[0]['RW'], 'Data volume drift')
                need(host.get('Tmpfs') == {'/tmp': 'rw,noexec,nosuid,size=32m'}, 'Temporary storage drift')
                need(set(m['Destination'] for m in row['Mounts']) <= {TARGETS[role], '/tmp'}, 'Unexpected mount')
                env = dict(e.split('=', 1) for e in row['Config']['Env'])
                need(all(env.get(k) == v for k, v in spec[role]['environment'].items()) and set(env) <= set(spec[role]['environment']) | {'PATH'}, 'Environment drift')
                need(row['Config']['Entrypoint'] == (['/beszel'] if role == 'hub' else ['/agent']) and row['Config']['Cmd'] == (['serve', '--http=0.0.0.0:8090'] if role == 'hub' else None), 'Process drift')
                found[kind][role] = row
            elif kind == 'networks':
                need(row['Name'] == project(plan) + '_default' and not row['Internal'] and row['Driver'] == 'bridge', 'Network drift')
                need(set(row.get('Containers') or {}) <= {c['Id'] for c in found['containers'].values()}, 'Foreign network attachment')
                found[kind].append(row)
            else:
                need(row['Name'] in {project(plan) + '_' + role + '-data' for role in spec} and row['Driver'] == 'local' and not row.get('Options'), 'Volume drift')
                attached = docker(['ps', '-aq', '--no-trunc', '--filter', 'volume=' + row['Name']], context=context).split()
                need(set(attached) <= {c['Id'] for c in found['containers'].values()}, 'Foreign volume attachment')
                found[kind].append(row)
    return found


def state_read(plan):
    root = Path(plan['root'])
    verify_private(root, directory=True)
    pending_guard(root)
    state = read_private(root / 'state.json')
    keys(state, {'kind', 'owner', 'plan_id', 'status', 'credential_hash', 'public_key'}, 'Beszel state')
    need(state['kind'] == 'beszel-owned-v1' and state['plan_id'] == plan['plan_id'], 'Ownership mismatch')
    need(isinstance(state['owner'], str) and re.fullmatch('[0-9a-f]{32}', state['owner']), 'Invalid owner')
    need(state['status'] in ('prepared', 'restore-copying', 'ready', 'running', 'pairing', 'stopped', 'removing', 'removed'), 'Invalid state')
    need(read_private(root / 'compose.json') == compose(plan, state['owner'], state['public_key']), 'Compose modified or interrupted pairing; preserve state for review')
    need(digest(read_private(root / 'credentials.json')) == state['credential_hash'], 'Credential drift; no implicit regeneration')
    return state


def prepare(plan):
    root = Path(plan['root'])
    if root.exists():
        return state_read(plan)
    inventory(plan, None)
    context = plan['runtime']['context']
    for query, names in ((['network', 'ls', '--format', '{{.Name}}'], {project(plan) + '_default'}),
                         (['volume', 'ls', '--format', '{{.Name}}'], {project(plan) + '_' + r + '-data' for r in TARGETS})):
        need(not names.intersection(docker(query, context=context).splitlines()), 'Unowned resource name collision')
    port_free(plan['port'])
    for image_ref in plan['images'].values():
        image = json.loads(docker(['image', 'inspect', image_ref], context=context))[0]
        need(image['Os'] == 'linux' and image['Architecture'] == 'amd64', 'Reviewed linux/amd64 images must be cached')
    create_private_directory(root)
    create_lock_file(root / 'operation.lock')
    credentials = (read_private(Path(plan['recovery']['path']) / 'credentials.json') if plan['recovery'] else
                   {'email': EMAIL, 'password': secrets.token_urlsafe(32)})
    public_key = verify_backup(Path(plan['recovery']['path']))['public_key'] if plan['recovery'] else None
    state = {'kind': 'beszel-owned-v1', 'owner': uuid.uuid4().hex, 'plan_id': plan['plan_id'], 'status': 'prepared', 'credential_hash': digest(credentials), 'public_key': public_key}
    atomic_json(root / 'credentials.json', credentials)
    atomic_json(root / 'compose.json', compose(plan, state['owner'], public_key))
    atomic_json(root / 'state.json', state)
    return state


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ConfigError('Local API redirected; refusing credential forwarding')


def api(plan, path, body=None, token=None):
    """Only called after ownership and effective loopback binding checks. No proxies."""
    need(path.startswith('/api/') and not any(c in path for c in '\r\n#'), 'Invalid API path')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = token
    request = urllib.request.Request('http://127.0.0.1:' + str(plan['port']) + path,
        data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            need(len(raw) <= 2 * 1024 * 1024, 'Oversized local API response')
            return json.loads(raw)
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise ConfigError('Beszel local API failed; retain private logs and retry after checking readiness') from error


def login(plan, credentials):
    result = api(plan, '/api/collections/users/auth-with-password', {'identity': credentials['email'], 'password': credentials['password']})
    need(result['record']['email'] == EMAIL and result['record']['role'] == 'admin', 'Unexpected application identity')
    return result['token'], result['record']['id']


def systems(plan, token, user_id):
    result = api(plan, '/api/collections/systems/records?perPage=2', token=token)
    need(result['totalItems'] <= 1 and len(result['items']) == result['totalItems'], 'Unexpected system set; no adoption')
    for row in result['items']:
        need(row['name'] == SYSTEM and row['host'] == 'agent' and row['port'] == '45876' and row['users'] == [user_id], 'Unexpected system configuration')
    return result['items']


def metrics(plan, token, user_id):
    rows = systems(plan, token, user_id)
    need(len(rows) == 1, 'Pair the synthetic agent first')
    stats = api(plan, '/api/collections/system_stats/records?perPage=1&sort=-created', token=token)
    latest = stats['items'][0] if stats['items'] else None
    if latest:
        need(latest['system'] == rows[0]['id'], 'Foreign metric history')
    # Do not print detailed hardware identifiers, session tokens or raw API records.
    return {'system_count': 1, 'status': rows[0]['status'], 'history_count': stats['totalItems'],
            'latest_record_id': latest['id'] if latest else None, 'latest_record_time': latest['created'] if latest else None,
            'metric_fields': sorted(latest['stats']) if latest else [],
            'scope': plan['metrics_scope'], 'gpu': 'not-exposed', 'native_services': 'not-exposed'}


def create_services(plan, roles):
    docker(['compose', '--project-name', project(plan), '--project-directory', plan['root'], '-f', str(Path(plan['root']) / 'compose.json'), 'create', '--pull', 'never', '--no-build', *roles], context=plan['runtime']['context'])


def operate(plan, action, confirmation=None):
    validate_plan(plan)
    need(action in ('up', 'status', 'stop', 'remove', 'seed', 'inspect-metrics', 'agent-down', 'agent-up'), 'Unsupported Beszel action')
    if action not in ('status', 'inspect-metrics'):
        need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    if action == 'up':
        prepare(plan)
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'], state['public_key'])
        containers = resources['containers']
        context = plan['runtime']['context']
        need(state['status'] != 'restore-copying', 'Interrupted restore copy; preserve evidence and use a fresh target')
        need(not any(c['State'].get('Paused') for c in containers.values()), 'Paused container needs explicit review')
        need(state['status'] != 'removed' or not containers and not resources['networks'], 'Resources reappeared after removal')
        if action == 'up':
            need(state['status'] not in ('pairing', 'removing', 'removed'), 'Finish pairing with seed or use a new recovery root')
            expected = set(TARGETS) if state['public_key'] else {'hub'}
            if not containers:
                need(state['status'] == 'prepared' and not resources['volumes'], 'Recorded resources missing; no silent recreation')
                port_free(plan['port'])
                create_services(plan, sorted(expected))
                containers = inventory(plan, state['owner'], state['public_key'])['containers']
            need(set(containers) == expected, 'Incomplete service creation; retain state for review')
            if plan['recovery'] and state['status'] == 'prepared':
                need(not any(c['State']['Running'] or c['State']['Status'] != 'created' for c in containers.values()), 'Recovery must target never-started containers')
                state['status'] = 'restore-copying'
                atomic_json(root / 'state.json', state, replace=True)
                for role in TARGETS:
                    docker(['cp', str(Path(plan['recovery']['path']) / role) + '/.', containers[role]['Id'] + ':' + TARGETS[role] + '/'], context=context)
                state['status'] = 'ready'
                atomic_json(root / 'state.json', state, replace=True)
            for role, container in containers.items():
                if not container['State']['Running']:
                    if role == 'hub':
                        port_free(plan['port'])
                    docker(['start', container['Id']], context=context)
            state['status'] = 'running'
        elif action == 'stop':
            need(bool(containers) and state['status'] not in ('removing', 'removed'), 'No owned deployment to stop')
            for container in containers.values():
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
                for network in inventory(plan, state['owner'], state['public_key'])['networks']:
                    docker(['network', 'rm', network['Id']], context=context)
                state['status'] = 'removed'  # Retain both volumes and private recovery artifacts.
        elif action in ('agent-up', 'agent-down'):
            need(state['status'] == 'running' and set(containers) == set(TARGETS) and containers['hub']['State']['Running'], 'Agent exercise requires a running paired deployment')
            container = containers['agent']
            if container['State']['Running'] != (action == 'agent-up'):
                docker((['start'] if action == 'agent-up' else ['stop', '--time', '10']) + [container['Id']], context=context)
        elif action in ('seed', 'inspect-metrics'):
            need(state['status'] in ('running', 'pairing') and 'hub' in containers and containers['hub']['State']['Running'], 'Hub is not running')
            credentials = read_private(root / 'credentials.json')
            if action == 'seed' and api(plan, '/api/beszel/first-run')['firstRun']:
                need(state['public_key'] is None and not plan['recovery'], 'Restored hub unexpectedly empty')
                api(plan, '/api/beszel/create-user', credentials)
            token, user_id = login(plan, credentials)
            if action == 'inspect-metrics':
                return metrics(plan, token, user_id)
            public_key = valid_key(api(plan, '/api/beszel/info', token=token)['key'].strip())
            need(state['public_key'] is None or state['public_key'] == public_key, 'Hub key changed; refusing re-pair')
            if not systems(plan, token, user_id):
                need(state['public_key'] is None and not plan['recovery'], 'Recorded system missing; no silent recreation')
                api(plan, '/api/collections/systems/records', {'name': SYSTEM, 'host': 'agent', 'port': '45876', 'users': [user_id]}, token)
            if state['public_key'] is None:
                state.update(public_key=public_key, status='pairing')
                # A crash between these two private writes fails closed in state_read.
                atomic_json(root / 'compose.json', compose(plan, state['owner'], public_key), replace=True)
                atomic_json(root / 'state.json', state, replace=True)
            if 'agent' not in containers:
                need(state['status'] == 'pairing', 'Recorded agent missing; refusing replacement')
                need(project(plan) + '_agent-data' not in docker(['volume', 'ls', '--format', '{{.Name}}'], context=context).splitlines(), 'Agent volume exists without its container; review interrupted creation')
                create_services(plan, ['agent'])
            containers = inventory(plan, state['owner'], public_key)['containers']
            need(set(containers) == set(TARGETS), 'Incomplete paired deployment')
            if not containers['agent']['State']['Running']:
                docker(['start', containers['agent']['Id']], context=context)
            state['status'] = 'running'
        if action != 'status' and read_private(root / 'state.json') != state:
            atomic_json(root / 'state.json', state, replace=True)
        resources = inventory(plan, state['owner'], state['public_key'])
        return {'module': 'beszel', 'state': state['status'], 'paired': state['public_key'] is not None,
                'services': {role: c['State']['Status'] for role, c in resources['containers'].items()},
                'url': 'http://127.0.0.1:' + str(plan['port']), 'application_health': 'requires-application-verification',
                'retained_data_volumes': len(resources['volumes']), 'metrics_scope': plan['metrics_scope']}


def database_summary(data):
    try:
        db = data / 'data.db'
        need(db.is_file(), 'Snapshot has no hub database')
        # A stopped, copied, checkpointed database may be opened immutable.
        # mode=ro alone can create -wal/-shm files and mutate a hashed snapshot.
        # Never ignore pending WAL/journal transactions to obtain a passing check.
        for database in data.glob('*.db'):
            for suffix in ('-wal', '-journal'):
                sidecar = database.with_name(database.name + suffix)
                need(not sidecar.exists() or sidecar.stat().st_size == 0,
                     'Uncheckpointed snapshot; preserve it and investigate shutdown before retrying')
        with closing(sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True)) as connection:
            need(connection.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'SQLite integrity check failed')
            users = connection.execute('SELECT id,email,role FROM users').fetchall()
            need(len(users) == 1 and users[0][1:] == (EMAIL, 'admin'), 'Unexpected account set')
            need(connection.execute('SELECT email FROM _superusers').fetchall() == [(EMAIL,)], 'Unexpected superuser set')
            systems_rows = connection.execute('SELECT id,name,host,port,users FROM systems').fetchall()
            need(len(systems_rows) == 1 and systems_rows[0][1:4] == (SYSTEM, 'agent', '45876') and json.loads(systems_rows[0][4]) == [users[0][0]], 'Unexpected system set')
            need(connection.execute('SELECT COUNT(*) FROM alerts').fetchone()[0] == 0, 'Alert configuration outside trial scope')
            records = connection.execute('SELECT id,system,stats,created FROM system_stats ORDER BY id').fetchall()
            need(bool(records) and all(r[1] == systems_rows[0][0] and isinstance(json.loads(r[2]), dict) for r in records), 'Nonempty owned metric history required')
            return {'system_id': systems_rows[0][0], 'user_id': users[0][0], 'history_count': len(records), 'history_digest': digest(records)}
    except sqlite3.Error as error:
        raise ConfigError('SQLite snapshot cannot be validated; retain private evidence') from error


def verify_backup(root):
    root = safe_path(root)
    verify_private(root, directory=True)
    manifest = read_private(root / 'manifest.json')
    keys(manifest, {'kind', 'images', 'files', 'credential_hash', 'public_key', 'summary'}, 'Beszel backup manifest')
    images = load_json(MODULE / 'image.json')
    need(manifest['kind'] == 'beszel-stopped-backup-v1' and manifest['images'] == {r: images[r] for r in TARGETS}, 'Backup image/format mismatch')
    valid_key(manifest['public_key'])
    need({role: tree_files(root / role) for role in TARGETS} == manifest['files'], 'Backup content checksum mismatch')
    need(digest(read_private(root / 'credentials.json')) == manifest['credential_hash'], 'Backup credential mismatch')
    need(database_summary(root / 'hub') == manifest['summary'], 'Backup content evidence mismatch')
    need((root / 'hub/id_ed25519').is_file(), 'Hub identity missing from snapshot')
    return manifest


def backup(plan, destination, confirmation):
    validate_plan(plan)
    need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root, destination = Path(plan['root']), safe_path(destination)
    need(not destination.is_relative_to(root) and not root.is_relative_to(destination), 'Backup and installation must not overlap')
    need(not destination.exists() and destination.parent.is_dir(), 'Backup requires an absent destination under an existing parent')
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'], state['public_key'])
        need(state['status'] == 'stopped' and state['public_key'] and set(resources['containers']) == set(TARGETS) and not any(c['State']['Running'] for c in resources['containers'].values()), 'Stop both owned services before backup')
        create_private_directory(destination)
        files = {}
        for role, target in TARGETS.items():
            create_private_directory(destination / role)
            docker(['cp', resources['containers'][role]['Id'] + ':' + target + '/.', str(destination / role)], context=plan['runtime']['context'])
            files[role] = tree_files(destination / role, protect_new=True)
        summary = database_summary(destination / 'hub')
        credentials = read_private(root / 'credentials.json')
        atomic_json(destination / 'credentials.json', credentials)
        atomic_json(destination / 'manifest.json', {'kind': 'beszel-stopped-backup-v1', 'images': plan['images'], 'files': files,
                    'credential_hash': digest(credentials), 'public_key': state['public_key'], 'summary': summary})
        verify_backup(destination)
        return {'backup_complete': True, 'encrypted': False, 'contains_credentials': True, 'summary': summary,
                'recovery_verified': False, 'note': 'Restore into a fresh project and verify content before considering recovery tested'}
