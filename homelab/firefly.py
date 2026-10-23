"""Isolated Firefly III lifecycle, synthetic finance exercise and consistent recovery."""
from __future__ import annotations

import base64
from decimal import Decimal, InvalidOperation
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


MODULE = ROOT / 'modules/firefly-iii'
SERVICES = ('database', 'app', 'cron')
APP_AREAS = {
    'upload': '/var/www/html/storage/upload',
    'export': '/var/www/html/storage/export',
}
VOLUMES = ('database-data', *APP_AREAS)
LIMITS = {
    'database': {'memory_mib': 512, 'cpus': 1.0, 'pids': 192},
    'app': {'memory_mib': 1024, 'cpus': 2.0, 'pids': 512},
    'cron': {'memory_mib': 64, 'cpus': 0.25, 'pids': 64},
}
FIXTURE_EMAIL = 'phase5-firefly@example.invalid'
FIXTURE_DESCRIPTION = 'HomeLab Firefly III Phase 5 recovery marker v1'
FIXTURE_AMOUNT = '42.15'
FIXTURE_CURRENCY = 'USD'
FIXTURE_SOURCE = 'Phase 5 Synthetic Asset'
FIXTURE_DESTINATION = 'Phase 5 Synthetic Expense'
FIXTURE_CATEGORY = 'Phase 5 Recovery'
FIXTURE_TAG = 'phase5-recovery'
FIXTURE_ATTACHMENT = 'phase5-firefly-receipt.txt'
FIXTURE_ATTACHMENT_BODY = b'HomeLab Firefly III Phase 5 attachment marker v1\n'


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
                    'method': 'mariadb-filesystem-restore'}
    plan = {
        'kind': 'homelab-firefly-plan', 'contract': 'firefly-isolated-recovery-v1',
        'platform': host_platform(), 'root': str(root), 'port': port, 'runtime': runtime,
        'images': images(), 'recovery': recovery, 'limits': LIMITS,
        'access': 'loopback', 'networks': ['frontend', 'internal-backend'],
        'docker_socket': False, 'mail': 'log-only', 'public_registration': False,
        'external_integrations': 'disabled', 'background_jobs': 'single-cron-owner',
        'recovery_method': 'mariadb-filesystem-restore',
        'authoritative_material': ['mariadb-logical-dump', *APP_AREAS, 'application-secrets'],
        'derived_material': ['application-image', 'runtime-cache', 'oauth-test-token'],
    }
    plan['plan_id'] = digest(plan)
    return plan


def validate_plan(plan):
    keys(plan, {'kind', 'contract', 'platform', 'root', 'port', 'runtime', 'images',
                'recovery', 'limits', 'access', 'networks', 'docker_socket', 'mail',
                'public_registration', 'external_integrations', 'background_jobs',
                'recovery_method', 'authoritative_material', 'derived_material',
                'plan_id'}, 'Firefly plan')
    backup = plan['recovery']['path'] if plan['recovery'] is not None else None
    need(canonical(plan) == canonical(make_plan(plan['root'], plan['port'], plan['runtime'], backup)),
         'Plan/image/recovery drift; review a new plan')
    return plan


def project(plan):
    return 'hl-firefly-' + plan['plan_id'][:16]


def tags(plan, owner):
    return {'org.homelab.owner': owner, 'org.homelab.plan': plan['plan_id'],
            'org.homelab.module': 'firefly-iii'}


def new_credentials():
    return {
        'app_key': 'base64:' + base64.b64encode(secrets.token_bytes(32)).decode('ascii'),
        'database_password': secrets.token_hex(32),
        'cron_token': secrets.token_hex(16),
    }


def validate_credentials(value):
    keys(value, {'app_key', 'database_password', 'cron_token'}, 'Firefly credentials')
    try:
        decoded = base64.b64decode(value['app_key'].removeprefix('base64:'), validate=True)
    except (ValueError, TypeError) as error:
        raise ConfigError('Invalid private credential material') from error
    need(value['app_key'].startswith('base64:') and len(decoded) == 32,
         'Invalid private credential material')
    need(isinstance(value['database_password'], str)
         and re.fullmatch(r'[0-9a-f]{64}', value['database_password']),
         'Invalid private credential material')
    need(isinstance(value['cron_token'], str)
         and re.fullmatch(r'[0-9a-f]{32}', value['cron_token']),
         'Invalid private credential material')
    need(all('\n' not in item and '\r' not in item for item in value.values()),
         'Invalid private credential material')
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
    return {name: root / (name + '.txt')
            for name in ('app_key', 'database_password', 'cron_token')}


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
    database = {
        **common, 'image': plan['images']['database'],
        'command': ['--innodb-buffer-pool-size=256M', '--skip-name-resolve'],
        'environment': {'MYSQL_RANDOM_ROOT_PASSWORD': 'yes', 'MYSQL_DATABASE': 'firefly',
                        'MYSQL_USER': 'firefly',
                        'MYSQL_PASSWORD_FILE': '/run/secrets/database_password'},
        'secrets': ['database_password'],
        'volumes': [{'type': 'volume', 'source': 'database-data',
                     'target': '/var/lib/mysql'}],
        'networks': ['backend'],
        'healthcheck': {'test': ['CMD', 'healthcheck.sh', '--connect', '--innodb_initialized'],
                        'interval': '10s', 'timeout': '5s', 'retries': 18,
                        'start_period': '30s'},
        'stop_grace_period': '60s', 'mem_limit': '512m', 'mem_reservation': '96m',
        'memswap_limit': '768m', 'cpus': 1.0, 'pids_limit': 192,
    }
    app_environment = {
        'APP_ENV': 'production', 'APP_DEBUG': 'false',
        'APP_URL': 'http://127.0.0.1:' + str(plan['port']),
        'SITE_OWNER': FIXTURE_EMAIL, 'TZ': 'UTC', 'DEFAULT_LANGUAGE': 'en_US',
        'DB_CONNECTION': 'mysql', 'DB_HOST': 'database', 'DB_PORT': '3306',
        'DB_DATABASE': 'firefly', 'DB_USERNAME': 'firefly',
        'MAIL_MAILER': 'log', 'SEND_ERROR_MESSAGE': 'false',
        'AUTHENTICATION_GUARD': 'web', 'COOKIE_SECURE': 'false',
        'COOKIE_SAMESITE': 'strict', 'DISABLE_FRAME_HEADER': 'false',
        'DISABLE_CSP_HEADER': 'false', 'CHECK_FOR_UPDATES': 'false',
        'ENABLE_EXCHANGE_RATES': 'false', 'LOG_CHANNEL': 'stderr',
        'AUDIT_LOG_CHANNEL': 'stderr', 'HEALTHCHECK_PATH': '/health',
    }
    app = {
        **common, 'image': plan['images']['app'],
        'entrypoint': ['/bin/sh', '-ec',
                       ('export APP_KEY="$$(cat /run/secrets/app_key)"; '
                        'export DB_PASSWORD="$$(cat /run/secrets/database_password)"; '
                        'export STATIC_CRON_TOKEN="$$(cat /run/secrets/cron_token)"; '
                        'exec docker-php-serversideup-entrypoint /init')],
        'environment': app_environment,
        'depends_on': {'database': {'condition': 'service_healthy'}},
        'ports': [{'target': 8080, 'published': str(plan['port']),
                   'host_ip': '127.0.0.1', 'protocol': 'tcp'}],
        'secrets': ['app_key', 'database_password', 'cron_token'],
        'volumes': [{'type': 'volume', 'source': name, 'target': target}
                    for name, target in APP_AREAS.items()],
        'networks': ['frontend', 'backend'],
        'healthcheck': {'test': ['CMD-SHELL',
                                 'curl -fsS --max-time 10 http://127.0.0.1:8080/health >/dev/null'],
                        'interval': '10s', 'timeout': '10s', 'retries': 36,
                        'start_period': '90s'},
        'stop_grace_period': '60s', 'mem_limit': '1024m',
        'mem_reservation': '192m', 'memswap_limit': '1536m',
        'cpus': 2.0, 'pids_limit': 512,
    }
    cron = {
        **common, 'image': plan['images']['cron'],
        'command': ['/bin/sh', '-ec',
                    ('token="$$(cat /run/secrets/cron_token)"; '
                     'echo "0 3 * * * wget -qO- http://app:8080/api/v1/cron/$$token; echo" '
                     '| crontab -; unset token; exec crond -f -L /dev/stdout')],
        'depends_on': {'app': {'condition': 'service_healthy'}},
        'secrets': ['cron_token'], 'networks': ['backend'], 'read_only': True,
        'tmpfs': ['/tmp', '/var/spool/cron/crontabs:mode=0700'],
        'healthcheck': {'test': ['CMD-SHELL', 'pidof crond >/dev/null || exit 1'],
                        'interval': '30s', 'timeout': '5s', 'retries': 6,
                        'start_period': '10s'},
        'mem_limit': '64m', 'mem_reservation': '8m', 'memswap_limit': '96m',
        'cpus': 0.25, 'pids_limit': 64,
    }
    return {
        'services': {'database': database, 'app': app, 'cron': cron},
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
    return plan['images'][role]


def inventory(plan, owner):
    context = plan['runtime']['context']
    found = {'containers': {}, 'networks': [], 'volumes': []}
    ids = docker(['ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project(plan)],
                 context=context).split()
    need(len(ids) <= len(SERVICES), 'Unexpected Firefly project containers')
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
        expected_ports = ({'8080/tcp': [{'HostIp': '127.0.0.1',
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
             'Unexpected Firefly project resources')
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
    keys(state, {'kind', 'owner', 'plan_id', 'status', 'recovery'}, 'Firefly state')
    need(state['kind'] == 'firefly-owned-v1' and state['plan_id'] == plan['plan_id'],
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
    state = {'kind': 'firefly-owned-v1', 'owner': owner, 'plan_id': plan['plan_id'],
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
                 'Firefly service exited before becoming ready')
        time.sleep(2)
    raise ConfigError('Firefly services did not become ready before the bounded deadline')


def _php_payload(plan, *, create_user):
    flag = 'true' if create_user else 'false'
    script = (
        'require "vendor/autoload.php"; '
        '$app=require "bootstrap/app.php"; '
        '$kernel=$app->make(Illuminate\\Contracts\\Console\\Kernel::class); '
        '$kernel->bootstrap(); '
        '$repo=app(FireflyIII\\Repositories\\User\\UserRepositoryInterface::class); '
        '$count=(int)$repo->count(); '
        f'$create={flag}; '
        'if($create && $count!==0){throw new RuntimeException("fixture-not-empty");} '
        'if($create){$user=$repo->store(["blocked"=>false,"blocked_code"=>null,'
        f'"email"=>"{FIXTURE_EMAIL}","role"=>"owner"]); '
        '$user->password=Illuminate\\Support\\Facades\\Hash::make(bin2hex(random_bytes(24))); '
        '$user->save(); $user->setRememberToken(bin2hex(random_bytes(30))); '
        '$owner=new FireflyIII\\Notifications\\Notifiables\\OwnerNotifiable(); '
        'event(new FireflyIII\\Events\\Security\\System\\NewUserRegistered($owner,$user));} '
        '$users=$repo->all(); if($users->count()!==1){throw new RuntimeException("fixture-user-count");} '
        '$user=$users->first(); '
        '$clients=app(Laravel\\Passport\\ClientRepository::class); '
        'try{$clients->personalAccessClient("users");}'
        'catch(Throwable $e){$clients->createPersonalAccessGrantClient('
        '"HomeLab Phase 5 synthetic client",null);} '
        '$result=$user->createToken("HomeLab Phase 5 synthetic token"); '
        '$pref=FireflyIII\\Support\\Facades\\Preferences::getForUser($user,"access_token"); '
        'if(null===$pref){$pref=FireflyIII\\Support\\Facades\\Preferences::setForUser('
        '$user,"access_token",$user->generateAccessToken());} '
        '$payload=["token"=>$result->accessToken,"cli_token"=>$pref->data,'
        '"user_id"=>(int)$user->id,'
        '"email"=>$user->email,"created"=>$create]; '
        'echo base64_encode(json_encode($payload,JSON_UNESCAPED_SLASHES));')
    encoded = docker(compose_args(plan) + ['exec', '-T', 'app', 'php', '-r', script],
                     context=plan['runtime']['context'], timeout=180)
    try:
        value = json.loads(base64.b64decode(encoded, validate=True).decode('utf-8'))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigError('Could not create bounded Firefly API authentication') from error
    keys(value, {'token', 'cli_token', 'user_id', 'email', 'created'},
         'Firefly API authentication')
    need(isinstance(value['token'], str) and len(value['token']) >= 64
         and isinstance(value['cli_token'], str)
         and re.fullmatch(r'[0-9a-f]{32}', value['cli_token'])
         and value['user_id'] == 1 and value['email'] == FIXTURE_EMAIL
         and value['created'] is create_user,
         'Unexpected bounded Firefly API authentication')
    return value


def _api_request(plan, token, method, path, *, payload=None, body=None,
                 content_type='application/json', expected=(200, 201, 204)):
    need(path.startswith('/api/v1/') and isinstance(token, str), 'Invalid bounded API request')
    if payload is not None:
        need(body is None, 'Ambiguous bounded API request')
        body = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.api+json'}
    if body is not None:
        headers['Content-Type'] = content_type
    request = urllib.request.Request('http://127.0.0.1:' + str(plan['port']) + path,
                                     data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read()
            need(response.status in expected, 'Unexpected Firefly API response')
            return response.status, data
    except urllib.error.HTTPError as error:
        raise ConfigError('Firefly API request failed with HTTP status '
                          + str(error.code) + ' without exposing credentials') from error
    except (OSError, TimeoutError) as error:
        raise ConfigError('Firefly API request did not complete') from error


def _json_api(plan, token, method, path, *, payload=None, expected=(200, 201)):
    _, body = _api_request(plan, token, method, path, payload=payload, expected=expected)
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigError('Firefly API returned invalid JSON') from error
    need(isinstance(value, dict), 'Firefly API returned an invalid object')
    return value


def _normal_amount(value):
    try:
        return format(Decimal(str(value)).quantize(Decimal('0.01')), 'f')
    except (InvalidOperation, ValueError) as error:
        raise ConfigError('Firefly returned an invalid synthetic amount') from error


def create_fixture(plan, token):
    account = _json_api(plan, token, 'POST', '/api/v1/accounts', payload={
        'name': FIXTURE_SOURCE, 'type': 'asset', 'currency_code': FIXTURE_CURRENCY,
        'account_role': 'defaultAsset', 'active': True, 'include_net_worth': True,
        'notes': 'Synthetic recovery validation only',
    })
    try:
        source_id = int(account['data']['id'])
    except (KeyError, TypeError, ValueError) as error:
        raise ConfigError('Firefly account fixture response is incomplete') from error
    transaction = {
        'error_if_duplicate_hash': True, 'apply_rules': False, 'fire_webhooks': False,
        'transactions': [{
            'type': 'withdrawal', 'date': '2026-01-15T12:00:00+00:00',
            'amount': FIXTURE_AMOUNT, 'description': FIXTURE_DESCRIPTION,
            'currency_code': FIXTURE_CURRENCY, 'source_id': source_id,
            'destination_name': FIXTURE_DESTINATION, 'category_name': FIXTURE_CATEGORY,
            'tags': [FIXTURE_TAG], 'notes': 'Synthetic recovery validation only',
            'internal_reference': 'homelab-phase5-firefly-v1',
        }],
    }
    stored = _json_api(plan, token, 'POST', '/api/v1/transactions', payload=transaction)
    try:
        journal_id = int(stored['data']['attributes']['transactions'][0]['transaction_journal_id'])
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ConfigError('Firefly transaction fixture response is incomplete') from error
    attachment = _json_api(plan, token, 'POST', '/api/v1/attachments', payload={
        'filename': FIXTURE_ATTACHMENT, 'title': 'Phase 5 synthetic receipt',
        'notes': 'Synthetic recovery validation only',
        'attachable_type': 'TransactionJournal', 'attachable_id': journal_id,
    })
    try:
        attachment_id = int(attachment['data']['id'])
    except (KeyError, TypeError, ValueError) as error:
        raise ConfigError('Firefly attachment fixture response is incomplete') from error
    _api_request(plan, token, 'POST', f'/api/v1/attachments/{attachment_id}/upload',
                 body=FIXTURE_ATTACHMENT_BODY, content_type='application/octet-stream',
                 expected=(200, 204))
    return attachment_id


def fixture_inventory(plan, token):
    transactions = _json_api(plan, token, 'GET', '/api/v1/transactions?limit=100')
    matches = []
    for group in transactions.get('data', []):
        attributes = group.get('attributes', {})
        for row in attributes.get('transactions', []):
            if row.get('description') == FIXTURE_DESCRIPTION:
                matches.append((group, row))
    need(len(matches) == 1, 'Expected exactly one synthetic Firefly transaction')
    group, row = matches[0]
    journal_id = int(row['transaction_journal_id'])
    attachments = _json_api(plan, token, 'GET', '/api/v1/attachments?limit=100')
    attachment_matches = []
    for item in attachments.get('data', []):
        attributes = item.get('attributes', {})
        if (attributes.get('filename') == FIXTURE_ATTACHMENT
                and attributes.get('attachable_type') == 'TransactionJournal'
                and int(attributes.get('attachable_id', 0)) == journal_id):
            attachment_matches.append(item)
    need(len(attachment_matches) == 1, 'Expected exactly one synthetic Firefly attachment')
    attachment_id = int(attachment_matches[0]['id'])
    _, content = _api_request(plan, token, 'GET',
                              f'/api/v1/attachments/{attachment_id}/download')
    need(content == FIXTURE_ATTACHMENT_BODY, 'Firefly attachment bytes differ from fixture')
    tags_value = row.get('tags') or []
    need(isinstance(tags_value, list), 'Firefly transaction tags are invalid')
    evidence = {
        'kind': 'firefly-synthetic-finance-fixture-v1',
        'transaction_groups': 1,
        'description': row.get('description'),
        'amount': _normal_amount(row.get('amount')),
        'currency_code': row.get('currency_code'),
        'source_name': row.get('source_name'),
        'destination_name': row.get('destination_name'),
        'category_name': row.get('category_name'),
        'tags': sorted(tags_value),
        'group_id': int(group['id']),
        'journal_id': journal_id,
        'attachment': {'filename': FIXTURE_ATTACHMENT,
                       'bytes': len(FIXTURE_ATTACHMENT_BODY),
                       'sha256': hashlib.sha256(FIXTURE_ATTACHMENT_BODY).hexdigest()},
    }
    need(evidence['amount'] == FIXTURE_AMOUNT
         and evidence['currency_code'] == FIXTURE_CURRENCY
         and evidence['source_name'] == FIXTURE_SOURCE
         and evidence['destination_name'] == FIXTURE_DESTINATION
         and evidence['category_name'] == FIXTURE_CATEGORY
         and evidence['tags'] == [FIXTURE_TAG],
         'Firefly synthetic transaction semantics differ')
    return evidence


def _run_export(plan, cli_token):
    need(isinstance(cli_token, str) and re.fullmatch(r'[0-9a-f]{32}', cli_token),
         'Invalid bounded Firefly CLI authentication')
    command = ('token="$(cat)"; '
               'mkdir -p /var/www/html/storage/export/phase5 && '
               'php artisan firefly-iii:export-data --user=1 '
               '--token="$token" '
               '--start=2026-01-01 --end=2026-12-31 '
               '--export_directory=/var/www/html/storage/export/phase5/ '
               '--export-transactions --export-accounts --force >/dev/null; unset token')
    docker(compose_args(plan) + ['exec', '-T', '--user', 'www-data', 'app',
                                 'sh', '-ec', command],
           context=plan['runtime']['context'], input_text=cli_token, timeout=300)
    output = docker(compose_args(plan) + ['exec', '-T', 'app', 'sh', '-ec',
                                          'find /var/www/html/storage/export/phase5 -type f | wc -l'],
                    context=plan['runtime']['context'])
    need(output.isdigit() and int(output) >= 2, 'Firefly synthetic export is incomplete')
    return int(output)


def _run_cron_once(plan):
    command = ('token="$(cat /run/secrets/cron_token)"; '
               'wget -qO- "http://app:8080/api/v1/cron/$token"; unset token')
    output = docker(compose_args(plan) + ['run', '--rm', '--no-deps',
                                          '--entrypoint', 'sh', 'cron', '-ec', command],
                    context=plan['runtime']['context'], timeout=300)
    need(bool(output), 'Firefly cron endpoint returned no evidence')
    try:
        value = json.loads(output)
    except json.JSONDecodeError as error:
        raise ConfigError('Firefly cron endpoint returned invalid evidence') from error
    need(isinstance(value, dict) or isinstance(value, list),
         'Firefly cron endpoint returned invalid evidence')


def backup_summary(manifest):
    return {
        'transaction_groups': manifest['fixture']['transaction_groups'],
        'attachment_bytes': manifest['fixture']['attachment']['bytes'],
        'attachment_sha256': manifest['fixture']['attachment']['sha256'],
        'upload_files': len(manifest['trees']['upload']),
        'export_files': len(manifest['trees']['export']),
        'recovery_status': manifest['recovery_status'],
    }


def _restore_database(plan, backup, database_id):
    context = plan['runtime']['context']
    target = '/tmp/firefly-restore-' + uuid.uuid4().hex + '.sql'
    docker(['cp', str(backup / 'firefly-mariadb.sql'), database_id + ':' + target],
           context=context, timeout=180)
    command = ('MYSQL_PWD="$(cat /run/secrets/database_password)"; export MYSQL_PWD; '
               'mariadb --user=firefly --database=firefly < "$1"; '
               'unset MYSQL_PWD')
    try:
        docker(['exec', database_id, 'sh', '-ec', command, 'restore', target],
               context=context, timeout=600)
        check = ('MYSQL_PWD="$(cat /run/secrets/database_password)"; export MYSQL_PWD; '
                 'mariadb-check --user=firefly --check-upgrade firefly >/dev/null; '
                 'unset MYSQL_PWD')
        docker(['exec', database_id, 'sh', '-ec', check], context=context, timeout=300)
    finally:
        docker(['exec', database_id, 'rm', '-f', target], context=context)


def _restore_filesystems(plan, backup, app_id):
    context = plan['runtime']['context']
    for name, target in APP_AREAS.items():
        docker(['cp', str(backup / 'filesystem' / name) + os.sep + '.',
                app_id + ':' + target], context=context, timeout=600)
    docker(compose_args(plan) + ['run', '--rm', '--no-deps', '--user', '0',
                                 '--cap-add', 'CHOWN', '--entrypoint', 'sh',
                                 'app', '-ec',
                                 ('chown -R www-data:www-data '
                                  '/var/www/html/storage/upload /var/www/html/storage/export')],
           context=context, timeout=300)


def operate(plan, action, confirmation=None):
    validate_plan(plan)
    need(action in ('up', 'status', 'stop', 'remove'), 'Unsupported Firefly action')
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
                 'Incomplete Firefly creation; retain state for review')
            need(not any(row['State'].get('Paused') for row in containers.values()),
                 'Paused state requires manual review')
            if plan['recovery'] and state['status'] == 'prepared':
                need(not any(row['State']['Running'] for row in containers.values()),
                     'Recovery must target never-started application containers')
                state['status'] = 'restoring'
                atomic_json(root / 'state.json', state, replace=True)
                docker(compose_args(plan) + ['start', 'database'], context=context)
                wait_health(plan, ('database',))
                backup_root = Path(plan['recovery']['path'])
                _restore_database(plan, backup_root, containers['database']['Id'])
                _restore_filesystems(plan, backup_root, containers['app']['Id'])
                state['status'] = 'prepared'
                atomic_json(root / 'state.json', state, replace=True)
                docker(compose_args(plan) + ['start', 'app'], context=context)
                wait_health(plan, ('app',))
                docker(compose_args(plan) + ['start', 'cron'], context=context)
            else:
                docker(compose_args(plan) + ['up', '-d', '--no-build', '--pull', 'never'],
                       context=context, timeout=480)
            wait_health(plan, SERVICES)
            if plan['recovery']:
                auth = _php_payload(plan, create_user=False)
                restored = fixture_inventory(plan, auth['token'])
                source = verify_backup(Path(plan['recovery']['path']))
                need(restored == source['fixture'],
                     'Restored Firefly content differs from backup evidence')
                docker(compose_args(plan) + ['exec', '-T', 'app', 'php', 'artisan',
                                             'firefly-iii:report-integrity'],
                       context=context, timeout=300)
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
        return {'module': 'firefly-iii', 'state': state['status'], 'health': health,
                'url': 'http://127.0.0.1:' + str(plan['port']),
                'data_volumes_retained': len(resources['volumes']),
                'recovery': state['recovery']}


def fixture_evidence(plan):
    """Read the exact synthetic finance fixture from a healthy owned project."""
    validate_plan(plan)
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        need(state['status'] == 'running' and set(resources['containers']) == set(SERVICES)
             and all(row['State']['Running'] for row in resources['containers'].values()),
             'Start the complete owned Firefly project before reading fixture evidence')
        auth = _php_payload(plan, create_user=False)
        return fixture_inventory(plan, auth['token'])


def exercise(plan, confirmation):
    validate_plan(plan)
    need(confirmation == plan['plan_id'], 'Confirm the complete reviewed plan ID')
    need(local_runtime() == plan['runtime'], 'Local Docker context/engine changed')
    root = Path(plan['root'])
    with operation_lock(root / 'operation.lock'):
        state = state_read(plan)
        resources = inventory(plan, state['owner'])
        need(state['status'] == 'running' and set(resources['containers']) == set(SERVICES),
             'Start the complete owned Firefly project before exercise')
        auth = _php_payload(plan, create_user=True)
        create_fixture(plan, auth['token'])
        evidence = fixture_inventory(plan, auth['token'])
        export_files = _run_export(plan, auth['cli_token'])
        docker(compose_args(plan) + ['exec', '-T', 'app', 'php', 'artisan',
                                     'firefly-iii:report-integrity'],
               context=plan['runtime']['context'], timeout=300)
        cron_stopped = False
        try:
            docker(compose_args(plan) + ['stop', '--timeout', '60', 'cron'],
                   context=plan['runtime']['context'], timeout=120)
            cron_stopped = True
            _run_cron_once(plan)
        except ConfigError as error:
            raise ConfigError('Firefly exercise failed during bounded cron execution') from error
        finally:
            if cron_stopped:
                docker(compose_args(plan) + ['start', 'cron'],
                       context=plan['runtime']['context'], timeout=120)
                wait_health(plan, ('cron',))
        return {'operation': 'synthetic-transaction-attachment-export-cron',
                'status': 'passed', **evidence, 'export_files': export_files,
                'integrity_report': True, 'background_job_run': True}


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
        windows_tree_acl(root, create=protect_new)
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
                    'database_bytes', 'trees', 'fixture', 'summary'},
         'Firefly backup manifest')
    need(manifest['kind'] == 'firefly-consistent-backup-v1'
         and manifest['images'] == images()
         and manifest['method'] == 'mariadb-filesystem-restore',
         'Backup image/format mismatch')
    need(manifest['consistency'] == {'cron_quiesced': True,
                                     'application_quiesced': True,
                                     'mariadb_dump_exit_verified': True,
                                     'mariadb_live_check_passed': True,
                                     'filesystem_copy_complete': True}
         and manifest['recovery_status'] == 'pending-independent-restore',
         'Backup consistency/recovery evidence is incomplete')
    credentials = validate_credentials(read_private(root / 'credentials.json'))
    need(digest(credentials) == manifest['credentials_hash'],
         'Backup credential checksum mismatch')
    database = root / 'firefly-mariadb.sql'
    need(file_hash(database) == manifest['database_sha256']
         and database.stat().st_size == manifest['database_bytes']
         and manifest['database_bytes'] > 1024,
         'MariaDB dump checksum or size mismatch')
    need(manifest['configuration_sha256'] == {
        'private': file_hash(root / 'compose.private.json'),
        'sanitized': file_hash(root / 'sanitized-config.json')},
         'Backup configuration checksum mismatch')
    expected = {name: tree_files(root / 'filesystem' / name) for name in APP_AREAS}
    need(expected == manifest['trees']
         and bool(expected['upload']) and bool(expected['export']),
         'Backup content checksum mismatch')
    fixture = manifest['fixture']
    keys(fixture, {'kind', 'transaction_groups', 'description', 'amount', 'currency_code',
                   'source_name', 'destination_name', 'category_name', 'tags', 'group_id',
                   'journal_id', 'attachment'}, 'Firefly semantic fixture')
    keys(fixture['attachment'], {'filename', 'bytes', 'sha256'},
         'Firefly attachment fixture')
    need(fixture['kind'] == 'firefly-synthetic-finance-fixture-v1'
         and fixture['transaction_groups'] == 1
         and fixture['description'] == FIXTURE_DESCRIPTION
         and fixture['amount'] == FIXTURE_AMOUNT
         and fixture['currency_code'] == FIXTURE_CURRENCY
         and fixture['source_name'] == FIXTURE_SOURCE
         and fixture['destination_name'] == FIXTURE_DESTINATION
         and fixture['category_name'] == FIXTURE_CATEGORY
         and fixture['tags'] == [FIXTURE_TAG]
         and type(fixture['group_id']) is int and fixture['group_id'] > 0
         and type(fixture['journal_id']) is int and fixture['journal_id'] > 0
         and fixture['attachment'] == {
             'filename': FIXTURE_ATTACHMENT, 'bytes': len(FIXTURE_ATTACHMENT_BODY),
             'sha256': hashlib.sha256(FIXTURE_ATTACHMENT_BODY).hexdigest()},
         'Backup lacks nonempty synthetic Firefly evidence')
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
             'Start the complete owned Firefly project before backup')
        auth = _php_payload(plan, create_user=False)
        fixture = fixture_inventory(plan, auth['token'])
        context = plan['runtime']['context']
        app = resources['containers']['app']['Id']
        database = resources['containers']['database']['Id']
        cron_stopped = False
        app_stopped = False
        failed_stage = 'quiesce'
        create_private_directory(destination)
        try:
            docker(compose_args(plan) + ['stop', '--timeout', '60', 'cron'],
                   context=context, timeout=120)
            cron_stopped = True
            docker(compose_args(plan) + ['stop', '--timeout', '60', 'app'],
                   context=context, timeout=120)
            app_stopped = True
            failed_stage = 'mariadb-live-check'
            check = ('MYSQL_PWD="$(cat /run/secrets/database_password)"; export MYSQL_PWD; '
                     'mariadb-check --user=firefly --check-upgrade firefly >/dev/null; '
                     'unset MYSQL_PWD')
            docker(['exec', database, 'sh', '-ec', check], context=context, timeout=300)
            dump_target = '/tmp/firefly-' + uuid.uuid4().hex + '.sql'
            failed_stage = 'mariadb-dump'
            dump = ('MYSQL_PWD="$(cat /run/secrets/database_password)"; export MYSQL_PWD; '
                    'mariadb-dump --user=firefly --single-transaction --quick '
                    '--skip-lock-tables --routines --events --triggers --hex-blob '
                    '--add-drop-table --result-file="$1" firefly; unset MYSQL_PWD; '
                    'test -s "$1"; grep -q "Dump completed" "$1"')
            docker(['exec', database, 'sh', '-ec', dump, 'backup', dump_target],
                   context=context, timeout=600)
            failed_stage = 'mariadb-copy'
            docker(['cp', database + ':' + dump_target,
                    str(destination / 'firefly-mariadb.sql')],
                   context=context, timeout=180)
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
            atomic_json(destination / 'sanitized-config.json', {
                'kind': 'firefly-sanitized-configuration-v1',
                'images': plan['images'], 'limits': plan['limits'],
                'access': plan['access'], 'mail': plan['mail'],
                'public_registration': plan['public_registration'],
                'external_integrations': plan['external_integrations'],
                'background_jobs': plan['background_jobs'],
                'recovery_method': plan['recovery_method'],
            })
            tree_files(destination / 'filesystem', protect_new=True)
            failed_stage = 'private-permissions'
            for name in ('credentials.json', 'compose.private.json', 'firefly-mariadb.sql'):
                path = destination / name
                if os.name == 'nt':
                    windows_acl(path, create=True)
                else:
                    path.chmod(0o600)
                verify_private(path)
            trees = {name: tree_files(destination / 'filesystem' / name)
                     for name in APP_AREAS}
            database_path = destination / 'firefly-mariadb.sql'
            manifest = {
                'kind': 'firefly-consistent-backup-v1',
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'images': plan['images'], 'method': 'mariadb-filesystem-restore',
                'authoritative_material': ['mariadb-logical-dump', *APP_AREAS,
                                           'application-secrets'],
                'derived_material': ['application-image', 'runtime-cache',
                                     'oauth-test-token'],
                'consistency': {'cron_quiesced': True, 'application_quiesced': True,
                                'mariadb_dump_exit_verified': True,
                                'mariadb_live_check_passed': True,
                                'filesystem_copy_complete': True},
                'recovery_status': 'pending-independent-restore',
                'credentials_hash': digest(read_private(destination / 'credentials.json')),
                'configuration_sha256': {
                    'private': file_hash(destination / 'compose.private.json'),
                    'sanitized': file_hash(destination / 'sanitized-config.json')},
                'database_sha256': file_hash(database_path),
                'database_bytes': database_path.stat().st_size,
                'trees': trees, 'fixture': fixture, 'summary': None,
            }
            manifest['summary'] = backup_summary(manifest)
            atomic_json(destination / 'manifest.json', manifest)
            failed_stage = 'manifest-verification'
            verify_backup(destination)
        except ConfigError as error:
            raise ConfigError('Firefly backup failed during ' + failed_stage
                              + '; sensitive partial state was retained for review') from error
        finally:
            if app_stopped:
                docker(compose_args(plan) + ['start', 'app'], context=context, timeout=180)
                wait_health(plan, ('app',))
            if cron_stopped:
                docker(compose_args(plan) + ['start', 'cron'], context=context, timeout=120)
                wait_health(plan, ('cron',))
        return {'backup_complete': True, 'application_consistent': True,
                'encrypted': False, 'contains_credentials': True,
                'summary': manifest['summary'], 'recovery_verified': False,
                'note': ('Sensitive local staging backup; restore into a fresh project '
                         'before encrypted off-host retention')}
