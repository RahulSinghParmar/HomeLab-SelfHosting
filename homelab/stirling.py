"""Isolated Stirling-PDF 2.14.2 lifecycle, synthetic PDF exercise and recovery."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import urllib.error
import urllib.request
import uuid
import zlib

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .doctor import host_platform
from .glance import docker, local_runtime, port_free
from .privatefs import (atomic_json, create_lock_file, create_private_directory,
                        operation_lock, read_private, safe_path, verify_private, windows_acl)
from .sandbox import digest, pending_guard


MODULE = ROOT / 'modules/stirling-pdf'
AREAS = {
    'configs': '/configs',
    'custom-files': '/customFiles',
    'logs': '/logs',
    'pipeline': '/pipeline',
    'tessdata': '/usr/share/tesseract-ocr/5/tessdata',
}
MEMORY_MIB = 1536
CPUS = 2
PIDS = 512


def docker_capabilities(values):
    """Return capability names in the normalized form emitted by Docker inspect."""
    return {value if value.startswith('CAP_') else 'CAP_' + value for value in values}


def expected_tmpfs():
    return {
        '/tmp': 'rw,nosuid,size=512m',
        '/storage': 'rw,noexec,nosuid,size=256m',
        '/home/stirlingpdfuser': 'rw,nosuid,size=256m',
        '/usr/local/bin': 'rw,nosuid,size=2m',
    }


def expected_healthcheck():
    return {
        'Test': ['CMD-SHELL',
                 'curl -fs --max-time 10 http://localhost:8080/api/v1/info/status || exit 1'],
        'Interval': 30_000_000_000,
        'Timeout': 15_000_000_000,
        'StartPeriod': 120_000_000_000,
        'Retries': 5,
    }


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
        recovery = {'path': str(source), 'manifest_id': digest(manifest)}
    plan = {
        'kind': 'homelab-stirling-plan', 'contract': 'stirling-isolated-v1',
        'platform': host_platform(), 'root': str(root), 'port': port, 'runtime': runtime,
        'image': load_json(MODULE / 'image.json')['image'], 'recovery': recovery,
        'limits': {'memory_mib': MEMORY_MIB, 'cpus': CPUS, 'pids': PIDS,
                   'java_initial_mib': 128, 'java_heap_mib': 768, 'metaspace_mib': 192,
                   'upload_mib': 50},
        'access': 'loopback', 'network': 'dedicated-bridge-outbound-allowed',
        'docker_socket': False, 'authentication': 'disabled-loopback-trial-only',
        'capabilities': ['CHOWN', 'SETGID', 'SETUID'],
    }
    plan['plan_id'] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'root', 'port', 'runtime', 'image', 'recovery',
                'limits', 'access', 'network', 'docker_socket', 'authentication', 'capabilities', 'plan_id'},
         'Stirling-PDF plan')
    backup = plan['recovery']['path'] if plan['recovery'] is not None else None
    need(canonical(plan) == canonical(make_plan(plan['root'], plan['port'], plan['runtime'], backup)),
         'Plan/image/recovery drift; review a new plan')
    return plan


def project(plan):
    return 'hl-stirling-' + plan['plan_id'][:16]


def tags(plan, owner):
    return {'org.homelab.owner': owner, 'org.homelab.plan': plan['plan_id'],
            'org.homelab.module': 'stirling-pdf'}


def compose(plan, owner):
    environment = {
        'TZ': 'UTC', 'SECURITY_ENABLELOGIN': 'false', 'SYSTEM_ENABLEANALYTICS': 'false',
        'SYSTEM_GOOGLEVISIBILITY': 'false', 'SYSTEM_DEFAULTLOCALE': 'en-GB',
        'SYSTEM_ENABLEALPHAFUNCTIONALITY': 'false', 'SPRINGDOC_API_DOCS_ENABLED': 'false',
        'SPRINGDOC_SWAGGER_UI_ENABLED': 'false', 'STIRLING_AOT_ENABLE': 'false',
        'STIRLING_JVM_PROFILE': 'balanced', 'SYSTEMFILEUPLOADLIMIT': '50MB',
        'JAVA_CUSTOM_OPTS': '-Xms128m -Xmx768m -XX:MaxMetaspaceSize=192m -XX:+UseG1GC',
        'UMASK': '027', 'PUID': '1001', 'PGID': '1001',
    }
    volumes = []
    for name, target in AREAS.items():
        volumes.append({'type': 'volume', 'source': name, 'target': target,
                        'volume': {'nocopy': name != 'tessdata'}})
    service = {
        'image': plan['image'], 'labels': tags(plan, owner), 'pull_policy': 'never',
        'restart': 'unless-stopped', 'read_only': True, 'cap_drop': ['ALL'],
        'cap_add': plan['capabilities'],
        'security_opt': ['no-new-privileges:true'], 'pids_limit': PIDS,
        'mem_limit': f'{MEMORY_MIB}m', 'cpus': CPUS, 'environment': environment,
        'tmpfs': ['/tmp:rw,nosuid,size=512m', '/storage:rw,noexec,nosuid,size=256m',
                  '/home/stirlingpdfuser:rw,nosuid,size=256m', '/usr/local/bin:rw,nosuid,size=2m'],
        'volumes': volumes,
        'ports': [{'target': 8080, 'published': str(plan['port']), 'host_ip': '127.0.0.1', 'protocol': 'tcp'}],
        'healthcheck': {'test': ['CMD-SHELL', 'curl -fs --max-time 10 http://localhost:8080/api/v1/info/status || exit 1'],
                        'interval': '30s', 'timeout': '15s', 'start_period': '120s', 'retries': 5},
        'logging': {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '2'}},
    }
    return {'services': {'stirling': service},
            'volumes': {name: {'labels': tags(plan, owner)} for name in AREAS},
            'networks': {'default': {'driver': 'bridge', 'labels': tags(plan, owner)}}}


def inventory(plan, owner):
    context = plan['runtime']['context']
    found = {'containers': {}, 'networks': [], 'volumes': []}
    for kind, query, inspect in (
        ('containers', ['ps', '-aq'], ['inspect']),
        ('networks', ['network', 'ls', '-q'], ['network', 'inspect']),
        ('volumes', ['volume', 'ls', '-q'], ['volume', 'inspect'])):
        ids = docker(query + ['--filter', 'label=com.docker.compose.project=' + project(plan)], context=context).split()
        need(len(ids) <= (1 if kind in ('containers', 'networks') else len(AREAS)),
             'Unexpected Stirling-PDF project resources')
        rows = json.loads(docker(inspect + ids, context=context)) if ids else []
        for row in rows:
            labels = (row['Config']['Labels'] if kind == 'containers' else row['Labels']) or {}
            need(owner is not None and all(labels.get(key) == value for key, value in tags(plan, owner).items()),
                 'Foreign resource; no adoption or mutation')
            if kind == 'containers':
                role = labels.get('com.docker.compose.service')
                need(role == 'stirling' and role not in found[kind], 'Unexpected or duplicate service')
                need(row['Config']['Image'] == plan['image'], 'Image drift')
                host = row['HostConfig']
                need(host['ReadonlyRootfs'] and not host['Privileged'] and host['CapDrop'] == ['ALL']
                     and docker_capabilities(host.get('CapAdd') or []) == docker_capabilities(plan['capabilities'])
                     and not host.get('Devices') and not host.get('DeviceRequests'),
                     'Privilege/device drift')
                need('no-new-privileges:true' in host['SecurityOpt'] and host['PidsLimit'] == PIDS,
                     'Security/process drift')
                need(host.get('Tmpfs') == expected_tmpfs(), 'Temporary-filesystem drift')
                need((row['Config'].get('Healthcheck') or {}) == expected_healthcheck(),
                     'Health-check drift')
                need(host['Memory'] == MEMORY_MIB * 1024**2 and host['NanoCpus'] == CPUS * 1_000_000_000,
                     'Resource drift')
                need(host['RestartPolicy']['Name'] == 'unless-stopped'
                     and host['LogConfig'] == {'Type': 'json-file', 'Config': {'max-size': '10m', 'max-file': '2'}},
                     'Lifecycle/logging drift')
                expected_ports = {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(plan['port'])}]}
                need((host['PortBindings'] or {}) == expected_ports, 'Port binding drift')
                if row['State']['Running']:
                    need(row['NetworkSettings']['Ports'].get('8080/tcp') == expected_ports['8080/tcp'],
                         'Requested port not actually published')
                need(set(row['NetworkSettings']['Networks']) == {project(plan) + '_default'}, 'Unexpected network')
                mounts = [mount for mount in row['Mounts'] if mount['Type'] != 'tmpfs']
                expected = {project(plan) + '_' + name: target for name, target in AREAS.items()}
                actual = {mount['Name']: mount['Destination'] for mount in mounts if mount['Type'] == 'volume'}
                need(actual == expected and all(mount['RW'] for mount in mounts), 'Persistent-volume drift')
                need(set(mount['Destination'] for mount in row['Mounts']) <= set(AREAS.values())
                     | {'/tmp', '/storage', '/home/stirlingpdfuser', '/usr/local/bin'}, 'Unexpected mount')
                required_environment = {f'{key}={value}' for key, value in compose(plan, owner)['services']['stirling']['environment'].items()}
                need(required_environment <= set(row['Config']['Env']), 'Environment drift')
                found[kind][role] = row
            elif kind == 'networks':
                need(row['Name'] == project(plan) + '_default' and not row['Internal']
                     and row['Driver'] == 'bridge', 'Network drift')
                need(set(row.get('Containers') or {}) <= {container['Id'] for container in found['containers'].values()},
                     'Foreign network attachment')
                found[kind].append(row)
            else:
                expected_names = {project(plan) + '_' + name for name in AREAS}
                need(row['Name'] in expected_names and row['Driver'] == 'local' and not row.get('Options'),
                     'Volume drift')
                attached = docker(['ps', '-aq', '--no-trunc', '--filter', 'volume=' + row['Name']],
                                  context=context).split()
                need(set(attached) <= {container['Id'] for container in found['containers'].values()},
                     'Foreign volume attachment')
                found[kind].append(row)
    return found


def state_read(plan):
    root = Path(plan['root'])
    verify_private(root, directory=True)
    pending_guard(root)
    state = read_private(root / 'state.json')
    keys(state, {'kind', 'owner', 'plan_id', 'status'}, 'Stirling-PDF state')
    need(state['kind'] == 'stirling-owned-v1' and state['plan_id'] == plan['plan_id'], 'Ownership mismatch')
    need(isinstance(state['owner'], str) and re.fullmatch('[0-9a-f]{32}', state['owner']), 'Invalid owner')
    need(state['status'] in ('prepared', 'restore-copying', 'ready', 'running', 'stopped', 'removing', 'removed'),
         'Invalid state')
    need(read_private(root / 'compose.json') == compose(plan, state['owner']), 'Compose modified; refusing execution')
    return state


def prepare(plan):
    root = Path(plan['root'])
    if root.exists():
        return state_read(plan)
    inventory(plan, None)
    context = plan['runtime']['context']
    names = [project(plan) + '_default', *(project(plan) + '_' + name for name in AREAS)]
    existing_networks = set(docker(['network', 'ls', '--format', '{{.Name}}'], context=context).splitlines())
    existing_volumes = set(docker(['volume', 'ls', '--format', '{{.Name}}'], context=context).splitlines())
    need(names[0] not in existing_networks and not set(names[1:]) & existing_volumes,
         'Unowned resource name collision')
    port_free(plan['port'])
    image = json.loads(docker(['image', 'inspect', plan['image']], context=context))[0]
    need(image['Os'] == 'linux' and image['Architecture'] == 'amd64',
         'Reviewed linux/amd64 image must be cached')
    create_private_directory(root)
    create_lock_file(root / 'operation.lock')
    state = {'kind': 'stirling-owned-v1', 'owner': uuid.uuid4().hex,
             'plan_id': plan['plan_id'], 'status': 'prepared'}
    atomic_json(root / 'compose.json', compose(plan, state['owner']))
    atomic_json(root / 'state.json', state)
    return state


def operate(plan, action, confirmation=None):
    validate_plan(plan)
    need(action in ('up', 'status', 'stop', 'remove'), 'Unsupported Stirling-PDF action')
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
            need(state['status'] not in ('removing', 'removed'), 'Removed deployments require a new recovery root')
            if not containers:
                need(state['status'] == 'prepared' and (not resources['volumes'] or plan['recovery'] is None),
                     'Recorded resources missing; no silent recreation')
                port_free(plan['port'])
                docker(['compose', '--project-name', project(plan), '--project-directory', str(root),
                        '-f', str(root / 'compose.json'), 'create', '--pull', 'never', '--no-build'], context=context)
                resources = inventory(plan, state['owner'])
                containers = resources['containers']
            need(set(containers) == {'stirling'} and len(resources['volumes']) == len(AREAS),
                 'Incomplete service creation; retain state for review')
            if plan['recovery'] and state['status'] == 'prepared':
                need(not containers['stirling']['State']['Running'],
                     'Recovery must target a never-started container')
                state['status'] = 'restore-copying'
                atomic_json(root / 'state.json', state, replace=True)
                for name, target in AREAS.items():
                    docker(['cp', str(Path(plan['recovery']['path']) / name) + '/.',
                            containers['stirling']['Id'] + ':' + target + '/'], context=context)
                state['status'] = 'ready'
                atomic_json(root / 'state.json', state, replace=True)
            container = containers['stirling']
            need(not container['State'].get('Paused'), 'Paused container needs explicit review')
            if not container['State']['Running']:
                port_free(plan['port'])
                docker(['start', container['Id']], context=context)
            state['status'] = 'running'
        elif action == 'stop':
            need(bool(containers) and state['status'] not in ('removing', 'removed'),
                 'No owned deployment to stop')
            container = containers['stirling']
            need(not container['State'].get('Paused'), 'Paused state requires review')
            if container['State']['Running']:
                docker(['stop', '--time', '45', container['Id']], context=context)
            state['status'] = 'stopped'
        elif action == 'remove':
            need(not any(container['State']['Running'] for container in containers.values()),
                 'Stop the owned service before removal')
            if state['status'] != 'removed':
                state['status'] = 'removing'
                atomic_json(root / 'state.json', state, replace=True)
                for container in containers.values():
                    docker(['rm', container['Id']], context=context)
                for network in inventory(plan, state['owner'])['networks']:
                    docker(['network', 'rm', network['Id']], context=context)
                state['status'] = 'removed'
        if action != 'status' and read_private(root / 'state.json') != state:
            atomic_json(root / 'state.json', state, replace=True)
        resources = inventory(plan, state['owner'])
        container = resources['containers'].get('stirling')
        health = ((container or {}).get('State', {}).get('Health') or {}).get('Status')
        return {'module': 'stirling-pdf', 'state': state['status'],
                'service': container['State']['Status'] if container else 'removed',
                'health': health or 'not-available', 'url': 'http://127.0.0.1:' + str(plan['port']),
                'data_volumes_retained': len(resources['volumes'])}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def synthetic_pdf():
    stream = b'BT /F1 18 Tf 24 140 Td (HomeLab Stirling-PDF validation) Tj ET\n'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'endstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    result = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f'{index} 0 obj\n'.encode() + body + b'\nendobj\n')
    xref = len(result)
    result.extend(f'xref\n0 {len(objects) + 1}\n'.encode())
    result.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        result.extend(f'{offset:010d} 00000 n \n'.encode())
    result.extend(f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(result)


def multipart_rotation(pdf):
    boundary = '----HomeLabStirlingValidationBoundary'
    chunks = []
    for headers, value in (
        ([f'Content-Disposition: form-data; name="fileInput"; filename="fixture.pdf"',
          'Content-Type: application/pdf'], pdf),
        (['Content-Disposition: form-data; name="angle"'], b'90')):
        chunks.append(('--' + boundary + '\r\n' + '\r\n'.join(headers) + '\r\n\r\n').encode()
                      + value + b'\r\n')
    chunks.append(('--' + boundary + '--\r\n').encode())
    return boundary, b''.join(chunks)


def pdf_syntax(pdf):
    """Expose bounded Flate-compressed PDF syntax for structural assertions."""
    fragments = [pdf]
    total = len(pdf)
    for match in re.finditer(rb'stream\r?\n(.*?)\r?\nendstream', pdf, re.DOTALL):
        header = pdf[max(0, match.start() - 512):match.start()]
        if b'/FlateDecode' not in header:
            continue
        try:
            inflater = zlib.decompressobj()
            expanded = inflater.decompress(match.group(1), 2_000_001)
            need(not inflater.unconsumed_tail, 'Synthetic PDF contains an oversized compressed stream')
            expanded += inflater.flush()
        except zlib.error as error:
            raise ConfigError('Synthetic PDF contains an invalid compressed stream') from error
        need(len(expanded) <= 2_000_000 and total + len(expanded) <= 4_000_000,
             'Synthetic PDF expanded syntax exceeds its validation bound')
        fragments.append(expanded)
        total += len(expanded)
    return b'\n'.join(fragments)


def exercise(plan, confirmation):
    validate_plan(plan)
    need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        container = resources['containers'].get('stirling')
        need(state['status'] == 'running' and container and container['State']['Running']
             and not container['State'].get('Paused'), 'Stirling-PDF is not running')
        source = synthetic_pdf()
        boundary, body = multipart_rotation(source)
        request = urllib.request.Request(
            f"http://127.0.0.1:{plan['port']}/api/v1/general/rotate-pdf", data=body, method='POST',
            headers={'Content-Type': 'multipart/form-data; boundary=' + boundary,
                     'Content-Length': str(len(body)), 'User-Agent': 'HomeLab-Stirling-Validation/1'})
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=45) as response:
                content_type = response.headers.get_content_type()
                output = response.read(2_000_001)
                status = response.status
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise ConfigError('Synthetic PDF request failed; no response details exposed') from error
        need(status == 200 and content_type == 'application/pdf' and len(output) <= 2_000_000,
             'Synthetic PDF response contract failed')
        syntax = pdf_syntax(output)
        need(output.startswith(b'%PDF-') and b'%%EOF' in output[-1024:]
             and re.search(rb'/Rotate\s+90\b', syntax),
             'Synthetic PDF output is not a verified 90-degree rotation')
        return {'operation': 'rotate-pdf', 'status': 'passed', 'input_bytes': len(source),
                'output_bytes': len(output), 'output_sha256': hashlib.sha256(output).hexdigest(),
                'rotation_degrees': 90, 'persistent_input_retained': False}


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
    trees = {name: tree_files(root / name) for name in AREAS}
    need('settings.yml' in trees['configs'], 'Snapshot has no generated Stirling-PDF settings')
    need(bool(trees['tessdata']), 'Snapshot has no OCR language data')
    counts = {name: len(files) for name, files in trees.items()}
    bytes_by_area = {name: sum((root / name / relative).stat().st_size for relative in files)
                     for name, files in trees.items()}
    return {'file_counts': counts, 'bytes_by_area': bytes_by_area,
            'content_fingerprint': digest(trees), 'settings_present': True}


def verify_backup(root):
    root = safe_path(root)
    verify_private(root, directory=True)
    manifest = read_private(root / 'manifest.json')
    keys(manifest, {'kind', 'image', 'trees', 'summary'}, 'Stirling-PDF backup manifest')
    need(manifest['kind'] == 'stirling-stopped-backup-v1'
         and manifest['image'] == load_json(MODULE / 'image.json')['image'], 'Backup image/format mismatch')
    actual = {name: tree_files(root / name) for name in AREAS}
    need(actual == manifest['trees'], 'Backup content checksum mismatch')
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
        need(state['status'] == 'stopped' and set(resources['containers']) == {'stirling'}
             and not resources['containers']['stirling']['State']['Running'],
             'Stop the owned service before backup')
        create_private_directory(destination)
        for name, target in AREAS.items():
            create_private_directory(destination / name)
            docker(['cp', resources['containers']['stirling']['Id'] + ':' + target + '/.',
                    str(destination / name)], context=plan['runtime']['context'])
            tree_files(destination / name, protect_new=True)
        trees = {name: tree_files(destination / name) for name in AREAS}
        summary = snapshot_summary(destination)
        atomic_json(destination / 'manifest.json', {'kind': 'stirling-stopped-backup-v1',
                    'image': plan['image'], 'trees': trees, 'summary': summary})
        verify_backup(destination)
        return {'backup_complete': True, 'encrypted': False, 'contains_authentication_state': True,
                'summary': summary, 'recovery_verified': False,
                'note': 'Restore into a fresh project and rerun the synthetic PDF exercise'}
