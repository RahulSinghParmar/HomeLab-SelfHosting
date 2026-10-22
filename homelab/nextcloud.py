"""Isolated Nextcloud lifecycle, WebDAV exercise and consistent recovery."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
import shutil
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .doctor import host_platform
from .glance import docker, local_runtime, port_free
from .privatefs import (atomic_json, create_lock_file, create_private_directory,
                        operation_lock, read_private, safe_path, verify_private, windows_acl,
                        windows_tree_acl)
from .sandbox import digest, pending_guard


MODULE = ROOT / 'modules/nextcloud'
SERVICES = ('cache', 'database', 'app', 'cron')
APP_AREAS = {
    'config': '/var/www/html/config',
    'data': '/var/www/html/data',
    'custom-apps': '/var/www/html/custom_apps',
    'themes': '/var/www/html/themes',
}
VOLUMES = ('cache-data', 'database-data', 'html', *APP_AREAS)
LIMITS = {
    'cache': {'memory_mib': 192, 'cpus': 0.25, 'pids': 96},
    'database': {'memory_mib': 768, 'cpus': 1.0, 'pids': 192},
    'app': {'memory_mib': 1536, 'cpus': 2.0, 'pids': 512},
    'cron': {'memory_mib': 512, 'cpus': 0.75, 'pids': 256},
}
ADMIN_USER = 'homelab-admin'
FIXTURE_NAME = 'phase5-nextcloud-recovery.txt'
FIXTURE_BODY = b'HomeLab Nextcloud Phase 5 WebDAV recovery marker v1\n'


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
                    'method': 'postgres-filesystem-restore'}
    plan = {
        'kind': 'homelab-nextcloud-plan', 'contract': 'nextcloud-isolated-recovery-v1',
        'platform': host_platform(), 'root': str(root), 'port': port, 'runtime': runtime,
        'images': images(), 'recovery': recovery, 'limits': LIMITS,
        'access': 'loopback', 'networks': ['frontend', 'internal-backend'],
        'docker_socket': False, 'mail': 'disabled', 'public_registration': False,
        'external_storage': 'not-mounted', 'background_jobs': 'cron',
        'recovery_method': 'postgres-filesystem-restore',
        'authoritative_material': ['postgres-custom-dump', *APP_AREAS],
        'derived_material': ['html', 'cache-data'],
    }
    plan['plan_id'] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'root', 'port', 'runtime', 'images',
                'recovery', 'limits', 'access', 'networks', 'docker_socket', 'mail',
                'public_registration', 'external_storage', 'background_jobs',
                'recovery_method', 'authoritative_material', 'derived_material',
                'plan_id'}, 'Nextcloud plan')
    backup = plan['recovery']['path'] if plan['recovery'] is not None else None
    need(canonical(plan) == canonical(make_plan(plan['root'], plan['port'], plan['runtime'], backup)),
         'Plan/image/recovery drift; review a new plan')
    return plan


def project(plan):
    return 'hl-nextcloud-' + plan['plan_id'][:16]


def tags(plan, owner):
    return {'org.homelab.owner': owner, 'org.homelab.plan': plan['plan_id'],
            'org.homelab.module': 'nextcloud'}


def new_credentials():
    return {'database_password': secrets.token_hex(32),
            'cache_password': secrets.token_hex(32),
            'admin_password': secrets.token_urlsafe(48)}


def validate_credentials(value):
    keys(value, {'database_password', 'cache_password', 'admin_password'},
         'Nextcloud credentials')
    need(all(isinstance(value[name], str) and len(value[name]) >= 64
             for name in value), 'Invalid private credential material')
    need(all('\n' not in value[name] and '\r' not in value[name] for name in value),
         'Invalid private credential material')
    return value


def validate_database_role(value):
    keys(value, {'username', 'password'}, 'Nextcloud application database role')
    need(isinstance(value['username'], str)
         and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,62}', value['username'])
         and value['username'] not in ('nextcloud', 'postgres'),
         'Invalid Nextcloud application database role name')
    need(isinstance(value['password'], str) and len(value['password']) >= 16
         and '\x00' not in value['password']
         and '\n' not in value['password'] and '\r' not in value['password'],
         'Invalid Nextcloud application database role password')
    return value


def _write_secret(path, value):
    need(not path.exists(), 'Refusing to overwrite an existing secret file')
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    if os.name == 'nt':
        windows_acl(path, create=True)
    verify_private(path)


def _secret_paths(plan):
    root = Path(plan['root']) / 'secrets'
    return {name: root / (name + '.txt') for name in
            ('database_password', 'cache_password', 'admin_password')}


def _verify_secret_files(plan, credentials):
    for name, path in _secret_paths(plan).items():
        verify_private(path)
        need(path.read_text(encoding='utf-8') == credentials[name],
             'Private secret file differs from reviewed credentials')


def compose(plan, owner, credentials):
    validate_credentials(credentials)
    label = tags(plan, owner)
    secret_paths = _secret_paths(plan)
    common = {'labels': label, 'pull_policy': 'never', 'restart': 'unless-stopped',
              'security_opt': ['no-new-privileges:true'],
              'logging': {'driver': 'json-file',
                          'options': {'max-size': '10m', 'max-file': '3'}}}
    secrets_map = {name: {'file': str(path)} for name, path in secret_paths.items()}
    cache = {
        **common, 'image': plan['images']['cache'],
        'command': ['sh', '-ec',
                    'exec redis-server --appendonly yes --requirepass "$$(cat /run/secrets/cache_password)"'],
        'secrets': ['cache_password'],
        'volumes': [{'type': 'volume', 'source': 'cache-data', 'target': '/data'}],
        'networks': ['backend'],
        'healthcheck': {'test': ['CMD-SHELL',
                                 'redis-cli -a "$$(cat /run/secrets/cache_password)" ping 2>/dev/null | grep -q PONG'],
                        'interval': '10s', 'timeout': '5s', 'retries': 12,
                        'start_period': '10s'},
        'mem_limit': '192m', 'mem_reservation': '32m', 'memswap_limit': '256m',
        'cpus': 0.25, 'pids_limit': 96,
    }
    database = {
        **common, 'image': plan['images']['database'],
        'environment': {'POSTGRES_DB': 'nextcloud', 'POSTGRES_USER': 'nextcloud',
                        'POSTGRES_PASSWORD_FILE': '/run/secrets/database_password'},
        'secrets': ['database_password'],
        'volumes': [{'type': 'volume', 'source': 'database-data',
                     'target': '/var/lib/postgresql'}],
        'networks': ['backend'], 'shm_size': '128m',
        'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U nextcloud -d nextcloud'],
                        'interval': '10s', 'timeout': '5s', 'retries': 12,
                        'start_period': '20s'},
        'mem_limit': '768m', 'mem_reservation': '128m', 'memswap_limit': '1024m',
        'cpus': 1.0, 'pids_limit': 192,
    }
    app_volumes = [{'type': 'volume', 'source': 'html', 'target': '/var/www/html'}]
    app_volumes.extend({'type': 'volume', 'source': name, 'target': target}
                       for name, target in APP_AREAS.items())
    environment = {
        'POSTGRES_HOST': 'database', 'POSTGRES_DB': 'nextcloud',
        'POSTGRES_USER': 'nextcloud',
        'POSTGRES_PASSWORD_FILE': '/run/secrets/database_password',
        'REDIS_HOST': 'cache', 'REDIS_HOST_PASSWORD_FILE': '/run/secrets/cache_password',
        'NEXTCLOUD_ADMIN_USER': ADMIN_USER,
        'NEXTCLOUD_ADMIN_PASSWORD_FILE': '/run/secrets/admin_password',
        'NEXTCLOUD_TRUSTED_DOMAINS': '127.0.0.1 localhost',
        'OVERWRITECLIURL': 'http://127.0.0.1:' + str(plan['port']),
        'OVERWRITEPROTOCOL': 'http', 'NEXTCLOUD_INIT_HTACCESS': 'true',
        'PHP_MEMORY_LIMIT': '512M', 'PHP_UPLOAD_LIMIT': '1G',
        'APACHE_BODY_LIMIT': '1073741824',
    }
    app = {
        **common, 'image': plan['images']['app'],
        'depends_on': {'cache': {'condition': 'service_healthy'},
                       'database': {'condition': 'service_healthy'}},
        'ports': [{'target': 80, 'published': str(plan['port']),
                   'host_ip': '127.0.0.1', 'protocol': 'tcp'}],
        'environment': environment,
        'secrets': ['database_password', 'cache_password', 'admin_password'],
        'volumes': app_volumes, 'networks': ['frontend', 'backend'],
        'healthcheck': {'test': ['CMD-SHELL',
                                 'curl -sS --max-time 10 http://127.0.0.1/status.php | grep -q \'"installed":true\''],
                        'interval': '10s', 'timeout': '10s', 'retries': 36,
                        'start_period': '40s'},
        'stop_grace_period': '60s', 'mem_limit': '1536m',
        'mem_reservation': '384m', 'memswap_limit': '2048m',
        'cpus': 2.0, 'pids_limit': 512,
    }
    cron = {
        **common, 'image': plan['images']['app'], 'entrypoint': ['/cron.sh'],
        'depends_on': {'app': {'condition': 'service_healthy'}},
        'environment': environment,
        'secrets': ['database_password', 'cache_password', 'admin_password'],
        'volumes': app_volumes, 'networks': ['backend'],
        'mem_limit': '512m', 'mem_reservation': '64m', 'memswap_limit': '640m',
        'cpus': 0.75, 'pids_limit': 256,
    }
    return {
        'services': {'cache': cache, 'database': database, 'app': app, 'cron': cron},
        'volumes': {name: {'labels': label} for name in VOLUMES},
        'networks': {'frontend': {'driver': 'bridge', 'labels': label},
                     'backend': {'driver': 'bridge', 'internal': True, 'labels': label}},
        'secrets': secrets_map,
    }


def compose_args(plan):
    root = Path(plan['root'])
    return ['compose', '--project-name', project(plan), '--project-directory', str(root),
            '-f', str(root / 'compose.json')]


def _role_image(plan, role):
    return plan['images']['app' if role in ('app', 'cron') else role]


def inventory(plan, owner):
    context = plan['runtime']['context']
    found = {'containers': {}, 'networks': [], 'volumes': []}
    ids = docker(['ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project(plan)],
                 context=context).split()
    need(len(ids) <= len(SERVICES), 'Unexpected Nextcloud project containers')
    rows = json.loads(docker(['inspect'] + ids, context=context)) if ids else []
    for row in rows:
        labels = row['Config'].get('Labels') or {}
        need(owner is not None and all(labels.get(key) == value
                                       for key, value in tags(plan, owner).items()),
             'Foreign resource; no adoption or mutation')
        role = labels.get('com.docker.compose.service')
        need(role in SERVICES and role not in found['containers'],
             'Unexpected or duplicate service')
        need(row['Config']['Image'] == _role_image(plan, role), 'Image drift')
        host = row['HostConfig']
        need(not host['Privileged'] and not host.get('Devices') and not host.get('DeviceRequests'),
             'Privilege/device drift')
        need('no-new-privileges:true' in host['SecurityOpt'], 'Security option drift')
        limit = LIMITS[role]
        need(host['Memory'] == limit['memory_mib'] * 1024**2
             and host['NanoCpus'] == int(limit['cpus'] * 1_000_000_000)
             and host['PidsLimit'] == limit['pids'], 'Resource drift')
        need(host['RestartPolicy']['Name'] == 'unless-stopped'
             and host['LogConfig'] == {'Type': 'json-file',
                                       'Config': {'max-size': '10m', 'max-file': '3'}},
             'Lifecycle/logging drift')
        expected_ports = ({'80/tcp': [{'HostIp': '127.0.0.1',
                                      'HostPort': str(plan['port'])}]}
                          if role == 'app' else {})
        need((host.get('PortBindings') or {}) == expected_ports, 'Port binding drift')
        networks = set(row['NetworkSettings']['Networks'])
        expected = ({project(plan) + '_backend', project(plan) + '_frontend'}
                    if role == 'app' else {project(plan) + '_backend'})
        need(networks == expected, 'Network drift')
        found['containers'][role] = row
    for kind, listing, inspect in (
            ('networks', ['network', 'ls', '-q'], ['network', 'inspect']),
            ('volumes', ['volume', 'ls', '-q'], ['volume', 'inspect'])):
        resource_ids = docker(listing + ['--filter',
                              'label=com.docker.compose.project=' + project(plan)],
                              context=context).split()
        need(len(resource_ids) <= (2 if kind == 'networks' else len(VOLUMES)),
             'Unexpected Nextcloud project resources')
        resources = json.loads(docker(inspect + resource_ids, context=context)) if resource_ids else []
        for row in resources:
            labels = row.get('Labels') or {}
            need(owner is not None and all(labels.get(key) == value
                                           for key, value in tags(plan, owner).items()),
                 'Foreign resource; no adoption or mutation')
        found[kind] = resources
    return found


def state_read(plan):
    root = Path(plan['root'])
    verify_private(root, directory=True)
    pending_guard(root)
    state = read_private(root / 'state.json')
    keys(state, {'kind', 'owner', 'plan_id', 'status', 'recovery'}, 'Nextcloud state')
    need(state['kind'] == 'nextcloud-owned-v1' and state['plan_id'] == plan['plan_id'],
         'Ownership mismatch')
    need(isinstance(state['owner'], str) and re.fullmatch('[0-9a-f]{32}', state['owner']),
         'Invalid owner')
    need(state['status'] in ('prepared', 'restoring', 'running', 'stopped',
                             'removing', 'removed'), 'Invalid state')
    credentials = validate_credentials(read_private(root / 'credentials.json'))
    _verify_secret_files(plan, credentials)
    need(read_private(root / 'compose.json') == compose(plan, state['owner'], credentials),
         'Compose modified; refusing execution')
    return state


def prepare(plan):
    root = Path(plan['root'])
    if root.exists():
        return state_read(plan)
    inventory(plan, None)
    context = plan['runtime']['context']
    port_free(plan['port'])
    for image in plan['images'].values():
        inspected = json.loads(docker(['image', 'inspect', image], context=context))[0]
        need(inspected['Os'] == 'linux' and inspected['Architecture'] == 'amd64',
             'Reviewed linux/amd64 images must be cached')
    create_private_directory(root)
    create_lock_file(root / 'operation.lock')
    credentials = (read_private(Path(plan['recovery']['path']) / 'credentials.json')
                   if plan['recovery'] else new_credentials())
    validate_credentials(credentials)
    create_private_directory(root / 'secrets')
    for name, path in _secret_paths(plan).items():
        _write_secret(path, credentials[name])
    owner = uuid.uuid4().hex
    state = {'kind': 'nextcloud-owned-v1', 'owner': owner, 'plan_id': plan['plan_id'],
             'status': 'prepared', 'recovery': None}
    atomic_json(root / 'credentials.json', credentials)
    atomic_json(root / 'compose.json', compose(plan, owner, credentials))
    atomic_json(root / 'state.json', state)
    return state


def wait_health(plan, roles, deadline_seconds=480):
    deadline = time.monotonic() + deadline_seconds
    context = plan['runtime']['context']
    while time.monotonic() < deadline:
        ids = docker(compose_args(plan) + ['ps', '-q'] + list(roles),
                     context=context).split()
        if len(ids) == len(roles):
            values = [docker(['inspect', '--format',
                              '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}',
                              value], context=context) for value in ids]
            if all(value in ('healthy', 'running') for value in values):
                return
            need(not any(value in ('exited', 'dead') for value in values),
                 'Nextcloud service exited before becoming ready')
        time.sleep(2)
    raise ConfigError('Nextcloud services did not become ready before the bounded deadline')


def _occ(plan, arguments, *, one_off=False, timeout=180):
    command = (['run', '--rm', '--no-deps', '--user', '33:33', '--entrypoint', 'php',
                'app', 'occ', *arguments]
               if one_off else ['exec', '-T', '--user', '33:33', 'app', 'php', 'occ', *arguments])
    return docker(compose_args(plan) + command, context=plan['runtime']['context'],
                  timeout=timeout)


def _auth_header(credentials):
    token = base64.b64encode((ADMIN_USER + ':' + credentials['admin_password']).encode()).decode()
    return 'Basic ' + token


def _database_role(plan, app_id):
    script = (
        '$configFile="/var/www/html/config/config.php"; '
        'include $configFile; '
        '$payload=["username"=>$CONFIG["dbuser"],"password"=>$CONFIG["dbpassword"]]; '
        'echo base64_encode(json_encode($payload, JSON_UNESCAPED_SLASHES));')
    encoded = docker(['exec', app_id, 'php', '-r', script],
                     context=plan['runtime']['context'], timeout=60)
    try:
        value = json.loads(base64.b64decode(encoded, validate=True).decode('utf-8'))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigError('Could not read the bounded Nextcloud database role') from error
    return validate_database_role(value)


def webdav_request(plan, credentials, method, name=FIXTURE_NAME, body=None,
                   expected=(200, 201, 204)):
    quoted_user = urllib.parse.quote(ADMIN_USER, safe='')
    quoted_name = urllib.parse.quote(name, safe='')
    url = (f'http://127.0.0.1:{plan["port"]}/remote.php/dav/files/'
           f'{quoted_user}/{quoted_name}')
    request = urllib.request.Request(url, data=body, method=method,
                                     headers={'Authorization': _auth_header(credentials),
                                              'X-Requested-With': 'XMLHttpRequest'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
            need(response.status in expected, 'Unexpected WebDAV response')
            return response.status, payload
    except urllib.error.HTTPError as error:
        if error.code in expected:
            return error.code, error.read()
        raise ConfigError('Nextcloud WebDAV request failed without exposing credentials') from error
    except (OSError, TimeoutError) as error:
        raise ConfigError('Nextcloud WebDAV request was unavailable') from error


def fixture_evidence(plan, credentials):
    _, payload = webdav_request(plan, credentials, 'GET')
    need(payload == FIXTURE_BODY, 'Stored Nextcloud fixture differs from uploaded content')
    return {'path': FIXTURE_NAME, 'bytes': len(payload),
            'sha256': hashlib.sha256(payload).hexdigest(),
            'marker_verified': True}


def backup_summary(manifest):
    fixture = manifest['fixture']
    return {'files': 1, 'path': fixture['path'], 'bytes': fixture['bytes'],
            'sha256': fixture['sha256'],
            'content_fingerprint': digest(fixture)}


def _restore_database(plan, backup, database_id):
    context = plan['runtime']['context']
    target = '/tmp/nextcloud-' + uuid.uuid4().hex + '.dump'
    docker(['cp', str(backup / 'nextcloud-postgres.dump'), database_id + ':' + target],
           context=context, timeout=120)
    try:
        docker(['exec', database_id, 'pg_restore', '--clean', '--if-exists',
                '--no-privileges', '-U', 'nextcloud', '-d', 'nextcloud', target],
               context=context, timeout=600)
    finally:
        try:
            docker(['exec', database_id, 'rm', '-f', target], context=context)
        except ConfigError:
            pass


def _restore_database_role(plan, backup, database_id):
    role = validate_database_role(read_private(backup / 'database-application-role.json'))
    username = "'" + role['username'].replace("'", "''") + "'"
    password = "'" + role['password'].replace("'", "''") + "'"
    sql = (
        'DO $homelab$\nDECLARE\n'
        f'  role_name text := {username};\n  role_password text := {password};\n'
        'BEGIN\n'
        "  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN\n"
        "    EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', role_name, role_password);\n"
        '  ELSE\n'
        "    EXECUTE format('CREATE ROLE %I WITH LOGIN PASSWORD %L', role_name, role_password);\n"
        '  END IF;\nEND\n$homelab$;\n')
    local = Path(plan['root']) / ('restore-role-' + uuid.uuid4().hex + '.sql')
    remote = '/tmp/nextcloud-role-' + uuid.uuid4().hex + '.sql'
    _write_secret(local, sql)
    try:
        docker(['cp', str(local), database_id + ':' + remote],
               context=plan['runtime']['context'], timeout=60)
        docker(['exec', database_id, 'psql', '--set', 'ON_ERROR_STOP=1',
                '-U', 'nextcloud', '-d', 'postgres', '--file', remote],
               context=plan['runtime']['context'], timeout=120)
    finally:
        try:
            docker(['exec', database_id, 'rm', '-f', remote],
                   context=plan['runtime']['context'])
        except ConfigError:
            pass
        local.unlink(missing_ok=True)


def _restore_filesystems(plan, backup, app_id):
    context = plan['runtime']['context']
    arguments = compose_args(plan)
    paths = ' '.join(APP_AREAS.values())
    docker(arguments + ['run', '--rm', '--no-deps', '--entrypoint', 'sh', 'app',
                        '-ec', 'for p in ' + paths + '; do find "$p" -mindepth 1 -delete; done'],
           context=context, timeout=300)
    for name, target in APP_AREAS.items():
        docker(['cp', str(backup / 'filesystem' / name) + '/.', app_id + ':' + target],
               context=context, timeout=300)
    docker(arguments + ['run', '--rm', '--no-deps', '--entrypoint', 'chown',
                        'app', '-R', 'www-data:www-data', *APP_AREAS.values()],
           context=context, timeout=300)


def _initialize_derived_html(plan):
    docker(compose_args(plan) + [
        'run', '--rm', '--no-deps', '--entrypoint', 'sh', 'app', '-ec',
        ('cp -a /usr/src/nextcloud/. /var/www/html/ && '
         'chown -R www-data:www-data /var/www/html')],
        context=plan['runtime']['context'], timeout=300)


def operate(plan, action, confirmation=None):
    validate_plan(plan)
    need(action in ('up', 'status', 'stop', 'remove'), 'Unsupported Nextcloud action')
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
             'Interrupted restore requires manual evidence review and a fresh target')
        if action == 'up':
            need(state['status'] not in ('removing', 'removed'),
                 'Removed deployments require a fresh root')
            if not containers:
                need(state['status'] == 'prepared' and (not resources['volumes'] or not plan['recovery']),
                     'Recorded resources missing; no silent recreation')
                port_free(plan['port'])
                docker(compose_args(plan) + ['create', '--pull', 'never', '--no-build'],
                       context=context, timeout=300)
                resources = inventory(plan, state['owner'])
                containers = resources['containers']
            need(set(containers) == set(SERVICES)
                 and len(resources['volumes']) == len(VOLUMES),
                 'Incomplete Nextcloud creation; retain state for review')
            need(not any(row['State'].get('Paused') for row in containers.values()),
                 'Paused state requires manual review')
            port_free(plan['port'])
            if plan['recovery'] and state['status'] == 'prepared':
                need(not any(row['State']['Running'] for row in containers.values()),
                     'Recovery must target never-started application containers')
                state['status'] = 'restoring'
                atomic_json(root / 'state.json', state, replace=True)
                docker(compose_args(plan) + ['start', 'cache', 'database'], context=context)
                wait_health(plan, ('cache', 'database'))
                backup_root = Path(plan['recovery']['path'])
                _initialize_derived_html(plan)
                _restore_database_role(plan, backup_root, containers['database']['Id'])
                _restore_database(plan, backup_root, containers['database']['Id'])
                _restore_filesystems(plan, backup_root, containers['app']['Id'])
                state['status'] = 'prepared'
                atomic_json(root / 'state.json', state, replace=True)
                docker(compose_args(plan) + ['start', 'app'], context=context)
                wait_health(plan, ('app',))
                _occ(plan, ['maintenance:mode', '--off'])
                _occ(plan, ['background:cron'])
                docker(compose_args(plan) + ['start', 'cron'], context=context)
            else:
                docker(compose_args(plan) + ['up', '-d', '--no-build', '--pull', 'never'],
                       context=context, timeout=480)
                wait_health(plan, SERVICES)
                _occ(plan, ['background:cron'])
            wait_health(plan, SERVICES)
            if plan['recovery']:
                credentials = read_private(root / 'credentials.json')
                restored = fixture_evidence(plan, credentials)
                source = verify_backup(Path(plan['recovery']['path']))
                need(restored == source['fixture'],
                     'Restored Nextcloud content differs from backup evidence')
                state['recovery'] = {'manifest_id': plan['recovery']['manifest_id'],
                                     'verified': True, 'summary': backup_summary(source)}
            state['status'] = 'running'
        elif action == 'stop':
            need(set(containers) == set(SERVICES)
                 and state['status'] not in ('removing', 'removed'),
                 'No complete owned deployment to stop')
            need(not any(row['State'].get('Paused') for row in containers.values()),
                 'Paused state requires manual review')
            docker(compose_args(plan) + ['stop', '--timeout', '60'],
                   context=context, timeout=180)
            state['status'] = 'stopped'
        elif action == 'remove':
            need(not any(row['State']['Running'] for row in containers.values()),
                 'Stop all owned services before removal')
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
            health[role] = (row['State'].get('Health') or {}).get('Status',
                                                                           row['State']['Status'])
        return {'module': 'nextcloud', 'state': state['status'], 'health': health,
                'url': 'http://127.0.0.1:' + str(plan['port']),
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
             'Start the complete owned Nextcloud project before exercise')
        credentials = read_private(root / 'credentials.json')
        try:
            webdav_request(plan, credentials, 'GET', expected=(404,))
        except ConfigError as error:
            raise ConfigError('Synthetic fixture already exists; use a fresh project') from error
        status, _ = webdav_request(plan, credentials, 'PUT', body=FIXTURE_BODY,
                                   expected=(201, 204))
        evidence = fixture_evidence(plan, credentials)
        cron_stopped = False
        failed_stage = 'cron-quiesce'
        try:
            docker(compose_args(plan) + ['stop', '--timeout', '60', 'cron'],
                   context=plan['runtime']['context'], timeout=120)
            cron_stopped = True
            failed_stage = 'background-mode'
            _occ(plan, ['background:cron'])
            failed_stage = 'cron-execution'
            docker(compose_args(plan) + ['exec', '-T', '--user', '33:33', 'app',
                                        'php', '-f', 'cron.php'],
                   context=plan['runtime']['context'], timeout=300)
        except ConfigError as error:
            raise ConfigError('Nextcloud exercise failed during ' + failed_stage) from error
        finally:
            if cron_stopped:
                docker(compose_args(plan) + ['start', 'cron'],
                       context=plan['runtime']['context'], timeout=120)
                wait_health(plan, ('cron',))
        return {'operation': 'webdav-upload-download-cron', 'status': 'passed',
                'upload_status': status, **evidence, 'background_job_run': True}


def file_hash(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def tree_files(root, *, protect_new=False):
    root = safe_path(root)
    verify_private(root, directory=True)
    paths = sorted(root.rglob('*'))
    result = {}
    for path in paths:
        safe_path(path)
        info = path.stat()
        need(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode),
             'Unexpected backup resource')
        need(path.is_dir() or info.st_nlink == 1, 'Hard-linked backup files refused')
        if os.name != 'nt':
            if protect_new:
                path.chmod(0o700 if path.is_dir() else 0o600)
            verify_private(path, directory=path.is_dir())
    if os.name == 'nt':
        # The root is created with protected inheritable rules before Docker copies
        # into it. Verify descendants in one pass; never repair an unexpected child.
        windows_tree_acl(root)
    for path in paths:
        if path.is_file():
            result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def verify_backup(root):
    root = safe_path(Path(root))
    verify_private(root, directory=True)
    manifest = read_private(root / 'manifest.json')
    keys(manifest, {'kind', 'created_utc', 'images', 'method', 'authoritative_material',
                    'derived_material', 'consistency', 'recovery_status',
                    'credentials_hash', 'configuration_sha256', 'database_sha256',
                    'database_role_sha256',
                    'trees', 'fixture', 'summary'}, 'Nextcloud backup manifest')
    need(manifest['kind'] == 'nextcloud-consistent-backup-v1'
         and manifest['images'] == images()
         and manifest['method'] == 'postgres-filesystem-restore',
         'Backup image/format mismatch')
    need(manifest['consistency'] == {'maintenance_mode': True, 'cron_quiesced': True,
                                     'application_quiesced': True,
                                     'postgres_archive_readable': True,
                                     'filesystem_copy_complete': True}
         and manifest['recovery_status'] == 'pending-independent-restore',
         'Backup consistency/recovery evidence is incomplete')
    credentials = validate_credentials(read_private(root / 'credentials.json'))
    need(digest(credentials) == manifest['credentials_hash'],
         'Backup credential checksum mismatch')
    need(file_hash(root / 'nextcloud-postgres.dump') == manifest['database_sha256'],
         'PostgreSQL dump checksum mismatch')
    validate_database_role(read_private(root / 'database-application-role.json'))
    need(file_hash(root / 'database-application-role.json') ==
         manifest['database_role_sha256'],
         'PostgreSQL application role checksum mismatch')
    need(manifest['configuration_sha256'] == {
        'private': file_hash(root / 'compose.private.json'),
        'sanitized': file_hash(root / 'sanitized-config.json')},
         'Backup configuration checksum mismatch')
    expected = {name: tree_files(root / 'filesystem' / name) for name in APP_AREAS}
    need(expected == manifest['trees'], 'Backup content checksum mismatch')
    need(manifest['fixture']['path'] == FIXTURE_NAME
         and manifest['fixture']['sha256'] == hashlib.sha256(FIXTURE_BODY).hexdigest()
         and manifest['fixture']['bytes'] == len(FIXTURE_BODY)
         and manifest['fixture']['marker_verified'] is True,
         'Backup lacks nonempty semantic WebDAV evidence')
    need(backup_summary(manifest) == manifest['summary'], 'Backup summary mismatch')
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
             'Start the complete owned Nextcloud project before backup')
        credentials = read_private(root / 'credentials.json')
        fixture = fixture_evidence(plan, credentials)
        context = plan['runtime']['context']
        app = resources['containers']['app']['Id']
        database = resources['containers']['database']['Id']
        database_role = _database_role(plan, app)
        cron_stopped = False
        app_stopped = False
        maintenance_on = False
        failed_stage = 'quiesce'
        create_private_directory(destination)
        try:
            docker(compose_args(plan) + ['stop', '--timeout', '60', 'cron'],
                   context=context, timeout=120)
            cron_stopped = True
            _occ(plan, ['maintenance:mode', '--on'])
            maintenance_on = True
            docker(compose_args(plan) + ['stop', '--timeout', '60', 'app'],
                   context=context, timeout=120)
            app_stopped = True
            dump_target = '/tmp/nextcloud-' + uuid.uuid4().hex + '.dump'
            failed_stage = 'postgres-dump'
            docker(['exec', database, 'pg_dump', '-U', 'nextcloud', '-d', 'nextcloud',
                    '--format', 'custom', '--file', dump_target],
                   context=context, timeout=600)
            failed_stage = 'postgres-archive-check'
            docker(['exec', database, 'pg_restore', '--list', dump_target],
                   context=context, timeout=120)
            failed_stage = 'postgres-copy'
            docker(['cp', database + ':' + dump_target,
                    str(destination / 'nextcloud-postgres.dump')],
                   context=context, timeout=120)
            docker(['exec', database, 'rm', '-f', dump_target], context=context)
            failed_stage = 'filesystem-copy'
            create_private_directory(destination / 'filesystem')
            for name, source in APP_AREAS.items():
                create_private_directory(destination / 'filesystem' / name)
                docker(['cp', app + ':' + source + '/.',
                        str(destination / 'filesystem' / name)],
                       context=context, timeout=600)
            failed_stage = 'metadata-copy'
            shutil.copy2(root / 'credentials.json', destination / 'credentials.json')
            shutil.copy2(root / 'compose.json', destination / 'compose.private.json')
            atomic_json(destination / 'database-application-role.json', database_role)
            atomic_json(destination / 'sanitized-config.json', {
                'kind': 'nextcloud-sanitized-configuration-v1',
                'images': plan['images'], 'limits': plan['limits'],
                'access': plan['access'], 'mail': plan['mail'],
                'public_registration': plan['public_registration'],
                'external_storage': plan['external_storage'],
                'background_jobs': plan['background_jobs'],
                'recovery_method': plan['recovery_method'],
            })
            tree_files(destination / 'filesystem', protect_new=True)
            failed_stage = 'private-permissions'
            protected = ('credentials.json', 'compose.private.json',
                         'database-application-role.json',
                         'nextcloud-postgres.dump')
            for name in protected:
                path = destination / name
                if os.name == 'nt':
                    windows_acl(path, create=True)
                else:
                    path.chmod(0o600)
                verify_private(path)
            trees = {name: tree_files(destination / 'filesystem' / name)
                     for name in APP_AREAS}
            manifest = {
                'kind': 'nextcloud-consistent-backup-v1',
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'images': plan['images'], 'method': 'postgres-filesystem-restore',
                'authoritative_material': ['postgres-custom-dump', *APP_AREAS],
                'derived_material': ['html', 'cache-data'],
                'consistency': {'maintenance_mode': True, 'cron_quiesced': True,
                                'application_quiesced': True,
                                'postgres_archive_readable': True,
                                'filesystem_copy_complete': True},
                'recovery_status': 'pending-independent-restore',
                'credentials_hash': digest(read_private(destination / 'credentials.json')),
                'configuration_sha256': {
                    'private': file_hash(destination / 'compose.private.json'),
                    'sanitized': file_hash(destination / 'sanitized-config.json')},
                'database_sha256': file_hash(destination / 'nextcloud-postgres.dump'),
                'database_role_sha256': file_hash(
                    destination / 'database-application-role.json'),
                'trees': trees, 'fixture': fixture, 'summary': None,
            }
            manifest['summary'] = backup_summary(manifest)
            atomic_json(destination / 'manifest.json', manifest)
            failed_stage = 'manifest-verification'
            verify_backup(destination)
        except ConfigError as error:
            raise ConfigError('Nextcloud backup failed during ' + failed_stage
                              + '; sensitive partial state was retained for review') from error
        finally:
            if app_stopped:
                docker(compose_args(plan) + ['start', 'app'], context=context, timeout=180)
                wait_health(plan, ('app',))
            if maintenance_on:
                _occ(plan, ['maintenance:mode', '--off'])
            if cron_stopped:
                docker(compose_args(plan) + ['start', 'cron'], context=context, timeout=120)
                wait_health(plan, ('cron',))
        return {'backup_complete': True, 'application_consistent': True,
                'encrypted': False, 'contains_credentials': True,
                'summary': manifest['summary'], 'recovery_verified': False,
                'note': ('Sensitive local staging backup; restore into a fresh project '
                         'before encrypted off-host retention')}
