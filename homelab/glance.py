"""Experimental Glance-only lifecycle. No adoption, arbitrary Compose or image pulls."""

import json
import os
from pathlib import Path
import re
import socket
import subprocess
import uuid

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .doctor import host_platform, local_endpoint
from .io import write_private
from .privatefs import atomic_json, create_lock_file, create_private_directory, operation_lock, read_private, safe_path, verify_private
from .sandbox import digest, pending_guard

MODULE = ROOT / 'modules/glance'


def docker(arguments, *, context=None):
    environment = {key: value for key, value in os.environ.items() if not key.startswith('COMPOSE_')}
    environment['COMPOSE_DISABLE_ENV_FILE'] = 'true'
    for key in ('DOCKER_HOST', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
        need(not environment.get(key), 'Docker endpoint/TLS overrides require explicit review')
    command = ['docker'] + (['--context', context] if context else []) + list(arguments)
    try:
        result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=60, shell=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ConfigError('Docker command unavailable or interrupted; inspect owned state before retrying') from error
    need(result.returncode == 0, 'Docker operation failed; no raw logs exposed; retain state for review')
    return result.stdout.strip()


def local_runtime():
    context = docker(['context', 'show'])
    need(bool(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*', context)), 'Invalid Docker context')
    endpoint = json.loads(docker(['context', 'inspect', context, '--format', '{{json .Endpoints.docker.Host}}']))
    need(local_endpoint(endpoint), 'Remote Docker contexts are not supported')
    info = json.loads(docker(['info', '--format', '{"id":{{json .ID}},"os":{{json .OSType}},"arch":{{json .Architecture}}}'], context=context))
    need(info['os'] == 'linux' and info['arch'] in ('amd64', 'x86_64'), 'This milestone requires a local Linux amd64 engine')
    return {'context': context, 'endpoint': endpoint, 'engine_id': info['id']}


def make_plan(root: Path, port: int, runtime: dict) -> dict:
    root = safe_path(root)
    need('$' not in str(root), 'Compose interpolation characters are not allowed in installation paths')
    need(root.parent.is_dir(), 'Installation parent must already exist')
    need(type(port) is int and 1024 <= port <= 65535, 'Choose an unprivileged TCP port')
    keys(runtime, {'context', 'endpoint', 'engine_id'}, 'local runtime')
    image = load_json(MODULE / 'image.json')['image']
    dashboard = load_json(MODULE / 'dashboard.json')
    plan = {'kind': 'homelab-glance-plan', 'contract': 'glance-loopback-v2', 'platform': host_platform(),
            'root': str(root), 'port': port, 'runtime': runtime, 'image': image, 'dashboard': dashboard,
            'limits': {'memory_mib': 128, 'cpus': 0.5, 'pids': 100}, 'access': 'loopback', 'docker_socket': False,
            'network': 'dedicated-bridge-outbound-allowed'}
    plan['plan_id'] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'root', 'port', 'runtime', 'image', 'dashboard', 'limits', 'access', 'docker_socket', 'network', 'plan_id'}, 'Glance plan')
    need(canonical(plan) == canonical(make_plan(Path(plan['root']), plan['port'], plan['runtime'])), 'Plan/template drift; recreate and review the plan')
    return plan


def project(plan):
    return 'hl-glance-' + plan['plan_id'][:16]


def labels(plan, owner):
    return {'org.homelab.owner': owner, 'org.homelab.plan': plan['plan_id'], 'org.homelab.module': 'glance'}


def compose(plan, owner):
    tags = labels(plan, owner)
    return {'services': {'dashboard': {
        'image': plan['image'], 'labels': tags, 'pull_policy': 'never', 'restart': 'unless-stopped',
        'ports': [{'target': 8080, 'published': str(plan['port']), 'host_ip': '127.0.0.1', 'protocol': 'tcp'}],
        'volumes': [{'type': 'bind', 'source': str(Path(plan['root']) / 'glance.yml'), 'target': '/app/config/glance.yml', 'read_only': True, 'bind': {'create_host_path': False}}],
        'read_only': True, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
        'mem_limit': '128m', 'cpus': 0.5, 'pids_limit': 100,
        'logging': {'driver': 'json-file', 'options': {'max-size': '5m', 'max-file': '2'}}
    }}, 'networks': {'default': {'driver': 'bridge', 'internal': False, 'labels': tags}}}


def inventory(plan, owner):
    context = plan['runtime']['context']
    found = {}
    for resource, verb in (('containers', ['ps', '-aq']), ('networks', ['network', 'ls', '-q'])):
        ids = docker(verb + ['--filter', 'label=com.docker.compose.project=' + project(plan)], context=context).split()
        need(len(ids) <= 1, 'Unexpected project resources; no mutations allowed')
        rows = json.loads(docker((['inspect'] if resource == 'containers' else ['network', 'inspect']) + ids, context=context)) if ids else []
        for row in rows:
            actual = row['Config']['Labels'] if resource == 'containers' else row['Labels']
            need(owner is not None and all(actual.get(key) == value for key, value in labels(plan, owner).items()), 'Foreign project resource; refusing adoption')
            if resource == 'containers':
                need(actual.get('com.docker.compose.service') == 'dashboard' and row['Config']['Image'] == plan['image'], 'Container specification drift')
                host = row['HostConfig']
                need(host['ReadonlyRootfs'] and host['Memory'] == 128 * 1024 * 1024 and host['NanoCpus'] == 500000000 and host['PidsLimit'] == 100, 'Container security/resource drift')
                need(host['PortBindings'] == {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(plan['port'])}]}, 'Container binding drift')
                need(host['CapDrop'] == ['ALL'] and 'no-new-privileges:true' in host['SecurityOpt'], 'Container privilege drift')
                need(len(row['Mounts']) == 1 and row['Mounts'][0]['Destination'] == '/app/config/glance.yml' and row['Mounts'][0]['RW'] is False, 'Container mount drift')
                mount = row['Mounts'][0]
                need(mount['Type'] == 'bind' and os.path.normcase(mount['Source']) == os.path.normcase(str(Path(plan['root']) / 'glance.yml')), 'Container mount source drift')
                need(not host['Privileged'] and not host.get('CapAdd') and not host.get('Devices') and not host.get('DeviceRequests'), 'Container privilege/device drift')
                need(host['RestartPolicy']['Name'] == 'unless-stopped' and host['LogConfig'] == {'Type': 'json-file', 'Config': {'max-size': '5m', 'max-file': '2'}}, 'Container lifecycle/logging drift')
                need(set(row['NetworkSettings']['Networks']) == {project(plan) + '_default'}, 'Unexpected container network')
                if row['State']['Running']:
                    need(row['NetworkSettings']['Ports'] == host['PortBindings'], 'Requested port is not actually published')
            else:
                need(row['Internal'] is False and row['Driver'] == 'bridge' and set(row.get('Containers') or {}) <= {container['Id'] for container in found['containers']}, 'Foreign network attachment or network drift; refusing mutation')
        found[resource] = rows
    return found


def state_read(plan):
    root = Path(plan['root'])
    verify_private(root, directory=True)
    pending_guard(root)
    state = read_private(root / 'state.json')
    keys(state, {'kind', 'owner', 'plan_id', 'status'}, 'Glance state')
    need(state['kind'] == 'glance-owned-v1' and state['plan_id'] == plan['plan_id'], 'Installation ownership mismatch')
    need(isinstance(state['owner'], str) and bool(re.fullmatch('[0-9a-f]{32}', state['owner'])), 'Invalid owner')
    need(state['status'] in ('prepared', 'running', 'stopped', 'removing', 'removed'), 'Invalid lifecycle state')
    need(read_private(root / 'glance.yml') == plan['dashboard'], 'Dashboard modified; preserve and review rather than overwrite')
    need(read_private(root / 'compose.json') == compose(plan, state['owner']), 'Compose modified; refusing execution')
    return state


def port_free(port):
    with socket.socket() as listener:
        if os.name == 'nt':
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind(('127.0.0.1', port))
        except OSError as error:
            raise ConfigError('Requested loopback port is occupied') from error


def prepare(plan):
    root = Path(plan['root'])
    if root.exists():
        return state_read(plan)
    inventory(plan, None)
    port_free(plan['port'])
    context = plan['runtime']['context']
    image = json.loads(docker(['image', 'inspect', plan['image']], context=context))[0]
    need(image['Os'] == 'linux' and image['Architecture'] == 'amd64', 'Pinned image must already be cached for linux/amd64')
    create_private_directory(root)
    create_lock_file(root / 'operation.lock')
    state = {'kind': 'glance-owned-v1', 'owner': uuid.uuid4().hex, 'plan_id': plan['plan_id'], 'status': 'prepared'}
    atomic_json(root / 'glance.yml', plan['dashboard'])
    atomic_json(root / 'compose.json', compose(plan, state['owner']))
    atomic_json(root / 'state.json', state)
    return state


def operate(plan, action, confirmation=None):
    validate_plan(plan)
    need(action in ('up', 'status', 'stop', 'remove'), 'Unsupported Glance action')
    if action != 'status':
        need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Docker context/engine changed; refusing operation')
    root = Path(plan['root'])
    if action == 'up':
        prepare(plan)
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        containers = resources['containers']
        need(state['status'] != 'removed' or not any(resources.values()), 'Resources reappeared after removal; refusing mutation')
        context = plan['runtime']['context']
        if action == 'up':
            need(state['status'] not in ('removing', 'removed'), 'Removed deployments cannot be implicitly reactivated')
            if containers:
                need(not containers[0]['State'].get('Paused'), 'Paused state needs explicit manual review')
                if not containers[0]['State']['Running']:
                    port_free(plan['port'])
                    docker(['start', containers[0]['Id']], context=context)
            else:
                need(state['status'] == 'prepared', 'Recorded container missing; no silent recreation')
                port_free(plan['port'])
                docker(['compose', '--project-name', project(plan), '--project-directory', str(root), '-f', str(root / 'compose.json'), 'up', '-d', '--pull', 'never', '--no-build'], context=context)
            state['status'] = 'running'
        elif action == 'stop':
            need(state['status'] in ('running', 'stopped') and bool(containers), 'No owned deployment to stop')
            docker(['stop', '--time', '10', containers[0]['Id']], context=context)
            state['status'] = 'stopped'
        elif action == 'remove':
            need(not containers or not containers[0]['State']['Running'], 'Stop the owned container before removal')
            if state['status'] != 'removed':
                state['status'] = 'removing'
                atomic_json(root / 'state.json', state, replace=True)
                if containers:
                    docker(['rm', containers[0]['Id']], context=context)
                for network in inventory(plan, state['owner'])['networks']:
                    docker(['network', 'rm', network['Id']], context=context)
                state['status'] = 'removed'
        if action != 'status':
            current = read_private(root / 'state.json')
            if state != current:
                atomic_json(root / 'state.json', state, replace=True)
        resources = inventory(plan, state['owner'])
        return {'module': 'glance', 'state': state['status'], 'container_count': len(resources['containers']),
                'running': bool(resources['containers'] and resources['containers'][0]['State']['Running']),
                'url': 'http://127.0.0.1:' + str(plan['port']), 'application_health': 'requires-rendered-verification', 'data_retained': True}


def export_config(plan, output):
    validate_plan(plan)
    root = Path(plan['root'])
    need(not output.resolve().is_relative_to(root), 'Export destination must be outside installation storage')
    with operation_lock(root / 'operation.lock'):
        state_read(plan)
        config = read_private(root / 'glance.yml')
        write_private(output, {'kind': 'homelab-glance-config-export', 'config': config, 'sha256': digest(config)})


def restore_config(source):
    data = load_json(source)
    keys(data, {'kind', 'config', 'sha256'}, 'Glance export')
    need(data['kind'] == 'homelab-glance-config-export' and digest(data['config']) == data['sha256'], 'Invalid configuration export')
    need(data['config'] == load_json(MODULE / 'dashboard.json'), 'This milestone restores only its certified starter configuration')
