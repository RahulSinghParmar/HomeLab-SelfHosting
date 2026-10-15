"""Isolated Portainer lifecycle with explicitly granted nested Docker control."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import time
import urllib.error
import urllib.request
import uuid

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .doctor import host_platform
from .glance import docker, local_runtime, port_free
from .privatefs import (atomic_json, create_lock_file, create_private_directory,
                        operation_lock, read_private, safe_path, verify_private, windows_acl)
from .sandbox import digest, pending_guard


MODULE = ROOT / 'modules/portainer'
GRANT = 'isolated-engine-only'
PORTAINER_MEMORY_MIB = 256
PORTAINER_CPUS = 0.5
PORTAINER_PIDS = 128
ENGINE_MEMORY_MIB = 512
ENGINE_CPUS = 1
ENGINE_PIDS = 256
PROBE_NETWORK = 'homelab-portainer-control-probe'


def make_plan(root, port, runtime, grant, backup=None):
    root = safe_path(Path(root))
    need(root.parent.is_dir() and '$' not in str(root),
         'Choose an absent installation under an existing local parent without interpolation characters')
    need(type(port) is int and 1024 <= port <= 65535, 'Choose an unprivileged TCP port')
    keys(runtime, {'context', 'endpoint', 'engine_id'}, 'local runtime')
    need(grant == GRANT,
         'Portainer requires the exact isolated-engine-only Docker-control grant')
    images = load_json(MODULE / 'images.json')
    recovery = None
    if backup is not None:
        source = safe_path(Path(backup))
        need(not source.is_relative_to(root) and not root.is_relative_to(source),
             'Backup and installation must not overlap')
        manifest = verify_backup(source)
        recovery = {'path': str(source), 'manifest_id': digest(manifest)}
    plan = {
        'kind': 'homelab-portainer-plan', 'contract': 'portainer-isolated-control-v4',
        'platform': host_platform(), 'root': str(root), 'port': port, 'runtime': runtime,
        'images': {'portainer': images['portainer_image'], 'engine': images['engine_image']},
        'recovery': recovery,
        'permission': {'grant': GRANT, 'docker_control': 'isolated-nested-engine',
                       'host_engine_access': False, 'privileged_sidecar': True},
        'limits': {
            'portainer': {'memory_mib': PORTAINER_MEMORY_MIB, 'cpus': PORTAINER_CPUS,
                          'pids': PORTAINER_PIDS},
            'engine': {'memory_mib': ENGINE_MEMORY_MIB, 'cpus': ENGINE_CPUS,
                       'pids': ENGINE_PIDS, 'storage': 'ephemeral-tmpfs'},
        },
        'access': 'loopback-https-self-signed',
        'network': 'published-frontend-plus-internal-control',
        'host_docker_socket': False,
    }
    plan['plan_id'] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'root', 'port', 'runtime', 'images', 'recovery',
                'permission', 'limits', 'access', 'network', 'host_docker_socket', 'plan_id'},
         'Portainer plan')
    backup = plan['recovery']['path'] if plan['recovery'] is not None else None
    need(canonical(plan) == canonical(make_plan(plan['root'], plan['port'], plan['runtime'], GRANT, backup)),
         'Plan/image/permission/recovery drift; review a new plan')
    return plan


def project(plan):
    return 'hl-portainer-' + plan['plan_id'][:16]


def tags(plan, owner):
    return {'org.homelab.owner': owner, 'org.homelab.plan': plan['plan_id'],
            'org.homelab.module': 'portainer'}


def portainer_command(plan):
    return [
        '--admin-password-file=/run/secrets/portainer_admin_password',
        '--secret-key-name=portainer',
        '--host=tcp://engine:2375', '--http-disabled', '--no-edge-compute',
        '--csp',
    ]


def engine_command():
    return [
        '--host=tcp://0.0.0.0:2375', '--host=unix:///var/run/docker.sock',
        '--tls=false', '--storage-driver=vfs',
    ]


def engine_healthcheck():
    return {
        'Test': ['CMD', 'docker', '--host=tcp://127.0.0.1:2375', 'info'],
        'Interval': 5_000_000_000, 'Timeout': 3_000_000_000,
        'StartPeriod': 30_000_000_000, 'Retries': 12,
    }


def compose(plan, owner):
    labels = tags(plan, owner)
    root = Path(plan['root'])
    portainer = {
        'image': plan['images']['portainer'], 'labels': labels, 'pull_policy': 'never',
        'command': portainer_command(plan), 'restart': 'unless-stopped',
        'depends_on': {'engine': {'condition': 'service_healthy'}},
        'ports': [{'target': 9443, 'published': str(plan['port']),
                   'host_ip': '127.0.0.1', 'protocol': 'tcp'}],
        'volumes': [{'type': 'volume', 'source': 'data', 'target': '/data'}],
        'secrets': [
            {'source': 'admin_password', 'target': 'portainer_admin_password', 'mode': 0o400},
            {'source': 'encryption_key', 'target': 'portainer', 'mode': 0o400},
        ],
        'networks': ['frontend', 'control'], 'read_only': True, 'cap_drop': ['ALL'],
        'security_opt': ['no-new-privileges:true'], 'tmpfs': ['/tmp:rw,noexec,nosuid,size=64m'],
        'mem_limit': f'{PORTAINER_MEMORY_MIB}m', 'cpus': PORTAINER_CPUS,
        'pids_limit': PORTAINER_PIDS,
        'logging': {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '2'}},
    }
    engine = {
        'image': plan['images']['engine'], 'labels': labels, 'pull_policy': 'never',
        'command': engine_command(),
        'restart': 'unless-stopped', 'privileged': True,
        'environment': {'DOCKER_TLS_CERTDIR': ''}, 'networks': ['control'],
        'expose': ['2375'],
        'tmpfs': ['/var/lib/docker:rw,nosuid,size=1024m', '/var/run:rw,nosuid,size=64m',
                  '/tmp:rw,noexec,nosuid,size=64m'],
        'mem_limit': f'{ENGINE_MEMORY_MIB}m', 'cpus': ENGINE_CPUS, 'pids_limit': ENGINE_PIDS,
        'healthcheck': {'test': engine_healthcheck()['Test'], 'interval': '5s', 'timeout': '3s',
                        'start_period': '30s', 'retries': 12},
        'logging': {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '2'}},
    }
    return {
        'services': {'portainer': portainer, 'engine': engine},
        'volumes': {'data': {'labels': labels}},
        'networks': {
            'frontend': {'driver': 'bridge', 'internal': False, 'labels': labels},
            'control': {'driver': 'bridge', 'internal': True, 'labels': labels},
        },
        'secrets': {
            'admin_password': {'file': str(root / 'admin-password.txt')},
            'encryption_key': {'file': str(root / 'encryption-key.txt')},
        },
    }


def expected_portainer_tmpfs():
    return {'/tmp': 'rw,noexec,nosuid,size=64m'}


def expected_engine_tmpfs():
    return {'/tmp': 'rw,noexec,nosuid,size=64m',
            '/var/lib/docker': 'rw,nosuid,size=1024m',
            '/var/run': 'rw,nosuid,size=64m'}


def inventory(plan, owner):
    context = plan['runtime']['context']
    found = {'containers': {}, 'networks': [], 'volumes': []}
    for kind, query, inspect in (
        ('containers', ['ps', '-aq'], ['inspect']),
        ('networks', ['network', 'ls', '-q'], ['network', 'inspect']),
        ('volumes', ['volume', 'ls', '-q'], ['volume', 'inspect'])):
        ids = docker(query + ['--filter', 'label=com.docker.compose.project=' + project(plan)],
                     context=context).split()
        limit = 2 if kind in ('containers', 'networks') else 1
        need(len(ids) <= limit, 'Unexpected Portainer project resources')
        rows = json.loads(docker(inspect + ids, context=context)) if ids else []
        for row in rows:
            labels = (row['Config']['Labels'] if kind == 'containers' else row['Labels']) or {}
            need(owner is not None and all(labels.get(key) == value for key, value in tags(plan, owner).items()),
                 'Foreign resource; no adoption or mutation')
            if kind == 'containers':
                role = labels.get('com.docker.compose.service')
                need(role in ('portainer', 'engine') and role not in found[kind],
                     'Unexpected or duplicate service')
                need(row['Config']['Image'] == plan['images'][role], 'Image drift')
                host = row['HostConfig']
                need(host['RestartPolicy']['Name'] == 'unless-stopped'
                     and host['LogConfig'] == {'Type': 'json-file',
                                               'Config': {'max-size': '10m', 'max-file': '2'}},
                     'Lifecycle/logging drift')
                need(not host.get('Devices') and not host.get('DeviceRequests'), 'Device drift')
                if role == 'portainer':
                    need(host['ReadonlyRootfs'] and not host['Privileged'] and host['CapDrop'] == ['ALL']
                         and not host.get('CapAdd') and 'no-new-privileges:true' in host['SecurityOpt'],
                         'Portainer privilege drift')
                    need(host['Memory'] == PORTAINER_MEMORY_MIB * 1024**2
                         and host['NanoCpus'] == int(PORTAINER_CPUS * 1_000_000_000)
                         and host['PidsLimit'] == PORTAINER_PIDS, 'Portainer resource drift')
                    expected_ports = {'9443/tcp': [{'HostIp': '127.0.0.1',
                                                    'HostPort': str(plan['port'])}]}
                    need((host['PortBindings'] or {}) == expected_ports, 'Portainer binding drift')
                    if row['State']['Running']:
                        need(row['NetworkSettings']['Ports'].get('9443/tcp') == expected_ports['9443/tcp'],
                             'Requested HTTPS port not actually published')
                    need(host.get('Tmpfs') == expected_portainer_tmpfs(), 'Portainer tmpfs drift')
                    need(row['Config'].get('Cmd') == portainer_command(plan), 'Portainer command drift')
                    need(set(row['NetworkSettings']['Networks']) == {
                        project(plan) + '_frontend', project(plan) + '_control'},
                        'Portainer network drift')
                    expected_volume = project(plan) + '_data'
                    persistent = [mount for mount in row['Mounts'] if mount['Destination'] == '/data']
                    secrets_mount = [mount for mount in row['Mounts']
                                     if mount['Destination'] == '/run/secrets/portainer_admin_password']
                    encryption_mount = [mount for mount in row['Mounts']
                                        if mount['Destination'] == '/run/secrets/portainer']
                    need(len(persistent) == 1 and persistent[0]['Type'] == 'volume'
                         and persistent[0]['Name'] == expected_volume and persistent[0]['RW'],
                         'Portainer data-volume drift')
                    need(len(secrets_mount) == 1 and secrets_mount[0]['Type'] == 'bind'
                         and not secrets_mount[0]['RW']
                         and os.path.normcase(secrets_mount[0]['Source'])
                         == os.path.normcase(str(Path(plan['root']) / 'admin-password.txt')),
                         'Portainer secret mount drift')
                    need(len(encryption_mount) == 1 and encryption_mount[0]['Type'] == 'bind'
                         and not encryption_mount[0]['RW']
                         and os.path.normcase(encryption_mount[0]['Source'])
                         == os.path.normcase(str(Path(plan['root']) / 'encryption-key.txt')),
                         'Portainer encryption-key mount drift')
                    need(len(row['Mounts']) == 3, 'Unexpected Portainer mount')
                else:
                    need(host['Privileged'] and not host['ReadonlyRootfs'],
                         'Nested engine privilege contract drift')
                    need(host['Memory'] == ENGINE_MEMORY_MIB * 1024**2
                         and host['NanoCpus'] == ENGINE_CPUS * 1_000_000_000
                         and host['PidsLimit'] == ENGINE_PIDS, 'Nested engine resource drift')
                    need(not host.get('PortBindings') and not row['Mounts'],
                         'Nested engine must have no host port or persistent mount')
                    need(host.get('Tmpfs') == expected_engine_tmpfs(), 'Nested engine tmpfs drift')
                    need(row['Config'].get('Cmd') == engine_command(),
                         'Nested engine command drift')
                    need((row['Config'].get('Healthcheck') or {}) == engine_healthcheck(),
                         'Nested engine health-check drift')
                    need('DOCKER_TLS_CERTDIR=' in row['Config']['Env'], 'Nested engine TLS-mode drift')
                    need(set(row['NetworkSettings']['Networks']) == {project(plan) + '_control'},
                         'Nested engine network drift')
                found[kind][role] = row
            elif kind == 'networks':
                expected = {
                    project(plan) + '_frontend': False,
                    project(plan) + '_control': True,
                }
                need(row['Name'] in expected and row['Internal'] is expected[row['Name']]
                     and row['Driver'] == 'bridge', 'Network drift')
                need(set(row.get('Containers') or {})
                     <= {container['Id'] for container in found['containers'].values()},
                     'Foreign network attachment')
                found[kind].append(row)
            else:
                need(row['Name'] == project(plan) + '_data' and row['Driver'] == 'local'
                     and not row.get('Options'), 'Volume drift')
                attached = docker(['ps', '-aq', '--no-trunc', '--filter', 'volume=' + row['Name']],
                                  context=context).split()
                need(set(attached) <= {container['Id'] for container in found['containers'].values()},
                     'Foreign volume attachment')
                found[kind].append(row)
    return found


def file_hash(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def atomic_secret(path, value):
    safe_path(path)
    verify_private(path.parent, directory=True)
    need(not path.exists() and isinstance(value, str) and 20 <= len(value) <= 256
         and '\n' not in value and '\r' not in value, 'Invalid or existing private secret')
    temporary = path.parent / ('.pending-' + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    if os.name == 'nt':
        windows_acl(temporary, create=True)
    verify_private(temporary)
    os.link(temporary, path)
    temporary.unlink()


def read_secret(path):
    verify_private(path)
    need(path.stat().st_size <= 512, 'Private secret is too large')
    try:
        value = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as error:
        raise ConfigError('Cannot read private Portainer credential') from error
    need(20 <= len(value) <= 256 and '\n' not in value and '\r' not in value,
         'Invalid private Portainer credential')
    return value


def credential_hash(root):
    return hashlib.sha256(read_secret(Path(root) / 'admin-password.txt').encode()).hexdigest()


def encryption_key_hash(root):
    return hashlib.sha256(read_secret(Path(root) / 'encryption-key.txt').encode()).hexdigest()


def state_read(plan):
    root = Path(plan['root'])
    verify_private(root, directory=True)
    pending_guard(root)
    state = read_private(root / 'state.json')
    keys(state, {'kind', 'owner', 'plan_id', 'credential_hash', 'encryption_key_hash', 'status'},
         'Portainer state')
    need(state['kind'] == 'portainer-owned-v2' and state['plan_id'] == plan['plan_id'],
         'Ownership mismatch')
    need(isinstance(state['owner'], str) and re.fullmatch('[0-9a-f]{32}', state['owner']),
         'Invalid owner')
    need(state['credential_hash'] == credential_hash(root), 'Credential drift')
    need(state['encryption_key_hash'] == encryption_key_hash(root), 'Encryption-key drift')
    need(state['status'] in ('prepared', 'restore-copying', 'ready', 'running', 'stopped',
                             'removing', 'removed'), 'Invalid state')
    need(read_private(root / 'compose.json') == compose(plan, state['owner']),
         'Compose modified; refusing execution')
    return state


def prepare(plan):
    root = Path(plan['root'])
    if root.exists():
        return state_read(plan)
    inventory(plan, None)
    context = plan['runtime']['context']
    names = [project(plan) + '_frontend', project(plan) + '_control', project(plan) + '_data']
    existing_networks = set(docker(['network', 'ls', '--format', '{{.Name}}'], context=context).splitlines())
    existing_volumes = set(docker(['volume', 'ls', '--format', '{{.Name}}'], context=context).splitlines())
    need(not set(names[:2]) & existing_networks and names[2] not in existing_volumes,
         'Unowned resource name collision')
    port_free(plan['port'])
    for image_name in plan['images'].values():
        image = json.loads(docker(['image', 'inspect', image_name], context=context))[0]
        need(image['Os'] == 'linux' and image['Architecture'] == 'amd64',
             'Reviewed linux/amd64 image must be cached')
    create_private_directory(root)
    create_lock_file(root / 'operation.lock')
    password = (read_secret(Path(plan['recovery']['path']) / 'admin-password.txt')
                if plan['recovery'] else secrets.token_urlsafe(32))
    encryption_key = (read_secret(Path(plan['recovery']['path']) / 'encryption-key.txt')
                      if plan['recovery'] else secrets.token_hex(32))
    atomic_secret(root / 'admin-password.txt', password)
    atomic_secret(root / 'encryption-key.txt', encryption_key)
    state = {'kind': 'portainer-owned-v2', 'owner': uuid.uuid4().hex,
             'plan_id': plan['plan_id'],
             'credential_hash': hashlib.sha256(password.encode()).hexdigest(),
             'encryption_key_hash': hashlib.sha256(encryption_key.encode()).hexdigest(),
             'status': 'prepared'}
    atomic_json(root / 'compose.json', compose(plan, state['owner']))
    atomic_json(root / 'state.json', state)
    return state


def wait_engine(container, context):
    for _ in range(24):
        row = json.loads(docker(['inspect', container['Id']], context=context))[0]
        health = (row['State'].get('Health') or {}).get('Status')
        if health == 'healthy':
            return
        need(row['State']['Running'] and health != 'unhealthy',
             'Nested Docker engine failed health validation; retain state for review')
        time.sleep(2.5)
    raise ConfigError('Nested Docker engine health timed out; retain state for review')


def operate(plan, action, confirmation=None):
    validate_plan(plan)
    need(action in ('up', 'status', 'stop', 'remove'), 'Unsupported Portainer action')
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
        need(state['status'] != 'restore-copying',
             'Interrupted restore copy; preserve evidence and use a fresh target')
        need(state['status'] != 'removed' or not containers and not resources['networks'],
             'Resources reappeared after removal')
        if action == 'up':
            need(state['status'] not in ('removing', 'removed'),
                 'Removed deployments require a new recovery root')
            if not containers:
                need(state['status'] == 'prepared' and (not resources['volumes'] or plan['recovery'] is None),
                     'Recorded resources missing; no silent recreation')
                port_free(plan['port'])
                docker(['compose', '--project-name', project(plan), '--project-directory', str(root),
                        '-f', str(root / 'compose.json'), 'create', '--pull', 'never', '--no-build'],
                       context=context)
                resources = inventory(plan, state['owner'])
                containers = resources['containers']
            need(set(containers) == {'portainer', 'engine'} and len(resources['volumes']) == 1,
                 'Incomplete service creation; retain state for review')
            if plan['recovery'] and state['status'] == 'prepared':
                need(not any(container['State']['Running'] for container in containers.values()),
                     'Recovery must target never-started containers')
                state['status'] = 'restore-copying'
                atomic_json(root / 'state.json', state, replace=True)
                docker(['cp', str(Path(plan['recovery']['path']) / 'data') + '/.',
                        containers['portainer']['Id'] + ':/data/'], context=context)
                state['status'] = 'ready'
                atomic_json(root / 'state.json', state, replace=True)
            need(not any(container['State'].get('Paused') for container in containers.values()),
                 'Paused container needs explicit review')
            if not containers['engine']['State']['Running']:
                docker(['start', containers['engine']['Id']], context=context)
            wait_engine(containers['engine'], context)
            if not containers['portainer']['State']['Running']:
                port_free(plan['port'])
                docker(['start', containers['portainer']['Id']], context=context)
            state['status'] = 'running'
        elif action == 'stop':
            need(set(containers) == {'portainer', 'engine'}
                 and state['status'] not in ('removing', 'removed'), 'No owned deployment to stop')
            need(not any(container['State'].get('Paused') for container in containers.values()),
                 'Paused state requires review')
            for role in ('portainer', 'engine'):
                if containers[role]['State']['Running']:
                    docker(['stop', '--time', '30', containers[role]['Id']], context=context)
            state['status'] = 'stopped'
        elif action == 'remove':
            need(not any(container['State']['Running'] for container in containers.values()),
                 'Stop the owned services before removal')
            if state['status'] != 'removed':
                state['status'] = 'removing'
                atomic_json(root / 'state.json', state, replace=True)
                for role in ('portainer', 'engine'):
                    if role in containers:
                        docker(['rm', containers[role]['Id']], context=context)
                for network in inventory(plan, state['owner'])['networks']:
                    docker(['network', 'rm', network['Id']], context=context)
                state['status'] = 'removed'
        if action != 'status' and read_private(root / 'state.json') != state:
            atomic_json(root / 'state.json', state, replace=True)
        resources = inventory(plan, state['owner'])
        services = {role: row['State']['Status'] for role, row in resources['containers'].items()}
        return {'module': 'portainer', 'state': state['status'], 'services': services,
                'url': 'https://127.0.0.1:' + str(plan['port']),
                'docker_control': 'isolated-nested-engine', 'host_engine_access': False,
                'data_volumes_retained': len(resources['volumes'])}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def api(plan, path, *, method='GET', payload=None, token=None, expected=(200,), limit=1_000_000):
    need(path.startswith('/api/') and not path.startswith('//'), 'Invalid Portainer API path')
    data = None if payload is None else json.dumps(payload, separators=(',', ':')).encode()
    headers = {'Accept': 'application/json', 'User-Agent': 'HomeLab-Portainer-Validation/1',
               'Origin': f"https://127.0.0.1:{plan['port']}"}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    if token is not None:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(f"https://127.0.0.1:{plan['port']}{path}", data=data,
                                     method=method, headers=headers)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                         urllib.request.HTTPSHandler(context=context))
    try:
        with opener.open(request, timeout=30) as response:
            body = response.read(limit + 1)
            status = response.status
    except urllib.error.HTTPError as error:
        body = error.read(limit + 1)
        status = error.code
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise ConfigError('Portainer API request failed; no response details exposed') from error
    need(status in expected and len(body) <= limit,
         'Portainer API response contract failed; no response details exposed')
    if not body:
        return status, None
    try:
        return status, json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ConfigError('Portainer API returned invalid bounded JSON') from error


def authenticated(plan):
    password = read_secret(Path(plan['root']) / 'admin-password.txt')
    _, result = api(plan, '/api/auth', method='POST',
                    payload={'Username': 'admin', 'Password': password})
    need(isinstance(result, dict) and isinstance(result.get('jwt'), str)
         and 20 < len(result['jwt']) < 10_000, 'Portainer authentication contract failed')
    return result['jwt']


def exercise(plan, confirmation):
    validate_plan(plan)
    need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        need(state['status'] == 'running' and set(resources['containers']) == {'portainer', 'engine'}
             and all(row['State']['Running'] for row in resources['containers'].values()),
             'Portainer trial is not running')
        token = authenticated(plan)
        _, endpoints = api(plan, '/api/endpoints', token=token)
        matching = [row for row in endpoints if row.get('URL') == 'tcp://engine:2375']
        need(len(matching) == 1 and type(matching[0].get('Id')) is int,
             'Isolated Docker endpoint not uniquely registered')
        endpoint = matching[0]['Id']
        _, info = api(plan, f'/api/endpoints/{endpoint}/docker/info', token=token)
        need(isinstance(info, dict) and type(info.get('Containers')) is int
             and info['Containers'] == 0, 'Endpoint is not an empty isolated engine')
        api(plan, f'/api/endpoints/{endpoint}/docker/networks/{PROBE_NETWORK}', token=token,
            expected=(404,))
        created = None
        deleted = False
        try:
            _, result = api(plan, f'/api/endpoints/{endpoint}/docker/networks/create',
                            method='POST', token=token,
                            payload={'Name': PROBE_NETWORK, 'CheckDuplicate': True, 'Driver': 'bridge',
                                     'Labels': {'org.homelab.synthetic': 'true'}} , expected=(201,))
            created = result.get('Id') if isinstance(result, dict) else None
            need(isinstance(created, str) and bool(re.fullmatch('[0-9a-f]{64}', created)),
                 'Nested network creation returned an invalid identity')
            _, inspected = api(plan, f'/api/endpoints/{endpoint}/docker/networks/{created}', token=token)
            need(inspected.get('Name') == PROBE_NETWORK
                 and inspected.get('Labels', {}).get('org.homelab.synthetic') == 'true',
                 'Nested network inspection failed')
            api(plan, f'/api/endpoints/{endpoint}/docker/networks/{created}',
                method='DELETE', token=token, expected=(204,))
            deleted = True
            api(plan, f'/api/endpoints/{endpoint}/docker/networks/{created}', token=token,
                expected=(404,))
        finally:
            if created is not None and not deleted:
                try:
                    api(plan, f'/api/endpoints/{endpoint}/docker/networks/{created}',
                        method='DELETE', token=token, expected=(204, 404))
                except ConfigError:
                    pass
        need(deleted, 'Nested Docker-control cleanup failed; retain state for review')
        return {'operation': 'create-inspect-delete-network', 'status': 'passed',
                'docker_control': 'isolated-nested-engine', 'host_engine_access': False,
                'outer_resources_visible': False, 'probe_retained': False,
                'endpoint_count': len(endpoints)}


def tree_files(root, protect_new=False):
    root = safe_path(root)
    verify_private(root, directory=True)
    result = {}
    for path in sorted(root.rglob('*')):
        safe_path(path)
        info = path.stat()
        need(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode),
             'Unexpected backup resource')
        need(path.is_dir() or info.st_nlink == 1, 'Hard-linked backup files refused')
        if protect_new:
            if os.name == 'nt':
                windows_acl(path, create=True)
            else:
                path.chmod(0o700 if path.is_dir() else 0o600)
        verify_private(path, directory=path.is_dir())
        if path.is_file():
            result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def snapshot_summary(root):
    files = tree_files(root / 'data')
    need('portainer.edb' in files and (root / 'data/portainer.edb').stat().st_size > 0,
         'Snapshot has no nonempty Portainer database')
    return {'file_count': len(files),
            'bytes': sum((root / 'data' / relative).stat().st_size for relative in files),
            'content_fingerprint': digest(files), 'database_present': True}


def verify_backup(root):
    root = safe_path(root)
    verify_private(root, directory=True)
    manifest = read_private(root / 'manifest.json')
    keys(manifest, {'kind', 'images', 'permission', 'credential_hash', 'encryption_key_hash',
                    'tree', 'summary'},
         'Portainer backup manifest')
    images = load_json(MODULE / 'images.json')
    expected_images = {'portainer': images['portainer_image'], 'engine': images['engine_image']}
    need(manifest['kind'] == 'portainer-stopped-backup-v1'
         and manifest['images'] == expected_images
         and manifest['permission'] == 'isolated-nested-engine', 'Backup image/format mismatch')
    need(hashlib.sha256(read_secret(root / 'admin-password.txt').encode()).hexdigest()
         == manifest['credential_hash'], 'Backup credential mismatch')
    need(hashlib.sha256(read_secret(root / 'encryption-key.txt').encode()).hexdigest()
         == manifest['encryption_key_hash'], 'Backup encryption-key mismatch')
    need(tree_files(root / 'data') == manifest['tree'], 'Backup content checksum mismatch')
    need(snapshot_summary(root) == manifest['summary'], 'Backup content evidence mismatch')
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
        need(state['status'] == 'stopped' and set(resources['containers']) == {'portainer', 'engine'}
             and not any(row['State']['Running'] for row in resources['containers'].values()),
             'Stop both owned services before backup')
        create_private_directory(destination)
        create_private_directory(destination / 'data')
        docker(['cp', resources['containers']['portainer']['Id'] + ':/data/.',
                str(destination / 'data')], context=plan['runtime']['context'])
        tree_files(destination / 'data', protect_new=True)
        password = read_secret(root / 'admin-password.txt')
        encryption_key = read_secret(root / 'encryption-key.txt')
        atomic_secret(destination / 'admin-password.txt', password)
        atomic_secret(destination / 'encryption-key.txt', encryption_key)
        tree = tree_files(destination / 'data')
        summary = snapshot_summary(destination)
        manifest = {'kind': 'portainer-stopped-backup-v1', 'images': plan['images'],
                    'permission': 'isolated-nested-engine',
                    'credential_hash': hashlib.sha256(password.encode()).hexdigest(),
                    'encryption_key_hash': hashlib.sha256(encryption_key.encode()).hexdigest(),
                    'tree': tree, 'summary': summary}
        atomic_json(destination / 'manifest.json', manifest)
        verify_backup(destination)
        return {'backup_complete': True, 'encrypted': False,
                'contains_admin_credentials': True, 'summary': summary,
                'nested_engine_workloads_included': False, 'recovery_verified': False,
                'note': 'Restore into a fresh project and rerun the Docker-control exercise'}
