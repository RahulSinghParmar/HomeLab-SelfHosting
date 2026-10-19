"""Isolated Paperless-ngx lifecycle, synthetic document exercise and consistent recovery."""
from __future__ import annotations

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
import uuid

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .doctor import host_platform
from .glance import docker, local_runtime, port_free
from .privatefs import (atomic_json, create_lock_file, create_private_directory,
                        operation_lock, read_private, safe_path, verify_private, windows_acl)
from .sandbox import digest, pending_guard


MODULE = ROOT / 'modules/paperless-ngx'
SERVICES = ('broker', 'database', 'paperless')
AREAS = {
    'data': '/usr/src/paperless/data',
    'media': '/usr/src/paperless/media',
    'export': '/usr/src/paperless/export',
    'consume': '/usr/src/paperless/consume',
}
VOLUMES = ('broker-data', 'database-data', *AREAS)
LIMITS = {
    'broker': {'memory_mib': 128, 'cpus': 0.25, 'pids': 64},
    'database': {'memory_mib': 512, 'cpus': 1.0, 'pids': 128},
    'paperless': {'memory_mib': 1792, 'cpus': 2.0, 'pids': 512},
}


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
                    'method': 'document-exporter-importer'}
    plan = {
        'kind': 'homelab-paperless-plan', 'contract': 'paperless-isolated-recovery-v1',
        'platform': host_platform(), 'root': str(root), 'port': port, 'runtime': runtime,
        'images': images(), 'recovery': recovery, 'limits': LIMITS,
        'access': 'loopback', 'networks': ['frontend', 'internal-backend'],
        'docker_socket': False, 'mail': 'disabled', 'signups': False,
        'recovery_method': 'document-exporter-importer',
        'secondary_recovery_material': ['postgres-custom-dump', 'data', 'media', 'export'],
    }
    plan['plan_id'] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'root', 'port', 'runtime', 'images', 'recovery',
                'limits', 'access', 'networks', 'docker_socket', 'mail', 'signups',
                'recovery_method', 'secondary_recovery_material', 'plan_id'}, 'Paperless plan')
    backup = plan['recovery']['path'] if plan['recovery'] is not None else None
    need(canonical(plan) == canonical(make_plan(plan['root'], plan['port'], plan['runtime'], backup)),
         'Plan/image/recovery drift; review a new plan')
    return plan


def project(plan):
    return 'hl-paperless-' + plan['plan_id'][:16]


def tags(plan, owner):
    return {'org.homelab.owner': owner, 'org.homelab.plan': plan['plan_id'],
            'org.homelab.module': 'paperless-ngx'}


def new_credentials():
    return {'database_password': secrets.token_hex(32), 'broker_password': secrets.token_hex(32),
            'secret_key': secrets.token_hex(48)}


def validate_credentials(value):
    keys(value, {'database_password', 'broker_password', 'secret_key'}, 'Paperless credentials')
    need(all(isinstance(item, str) and re.fullmatch('[0-9a-f]{64,96}', item) for item in value.values()),
         'Invalid private credential material')
    return value


def compose(plan, owner, credentials):
    validate_credentials(credentials)
    label = tags(plan, owner)
    common = {'labels': label, 'pull_policy': 'never', 'restart': 'unless-stopped',
              'security_opt': ['no-new-privileges:true'],
              'logging': {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '3'}}}
    broker = {
        **common, 'image': plan['images']['broker'],
        'command': ['sh', '-ec', 'exec valkey-server --appendonly yes --requirepass "$$VALKEY_PASSWORD"'],
        'environment': {'VALKEY_PASSWORD': credentials['broker_password']},
        'volumes': [{'type': 'volume', 'source': 'broker-data', 'target': '/data'}],
        'networks': ['backend'],
        'healthcheck': {'test': ['CMD-SHELL', 'valkey-cli -a "$$VALKEY_PASSWORD" ping | grep -q PONG'],
                        'interval': '10s', 'timeout': '5s', 'retries': 10, 'start_period': '10s'},
        'mem_limit': '128m', 'mem_reservation': '32m', 'memswap_limit': '192m',
        'cpus': 0.25, 'pids_limit': 64,
    }
    database = {
        **common, 'image': plan['images']['database'],
        'environment': {'POSTGRES_DB': 'paperless', 'POSTGRES_USER': 'paperless',
                        'POSTGRES_PASSWORD': credentials['database_password']},
        'volumes': [{'type': 'volume', 'source': 'database-data', 'target': '/var/lib/postgresql'}],
        'networks': ['backend'], 'shm_size': '128m',
        'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U paperless -d paperless'],
                        'interval': '10s', 'timeout': '5s', 'retries': 10, 'start_period': '20s'},
        'mem_limit': '512m', 'mem_reservation': '128m', 'memswap_limit': '768m',
        'cpus': 1.0, 'pids_limit': 128,
    }
    paperless_volumes = [{'type': 'volume', 'source': name, 'target': target}
                         for name, target in AREAS.items()]
    if plan['recovery']:
        paperless_volumes.append({'type': 'bind',
                                  'source': str(Path(plan['recovery']['path']) / 'document-export'),
                                  'target': '/restore-import', 'read_only': True})
    paperless = {
        **common, 'image': plan['images']['paperless'],
        'depends_on': {'broker': {'condition': 'service_healthy'},
                       'database': {'condition': 'service_healthy'}},
        'ports': [{'target': 8000, 'published': str(plan['port']), 'host_ip': '127.0.0.1',
                   'protocol': 'tcp'}],
        'environment': {
            'PAPERLESS_REDIS': 'redis://:' + credentials['broker_password'] + '@broker:6379',
            'PAPERLESS_DBENGINE': 'postgresql', 'PAPERLESS_DBHOST': 'database',
            'PAPERLESS_DBPORT': '5432', 'PAPERLESS_DBNAME': 'paperless',
            'PAPERLESS_DBUSER': 'paperless', 'PAPERLESS_DBPASS': credentials['database_password'],
            'PAPERLESS_SECRET_KEY': credentials['secret_key'],
            'PAPERLESS_URL': 'http://127.0.0.1:' + str(plan['port']),
            'PAPERLESS_ALLOWED_HOSTS': '127.0.0.1,localhost',
            'PAPERLESS_CSRF_TRUSTED_ORIGINS': 'http://127.0.0.1:' + str(plan['port']),
            'PAPERLESS_TIME_ZONE': 'UTC', 'PAPERLESS_OCR_LANGUAGE': 'eng',
            'PAPERLESS_OCR_MODE': 'auto', 'PAPERLESS_OCR_CLEAN': 'clean',
            'PAPERLESS_CONSUMER_DELETE_DUPLICATES': 'true',
            'PAPERLESS_CONSUMER_STABILITY_DELAY': '5', 'PAPERLESS_WEBSERVER_WORKERS': '1',
            'PAPERLESS_TASK_WORKERS': '1', 'PAPERLESS_THREADS_PER_WORKER': '1',
            'PAPERLESS_CONSUMER_POLLING_INTERVAL': '5', 'PAPERLESS_ACCOUNT_ALLOW_SIGNUPS': 'false',
            'PAPERLESS_AUDIT_LOG_ENABLED': 'true', 'PAPERLESS_AI_ENABLED': 'false',
        },
        'volumes': paperless_volumes, 'networks': ['frontend', 'backend'],
        'healthcheck': {'test': ['CMD-SHELL', 'curl -fsS --max-time 10 http://localhost:8000/ >/dev/null || exit 1'],
                        'interval': '10s', 'timeout': '10s', 'retries': 30, 'start_period': '30s'},
        'stop_grace_period': '60s', 'mem_limit': '1792m', 'mem_reservation': '512m',
        'memswap_limit': '2304m', 'cpus': 2.0, 'pids_limit': 512,
    }
    return {
        'services': {'broker': broker, 'database': database, 'paperless': paperless},
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
    need(len(ids) <= len(SERVICES), 'Unexpected Paperless project containers')
    rows = json.loads(docker(['inspect'] + ids, context=context)) if ids else []
    for row in rows:
        labels = row['Config'].get('Labels') or {}
        need(owner is not None and all(labels.get(key) == value for key, value in tags(plan, owner).items()),
             'Foreign resource; no adoption or mutation')
        role = labels.get('com.docker.compose.service')
        need(role in SERVICES and role not in found['containers'], 'Unexpected or duplicate service')
        need(row['Config']['Image'] == plan['images'][role], 'Image drift')
        host = row['HostConfig']
        need(not host['Privileged'] and not host.get('Devices') and not host.get('DeviceRequests'),
             'Privilege/device drift')
        need('no-new-privileges:true' in host['SecurityOpt'], 'Security option drift')
        limit = LIMITS[role]
        need(host['Memory'] == limit['memory_mib'] * 1024**2
             and host['NanoCpus'] == int(limit['cpus'] * 1_000_000_000)
             and host['PidsLimit'] == limit['pids'], 'Resource drift')
        need(host['RestartPolicy']['Name'] == 'unless-stopped'
             and host['LogConfig'] == {'Type': 'json-file', 'Config': {'max-size': '10m', 'max-file': '3'}},
             'Lifecycle/logging drift')
        expected_ports = ({'8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(plan['port'])}]}
                          if role == 'paperless' else {})
        need((host.get('PortBindings') or {}) == expected_ports, 'Port binding drift')
        networks = set(row['NetworkSettings']['Networks'])
        expected_networks = ({project(plan) + '_backend', project(plan) + '_frontend'}
                             if role == 'paperless' else {project(plan) + '_backend'})
        need(networks == expected_networks, 'Network drift')
        found['containers'][role] = row
    for kind, listing, inspect in (
            ('networks', ['network', 'ls', '-q'], ['network', 'inspect']),
            ('volumes', ['volume', 'ls', '-q'], ['volume', 'inspect'])):
        resource_ids = docker(listing + ['--filter', 'label=com.docker.compose.project=' + project(plan)],
                              context=context).split()
        need(len(resource_ids) <= (2 if kind == 'networks' else len(VOLUMES)),
             'Unexpected Paperless project resources')
        resources = json.loads(docker(inspect + resource_ids, context=context)) if resource_ids else []
        for row in resources:
            labels = row.get('Labels') or {}
            need(owner is not None and all(labels.get(key) == value for key, value in tags(plan, owner).items()),
                 'Foreign resource; no adoption or mutation')
        found[kind] = resources
    return found


def state_read(plan):
    root = Path(plan['root'])
    verify_private(root, directory=True)
    pending_guard(root)
    state = read_private(root / 'state.json')
    keys(state, {'kind', 'owner', 'plan_id', 'status', 'recovery'}, 'Paperless state')
    need(state['kind'] == 'paperless-owned-v1' and state['plan_id'] == plan['plan_id'],
         'Ownership mismatch')
    need(isinstance(state['owner'], str) and re.fullmatch('[0-9a-f]{32}', state['owner']), 'Invalid owner')
    need(state['status'] in ('prepared', 'restoring', 'running', 'stopped', 'removing', 'removed'),
         'Invalid state')
    credentials = validate_credentials(read_private(root / 'credentials.json'))
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
    owner = uuid.uuid4().hex
    state = {'kind': 'paperless-owned-v1', 'owner': owner, 'plan_id': plan['plan_id'],
             'status': 'prepared', 'recovery': None}
    atomic_json(root / 'credentials.json', credentials)
    atomic_json(root / 'compose.json', compose(plan, owner, credentials))
    atomic_json(root / 'state.json', state)
    return state


def wait_health(plan, roles, deadline_seconds=300):
    deadline = time.monotonic() + deadline_seconds
    context = plan['runtime']['context']
    while time.monotonic() < deadline:
        ids = docker(compose_args(plan) + ['ps', '-q'] + list(roles), context=context).split()
        if len(ids) == len(roles):
            values = [docker(['inspect', '--format',
                              '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}', value],
                             context=context) for value in ids]
            if all(value == 'healthy' for value in values):
                return
            need(not any(value in ('exited', 'dead') for value in values),
                 'Paperless service exited before becoming healthy')
        time.sleep(2)
    raise ConfigError('Paperless services did not become healthy before the bounded deadline')


INVENTORY_SCRIPT = (
    "import hashlib,json; from documents.models import Document; "
    "rows=[]; "
    "[(rows.append({'title':d.title,'checksum':d.checksum,'original_filename':d.original_filename,"
    "'tags':sorted(d.tags.values_list('name',flat=True)),'file_sha256':hashlib.sha256(open(d.source_path,'rb').read()).hexdigest(),"
    "'content_marker':('HomeLab Paperless recovery validation' in (d.content or ''))})) for d in Document.objects.order_by('id')]; "
    "print(json.dumps({'documents':len(rows),'rows':rows},sort_keys=True))"
)


def content_inventory(plan, *, one_off=False):
    context = plan['runtime']['context']
    command = (['run', '--rm', '--no-deps', '--entrypoint', 's6-setuidgid', 'paperless',
                'paperless', 'python3', '/usr/src/paperless/src/manage.py', 'shell', '-c', INVENTORY_SCRIPT]
               if one_off else ['exec', '-T', 'paperless', 'python3', 'manage.py', 'shell', '-c',
                                INVENTORY_SCRIPT])
    output = docker(compose_args(plan) + command,
                    context=context, timeout=300)
    rows = [line for line in output.splitlines() if line.startswith('{')]
    need(bool(rows), 'Paperless content inventory returned no bounded JSON result')
    value = json.loads(rows[-1])
    need(type(value.get('documents')) is int and isinstance(value.get('rows'), list),
         'Paperless content inventory is invalid')
    return value


def backup_summary(manifest):
    return {'documents': manifest['inventory']['documents'],
            'titles': sorted(row['title'] for row in manifest['inventory']['rows']),
            'checksums': sorted(row['checksum'] for row in manifest['inventory']['rows']),
            'content_fingerprint': digest(manifest['inventory'])}


def operate(plan, action, confirmation=None):
    validate_plan(plan)
    need(action in ('up', 'status', 'stop', 'remove'), 'Unsupported Paperless action')
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
        need(state['status'] != 'restoring', 'Interrupted restore requires manual evidence review and a fresh target')
        if action == 'up':
            need(state['status'] not in ('removing', 'removed'), 'Removed deployments require a fresh root')
            if not containers:
                need(state['status'] == 'prepared' and (not resources['volumes'] or not plan['recovery']),
                     'Recorded resources missing; no silent recreation')
                port_free(plan['port'])
                docker(compose_args(plan) + ['create', '--pull', 'never', '--no-build'], context=context, timeout=300)
                resources = inventory(plan, state['owner'])
                containers = resources['containers']
            need(set(containers) == set(SERVICES) and len(resources['volumes']) == len(VOLUMES),
                 'Incomplete Paperless creation; retain state for review')
            need(not any(row['State'].get('Paused') for row in containers.values()),
                 'Paused state requires manual review')
            if plan['recovery'] and state['status'] == 'prepared':
                need(not any(row['State']['Running'] for row in containers.values()),
                     'Recovery must target never-started application containers')
                state['status'] = 'restoring'
                atomic_json(root / 'state.json', state, replace=True)
                # Initialize the empty schema and volume ownership once, then quiesce
                # the application before invoking the supported importer.
                docker(compose_args(plan) + ['start', 'broker', 'database', 'paperless'], context=context)
                wait_health(plan, SERVICES)
                docker(compose_args(plan) + ['stop', '--timeout', '60', 'paperless'],
                       context=context, timeout=120)
                docker(compose_args(plan) + ['run', '--rm', '--no-deps', '--entrypoint',
                       's6-setuidgid', 'paperless', 'paperless', 'python3',
                       '/usr/src/paperless/src/manage.py', 'document_importer',
                       '/restore-import', '--no-progress-bar'],
                       context=context, timeout=900)
                state['status'] = 'prepared'
                atomic_json(root / 'state.json', state, replace=True)
            port_free(plan['port'])
            docker(compose_args(plan) + ['up', '-d', '--no-build', '--pull', 'never'],
                   context=context, timeout=300)
            wait_health(plan, SERVICES)
            if plan['recovery']:
                restored = content_inventory(plan)
                source = verify_backup(Path(plan['recovery']['path']))
                need(restored == source['inventory'], 'Restored Paperless content differs from backup evidence')
                state['recovery'] = {'manifest_id': plan['recovery']['manifest_id'],
                                     'verified': True, 'summary': backup_summary(source)}
            state['status'] = 'running'
        elif action == 'stop':
            need(set(containers) == set(SERVICES) and state['status'] not in ('removing', 'removed'),
                 'No complete owned deployment to stop')
            need(not any(row['State'].get('Paused') for row in containers.values()),
                 'Paused state requires manual review')
            docker(compose_args(plan) + ['stop', '--timeout', '60'], context=context, timeout=120)
            state['status'] = 'stopped'
        elif action == 'remove':
            need(not any(row['State']['Running'] for row in containers.values()),
                 'Stop all owned services before removal')
            if state['status'] != 'removed':
                state['status'] = 'removing'
                atomic_json(root / 'state.json', state, replace=True)
                docker(compose_args(plan) + ['down', '--remove-orphans'], context=context, timeout=120)
                state['status'] = 'removed'
        if action != 'status' and read_private(root / 'state.json') != state:
            atomic_json(root / 'state.json', state, replace=True)
        resources = inventory(plan, state['owner'])
        health = {}
        for role, row in resources['containers'].items():
            health[role] = (row['State'].get('Health') or {}).get('Status', row['State']['Status'])
        return {'module': 'paperless-ngx', 'state': state['status'], 'health': health,
                'url': 'http://127.0.0.1:' + str(plan['port']),
                'data_volumes_retained': len(resources['volumes']), 'recovery': state['recovery']}


def synthetic_pdf():
    marker = b'HomeLab Paperless recovery validation'
    stream = b'BT /F1 16 Tf 24 140 Td (' + marker + b') Tj ET\n'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'endstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    result = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(result)); result.extend(f'{index} 0 obj\n'.encode() + body + b'\nendobj\n')
    xref = len(result); result.extend(f'xref\n0 {len(objects)+1}\n'.encode()); result.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        result.extend(f'{offset:010d} 00000 n \n'.encode())
    result.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(result)


def stage_consume_fixture(context, container, fixture):
    staged = '/usr/src/paperless/consume/.paperless-recovery-fixture.uploading'
    destination = '/usr/src/paperless/consume/paperless-recovery-fixture.pdf'
    docker(['cp', str(fixture), container + ':' + staged], context=context)
    docker(['exec', container, 'chown', 'paperless:paperless', staged], context=context)
    docker(['exec', container, 'chmod', '0600', staged], context=context)
    docker(['exec', container, 'mv', '--', staged, destination], context=context)


def exercise(plan, confirmation):
    validate_plan(plan)
    need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        need(state['status'] == 'running' and set(resources['containers']) == set(SERVICES),
             'Start the complete owned Paperless project before exercise')
        need(content_inventory(plan)['documents'] == 0, 'Synthetic exercise requires an empty fresh project')
        fixture = root / 'paperless-recovery-fixture.pdf'
        fixture.write_bytes(synthetic_pdf())
        if os.name == 'nt':
            windows_acl(fixture, create=True)
        else:
            fixture.chmod(0o600)
        verify_private(fixture)
        expected_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
        context = plan['runtime']['context']
        try:
            web = resources['containers']['paperless']['Id']
            stage_consume_fixture(context, web, fixture)
            deadline = time.monotonic() + 300
            value = {'documents': 0, 'rows': []}
            while time.monotonic() < deadline:
                time.sleep(3)
                value = content_inventory(plan)
                if value['documents'] == 1:
                    break
            need(value['documents'] == 1, 'Synthetic document was not consumed before the bounded deadline')
            update = ("from documents.models import Document,Tag; d=Document.objects.get(); "
                      "d.title='Phase 5 Recovery Fixture'; d.save(); "
                      "t,_=Tag.objects.get_or_create(name='phase5-recovery'); d.tags.add(t)")
            docker(compose_args(plan) + ['exec', '-T', 'paperless', 'python3', 'manage.py', 'shell', '-c', update],
                   context=context, timeout=120)
            value = content_inventory(plan)
            row = value['rows'][0]
            need(row['title'] == 'Phase 5 Recovery Fixture' and row['tags'] == ['phase5-recovery'],
                 'Synthetic metadata edit did not persist')
            need(row['checksum'] == expected_hash and row['file_sha256'] == expected_hash,
                 'Stored synthetic document checksum differs from uploaded content')
            need(row['content_marker'], 'Synthetic document searchable text was not recovered')
            return {'operation': 'upload-open-edit-search', 'status': 'passed',
                    'documents': 1, 'title': row['title'], 'tags': row['tags'],
                    'sha256': expected_hash, 'searchable_content_verified': True}
        finally:
            if fixture.exists():
                fixture.unlink()


def file_hash(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def tree_files(root, *, protect_new=False):
    root = safe_path(root)
    verify_private(root, directory=True)
    result = {}
    for path in sorted(root.rglob('*')):
        safe_path(path)
        info = path.stat()
        need(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), 'Unexpected backup resource')
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


def verify_backup(root):
    root = safe_path(Path(root))
    verify_private(root, directory=True)
    manifest = read_private(root / 'manifest.json')
    keys(manifest, {'kind', 'created_utc', 'images', 'method', 'secondary_material',
                    'consistency', 'recovery_status', 'credentials_hash', 'configuration_sha256',
                    'database_sha256', 'trees', 'inventory', 'summary'}, 'Paperless backup manifest')
    need(manifest['kind'] == 'paperless-consistent-backup-v1' and manifest['images'] == images()
         and manifest['method'] == 'document-exporter-importer', 'Backup image/format mismatch')
    need(manifest['consistency'] == {'application_quiesced': True, 'document_export_complete': True,
                                     'postgres_archive_readable': True, 'filesystem_copy_complete': True}
         and manifest['recovery_status'] == 'pending-independent-restore',
         'Backup consistency/recovery evidence is incomplete')
    credentials = validate_credentials(read_private(root / 'credentials.json'))
    need(digest(credentials) == manifest['credentials_hash'], 'Backup credential checksum mismatch')
    need(file_hash(root / 'paperless-postgres.dump') == manifest['database_sha256'],
         'PostgreSQL dump checksum mismatch')
    need(manifest['configuration_sha256'] == {
        'private': file_hash(root / 'compose.private.json'),
        'sanitized': file_hash(root / 'sanitized-config.json')},
         'Backup configuration checksum mismatch')
    expected = {'document-export': tree_files(root / 'document-export'),
                **{name: tree_files(root / 'filesystem' / name) for name in ('data', 'media', 'export')}}
    need(expected == manifest['trees'], 'Backup content checksum mismatch')
    need(manifest['inventory']['documents'] > 0 and backup_summary(manifest) == manifest['summary'],
         'Backup lacks nonempty semantic recovery evidence')
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
             'Start the complete owned Paperless project before backup')
        need(content_inventory(plan)['documents'] > 0, 'Recovery certification requires nonempty synthetic content')
        context = plan['runtime']['context']
        stage = '.homelab-backup-' + uuid.uuid4().hex
        export_target = '/usr/src/paperless/export/' + stage
        web = resources['containers']['paperless']['Id']
        database = resources['containers']['database']['Id']
        web_stopped = False
        export_stage_present = False
        failed_stage = 'quiesce'
        create_private_directory(destination)
        try:
            failed_stage = 'quiesce'
            docker(compose_args(plan) + ['stop', '--timeout', '60', 'paperless'],
                   context=context, timeout=120)
            web_stopped = True
            failed_stage = 'export-target'
            docker(compose_args(plan) + ['run', '--rm', '--no-deps', '--entrypoint',
                   's6-setuidgid', 'paperless', 'paperless', 'mkdir', '-p', export_target],
                   context=context, timeout=120)
            export_stage_present = True
            failed_stage = 'document-exporter'
            docker(compose_args(plan) + ['run', '--rm', '--no-deps', '--entrypoint',
                   's6-setuidgid', 'paperless', 'paperless', 'python3',
                   '/usr/src/paperless/src/manage.py', 'document_exporter',
                   export_target, '--no-progress-bar'],
                   context=context, timeout=900)
            failed_stage = 'semantic-inventory'
            inventory_value = content_inventory(plan, one_off=True)
            need(inventory_value['documents'] > 0, 'Exporter backup is empty; refusing certification')
            dump_target = '/tmp/paperless-' + uuid.uuid4().hex + '.dump'
            failed_stage = 'postgres-dump'
            docker(['exec', database, 'pg_dump', '-U', 'paperless', '-d', 'paperless',
                    '--format', 'custom', '--file', dump_target], context=context, timeout=300)
            failed_stage = 'postgres-archive-check'
            docker(['exec', database, 'pg_restore', '--list', dump_target], context=context, timeout=120)
            failed_stage = 'postgres-copy'
            docker(['cp', database + ':' + dump_target, str(destination / 'paperless-postgres.dump')],
                   context=context, timeout=120)
            docker(['exec', database, 'rm', '-f', dump_target], context=context)
            failed_stage = 'document-export-copy'
            create_private_directory(destination / 'document-export')
            docker(['cp', web + ':' + export_target + '/.', str(destination / 'document-export')],
                   context=context, timeout=300)
            docker(compose_args(plan) + ['run', '--rm', '--no-deps', '--entrypoint', 'rm',
                   'paperless', '-rf', '--', export_target], context=context, timeout=120)
            export_stage_present = False
            failed_stage = 'filesystem-copy'
            create_private_directory(destination / 'filesystem')
            for name in ('data', 'media', 'export'):
                create_private_directory(destination / 'filesystem' / name)
                docker(['cp', web + ':' + AREAS[name] + '/.', str(destination / 'filesystem' / name)],
                       context=context, timeout=300)
            failed_stage = 'metadata-copy'
            shutil.copy2(root / 'credentials.json', destination / 'credentials.json')
            shutil.copy2(root / 'compose.json', destination / 'compose.private.json')
            atomic_json(destination / 'sanitized-config.json', {
                'kind': 'paperless-sanitized-configuration-v1', 'images': plan['images'],
                'limits': plan['limits'], 'access': plan['access'], 'mail': plan['mail'],
                'signups': plan['signups'], 'recovery_method': plan['recovery_method'],
            })
            for child in ('document-export', 'filesystem'):
                tree_files(destination / child, protect_new=True)
            failed_stage = 'private-permissions'
            if os.name == 'nt':
                windows_acl(destination / 'credentials.json', create=True)
                windows_acl(destination / 'compose.private.json', create=True)
                windows_acl(destination / 'paperless-postgres.dump', create=True)
            else:
                (destination / 'credentials.json').chmod(0o600)
                (destination / 'compose.private.json').chmod(0o600)
                (destination / 'paperless-postgres.dump').chmod(0o600)
            verify_private(destination / 'credentials.json')
            verify_private(destination / 'compose.private.json')
            verify_private(destination / 'paperless-postgres.dump')
            trees = {'document-export': tree_files(destination / 'document-export'),
                     **{name: tree_files(destination / 'filesystem' / name)
                        for name in ('data', 'media', 'export')}}
            manifest = {'kind': 'paperless-consistent-backup-v1',
                        'created_utc': datetime.now(timezone.utc).isoformat(),
                        'images': plan['images'],
                        'method': 'document-exporter-importer',
                        'secondary_material': ['postgres-custom-dump', 'data', 'media', 'export'],
                        'consistency': {'application_quiesced': True,
                                        'document_export_complete': True,
                                        'postgres_archive_readable': True,
                                        'filesystem_copy_complete': True},
                        'recovery_status': 'pending-independent-restore',
                        'credentials_hash': digest(read_private(destination / 'credentials.json')),
                        'configuration_sha256': {
                            'private': file_hash(destination / 'compose.private.json'),
                            'sanitized': file_hash(destination / 'sanitized-config.json')},
                        'database_sha256': file_hash(destination / 'paperless-postgres.dump'),
                        'trees': trees, 'inventory': inventory_value, 'summary': None}
            manifest['summary'] = backup_summary(manifest)
            atomic_json(destination / 'manifest.json', manifest)
            failed_stage = 'manifest-verification'
            verify_backup(destination)
        except ConfigError as error:
            raise ConfigError('Paperless backup failed during ' + failed_stage
                              + '; sensitive partial state was retained for review') from error
        finally:
            if export_stage_present:
                try:
                    docker(compose_args(plan) + ['run', '--rm', '--no-deps', '--entrypoint', 'rm',
                           'paperless', '-rf', '--', export_target],
                           context=context, timeout=120)
                except ConfigError:
                    pass
            if web_stopped:
                docker(compose_args(plan) + ['start', 'paperless'], context=context, timeout=120)
                wait_health(plan, ('paperless',))
        return {'backup_complete': True, 'application_consistent': True, 'encrypted': False,
                'contains_credentials': True, 'summary': manifest['summary'],
                'recovery_verified': False,
                'note': 'Sensitive local staging backup; restore into a fresh project before encrypted off-host retention'}
