"""Validate the bounded personal-data Phase 5 prerelease without Docker."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = '0.6.0-alpha.9'
DIGEST = re.compile(r'^[^@\s]+@sha256:[0-9a-f]{64}$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
RESTIC_VERSION = '0.19.1'
RESTIC_HASHES = {
    'windows_amd64': {
        'extension': 'zip',
        'archive': 'da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d',
        'executable': 'b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830',
    },
    'linux_amd64': {
        'extension': 'bz2',
        'archive': 'f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c',
        'executable': '20d4142678d0d95ec11a4759def1b73fd9190abc9ca19e4b62d067c0b387e639',
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f'{path}: duplicate JSON key {key}')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)


def validate_phase5(root: Path = ROOT) -> str:
    package = (root / 'homelab/__init__.py').read_text(encoding='utf-8')
    catalog = load_json(root / 'catalog/services.json')
    cli = (root / 'homelab/cli.py').read_text(encoding='utf-8')
    require(f'__version__ = "{RELEASE}"' in package, 'package release version mismatch')
    require(catalog.get('release') == RELEASE, 'catalog release version mismatch')
    for relative in ('homelab/paperless.py', 'homelab/paperless_vault.py',
                     'tests/test_paperless.py', 'tests/test_paperless_vault.py',
                     'docs/paperless-ngx-module.md', 'docs/validation/paperless-ngx.md',
                     'docs/paperless-vault.md', 'docs/validation/paperless-vault.md',
                     'docs/validation/paperless-off-host-recovery.md',
                     'docs/releases/v0.6.0-alpha.1.md', 'docs/releases/v0.6.0-alpha.2.md',
                     'docs/releases/v0.6.0-alpha.3.md',
                     'tools/paperless_dr_trial.py',
                     '.github/workflows/paperless-disaster-recovery.yml'):
        require((root / relative).is_file(), f'missing Paperless release file {relative}')
    for relative in ('homelab/affine.py', 'homelab/affine_vault.py',
                     'modules/affine/images.json', 'modules/affine/fixture.mjs',
                     'modules/affine/browser.json', 'modules/affine/browser/Dockerfile',
                     'modules/affine/browser/package-lock.json',
                     'modules/affine/browser/validate.mjs', 'modules/affine/restic.json',
                     'tests/test_affine.py', 'tests/test_affine_vault.py',
                     'tools/affine_dr_trial.py', 'tools/affine_local_trial.py',
                     '.github/workflows/affine-disaster-recovery.yml',
                     'docs/affine-module.md', 'docs/affine-vault.md',
                     'docs/validation/affine.md',
                     'docs/validation/affine-off-host-recovery.md',
                     'docs/releases/v0.6.0-alpha.4.md',
                     'docs/releases/v0.6.0-alpha.5.md'):
        require((root / relative).is_file(), f'missing AFFiNE release file {relative}')
    for relative in ('homelab/nextcloud.py', 'homelab/nextcloud_vault.py',
                     'modules/nextcloud/images.json', 'modules/nextcloud/restic.json',
                     'tests/test_nextcloud.py', 'tests/test_nextcloud_vault.py',
                     'tools/nextcloud_local_trial.py', 'tools/nextcloud_dr_trial.py',
                     '.github/workflows/nextcloud-disaster-recovery.yml',
                     'docs/nextcloud-module.md', 'docs/validation/nextcloud.md',
                     'docs/nextcloud-vault.md',
                     'docs/validation/nextcloud-off-host-recovery.md',
                     'docs/releases/v0.6.0-alpha.6.md',
                     'docs/releases/v0.6.0-alpha.7.md'):
        require((root / relative).is_file(), f'missing Nextcloud release file {relative}')
    for relative in ('homelab/firefly.py', 'homelab/firefly_vault.py',
                     'modules/firefly-iii/images.json',
                     'modules/firefly-iii/restic.json',
                     'tests/test_firefly.py', 'tests/test_firefly_vault.py',
                     'tools/firefly_dr_trial.py',
                     '.github/workflows/firefly-disaster-recovery.yml',
                     'docs/firefly-iii-module.md', 'docs/firefly-vault.md',
                     'docs/validation/firefly-iii.md',
                     'docs/validation/firefly-off-host-recovery.md',
                     'docs/releases/v0.6.0-alpha.8.md',
                     'docs/releases/v0.6.0-alpha.9.md'):
        require((root / relative).is_file(), f'missing Firefly release file {relative}')
    require("add_parser('paperless'" in cli, 'missing Paperless CLI command')
    require("'paperless-vault'" in cli, 'missing Paperless encrypted-vault CLI command')
    require("add_parser('affine'" in cli, 'missing AFFiNE CLI command')
    require("'affine-vault'" in cli, 'missing AFFiNE encrypted-vault CLI command')
    require("add_parser(\n        'nextcloud'" in cli, 'missing Nextcloud CLI command')
    require("'nextcloud-vault'" in cli,
            'missing Nextcloud encrypted-vault CLI command')
    require("add_parser(\n        'firefly'" in cli,
            'missing Firefly III CLI command')
    require("'firefly-vault'" in cli,
            'missing Firefly III encrypted-vault CLI command')
    for command in ('portable-manifest', 'recovery-plan', 'recover-off-host'):
        require(f"add_parser('{command}')" in cli,
                f'missing Paperless off-host CLI command {command}')
    manifest = load_json(root / 'modules/paperless-ngx/images.json')
    require(set(manifest) == {'paperless', 'database', 'broker'}, 'Paperless image manifest fields changed')
    for name, image in manifest.items():
        require(isinstance(image, str) and DIGEST.fullmatch(image),
                f'Paperless {name}: exact sha256 image digest required')
    restic = load_json(root / 'modules/paperless-ngx/restic.json')
    require(set(restic) == {'version', *RESTIC_HASHES}, 'restic manifest fields changed')
    require(restic['version'] == RESTIC_VERSION, 'restic reviewed version changed')
    for target, expected in RESTIC_HASHES.items():
        item = restic[target]
        require(set(item) == {'archive_url', 'archive_sha256', 'executable_sha256'},
                f'restic {target} manifest fields changed')
        require(item['archive_url'] ==
                f'https://github.com/restic/restic/releases/download/v{RESTIC_VERSION}/restic_{RESTIC_VERSION}_{target}.{expected["extension"]}',
                f'restic {target} archive must use the reviewed upstream release URL')
        require(SHA256.fullmatch(item['archive_sha256']) is not None
                and item['archive_sha256'] == expected['archive'],
                f'restic {target} archive checksum changed')
        require(SHA256.fullmatch(item['executable_sha256']) is not None
                and item['executable_sha256'] == expected['executable'],
                f'restic {target} executable checksum changed')
    workflow = (root / '.github/workflows/paperless-disaster-recovery.yml').read_text(encoding='utf-8')
    require('workflow_dispatch:' in workflow and 'PAPERLESS_DR_TEST_PASSWORD' in workflow,
            'off-host workflow must be manual and use separate secret custody')
    require('Prepare encrypted off-host artifact' in workflow
            and 'Recover on independent clean runner' in workflow,
            'off-host workflow must separate preparation and recovery jobs')
    require('actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9' in workflow
            and 'actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333' in workflow,
            'off-host artifact actions must be immutable reviewed revisions')
    affine = load_json(root / 'modules/affine/images.json')
    require(set(affine) == {'affine', 'database', 'cache'},
            'AFFiNE image manifest fields changed')
    for name, image in affine.items():
        require(isinstance(image, str) and DIGEST.fullmatch(image),
                f'AFFiNE {name}: exact sha256 image digest required')
    browser = load_json(root / 'modules/affine/browser.json')
    require(set(browser) == {'image', 'playwright', 'browser', 'upstream_tag'},
            'AFFiNE browser manifest fields changed')
    require(DIGEST.fullmatch(browser['image']) is not None
            and browser['playwright'] == '1.64.0'
            and browser['browser'] == 'chromium'
            and browser['upstream_tag'] == 'v1.64.0-noble',
            'AFFiNE browser runtime differs from the reviewed pinned release')
    browser_driver = (root / 'modules/affine/browser/validate.mjs').read_text(encoding='utf-8')
    for contract in ('affine-browser-document-v1', 'independent_sessions',
                     'reload_persistence', 'doc-title .inline-editor',
                     'affine-note affine-paragraph'):
        require(contract in browser_driver,
                f'AFFiNE browser validation contract missing {contract}')
    affine_restic = load_json(root / 'modules/affine/restic.json')
    require(set(affine_restic) == {'version', *RESTIC_HASHES},
            'AFFiNE restic manifest fields changed')
    require(affine_restic['version'] == RESTIC_VERSION,
            'AFFiNE restic reviewed version changed')
    for target, expected in RESTIC_HASHES.items():
        item = affine_restic[target]
        require(set(item) == {'archive_url', 'archive_sha256', 'executable_sha256'},
                f'AFFiNE restic {target} manifest fields changed')
        require(item['archive_url'] ==
                f'https://github.com/restic/restic/releases/download/v{RESTIC_VERSION}/restic_{RESTIC_VERSION}_{target}.{expected["extension"]}',
                f'AFFiNE restic {target} archive URL changed')
        require(item['archive_sha256'] == expected['archive']
                and item['executable_sha256'] == expected['executable'],
                f'AFFiNE restic {target} reviewed checksums changed')
    affine_workflow = (root / '.github/workflows/affine-disaster-recovery.yml').read_text(
        encoding='utf-8')
    require('workflow_dispatch:' in affine_workflow
            and 'AFFINE_DR_TEST_PASSWORD' in affine_workflow,
            'AFFiNE off-host workflow must be manual and use separate secret custody')
    require('Prepare encrypted off-host artifact' in affine_workflow
            and 'Recover on independent clean runner' in affine_workflow,
            'AFFiNE off-host workflow must separate preparation and recovery jobs')
    require('actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9' in affine_workflow
            and 'actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333' in affine_workflow,
            'AFFiNE off-host artifact actions must be immutable reviewed revisions')
    fixture = (root / 'modules/affine/fixture.mjs').read_text(encoding='utf-8')
    for contract in ('HOMELAB_FIXTURE_PASSWORD', '/api/setup/create-admin-user',
                     'space:join', 'space:push-doc-update', 'space:load-doc',
                     'HomeLab AFFiNE Phase 5 recovery marker v1'):
        require(contract in fixture, f'AFFiNE fixture contract missing {contract}')
    nextcloud = load_json(root / 'modules/nextcloud/images.json')
    require(set(nextcloud) == {'app', 'database', 'cache'},
            'Nextcloud image manifest fields changed')
    for name, image in nextcloud.items():
        require(isinstance(image, str) and DIGEST.fullmatch(image),
                f'Nextcloud {name}: exact sha256 image digest required')
    nextcloud_restic = load_json(root / 'modules/nextcloud/restic.json')
    require(set(nextcloud_restic) == {'version', *RESTIC_HASHES},
            'Nextcloud restic manifest fields changed')
    require(nextcloud_restic['version'] == RESTIC_VERSION,
            'Nextcloud restic reviewed version changed')
    for target, expected in RESTIC_HASHES.items():
        item = nextcloud_restic[target]
        require(set(item) == {'archive_url', 'archive_sha256', 'executable_sha256'},
                f'Nextcloud restic {target} manifest fields changed')
        require(item['archive_url'] ==
                f'https://github.com/restic/restic/releases/download/v{RESTIC_VERSION}/restic_{RESTIC_VERSION}_{target}.{expected["extension"]}',
                f'Nextcloud restic {target} archive URL changed')
        require(item['archive_sha256'] == expected['archive']
                and item['executable_sha256'] == expected['executable'],
                f'Nextcloud restic {target} reviewed checksums changed')
    nextcloud_workflow = (root / '.github/workflows/nextcloud-disaster-recovery.yml').read_text(
        encoding='utf-8')
    require('workflow_dispatch:' in nextcloud_workflow
            and 'NEXTCLOUD_DR_TEST_PASSWORD' in nextcloud_workflow,
            'Nextcloud off-host workflow must be manual and use separate secret custody')
    require('Prepare encrypted off-host artifact' in nextcloud_workflow
            and 'Recover on independent clean runner' in nextcloud_workflow,
            'Nextcloud off-host workflow must separate preparation and recovery jobs')
    require('actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9' in nextcloud_workflow
            and 'actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333' in nextcloud_workflow,
            'Nextcloud off-host artifact actions must be immutable reviewed revisions')
    nextcloud_code = (root / 'homelab/nextcloud.py').read_text(encoding='utf-8')
    for contract in ('nextcloud-isolated-recovery-v1', 'postgres-filesystem-restore',
                     'phase5-nextcloud-recovery.txt', 'database-application-role.json',
                     'background:cron', 'NEXTCLOUD_ADMIN_PASSWORD_FILE',
                     'windows_tree_acl'):
        require(contract in nextcloud_code,
                f'Nextcloud recovery contract missing {contract}')
    nextcloud_vault = (root / 'homelab/nextcloud_vault.py').read_text(encoding='utf-8')
    for contract in ('nextcloud-restic-vault-v1', 'nextcloud-portable-recovery-v1',
                     'nextcloud-off-host-restore-v1',
                     'CREATE-NEXTCLOUD-RECOVERY-KEY', 'check', '--read-data',
                     'recovery-verified'):
        require(contract in nextcloud_vault,
                f'Nextcloud encrypted recovery contract missing {contract}')
    firefly = load_json(root / 'modules/firefly-iii/images.json')
    require(set(firefly) == {'app', 'database', 'cron'},
            'Firefly III image manifest fields changed')
    for name, image in firefly.items():
        require(isinstance(image, str) and DIGEST.fullmatch(image),
                f'Firefly III {name}: exact sha256 image digest required')
    firefly_code = (root / 'homelab/firefly.py').read_text(encoding='utf-8')
    for contract in ('firefly-isolated-recovery-v1', 'mariadb-filesystem-restore',
                     'phase5-firefly-receipt.txt', 'application/octet-stream',
                     'mariadb-check --user=firefly --check-upgrade firefly',
                     'grep -q "Dump completed"', "'--cap-add', 'CHOWN'",
                     'windows_tree_acl'):
        require(contract in firefly_code,
                f'Firefly III recovery contract missing {contract}')
    firefly_restic = load_json(root / 'modules/firefly-iii/restic.json')
    require(set(firefly_restic) == {'version', *RESTIC_HASHES},
            'Firefly III restic manifest fields changed')
    require(firefly_restic['version'] == RESTIC_VERSION,
            'Firefly III restic reviewed version changed')
    for target, expected in RESTIC_HASHES.items():
        item = firefly_restic[target]
        require(set(item) == {'archive_url', 'archive_sha256', 'executable_sha256'},
                f'Firefly III restic {target} manifest fields changed')
        require(item['archive_url'] ==
                f'https://github.com/restic/restic/releases/download/v{RESTIC_VERSION}/restic_{RESTIC_VERSION}_{target}.{expected["extension"]}',
                f'Firefly III restic {target} archive URL changed')
        require(item['archive_sha256'] == expected['archive']
                and item['executable_sha256'] == expected['executable'],
                f'Firefly III restic {target} reviewed checksums changed')
    firefly_workflow = (root / '.github/workflows/firefly-disaster-recovery.yml').read_text(
        encoding='utf-8')
    require('workflow_dispatch:' in firefly_workflow
            and 'FIREFLY_DR_TEST_PASSWORD' in firefly_workflow,
            'Firefly III off-host workflow must be manual and use separate secret custody')
    require('Prepare encrypted off-host artifact' in firefly_workflow
            and 'Recover on independent clean runner' in firefly_workflow,
            'Firefly III off-host workflow must separate preparation and recovery jobs')
    require('actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9' in firefly_workflow
            and 'actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333' in firefly_workflow,
            'Firefly III off-host artifact actions must be immutable reviewed revisions')
    firefly_vault = (root / 'homelab/firefly_vault.py').read_text(encoding='utf-8')
    for contract in ('firefly-restic-vault-v1', 'firefly-portable-recovery-v1',
                     'firefly-off-host-restore-v1',
                     'CREATE-FIREFLY-RECOVERY-KEY', 'check', '--read-data',
                     'recovery-verified', 'attachment_sha256'):
        require(contract in firefly_vault,
                f'Firefly III encrypted recovery contract missing {contract}')
    return ('PASS: Phase 5 0.6.0-alpha.9 validates Paperless off-host recovery, '
            'AFFiNE sync and off-host recovery, digest-pinned Nextcloud WebDAV '
            'off-host recovery, and Firefly III encrypted off-host recovery')


def main() -> int:
    try:
        print(validate_phase5())
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
