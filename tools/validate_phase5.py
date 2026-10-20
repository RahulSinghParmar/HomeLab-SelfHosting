"""Validate the bounded Paperless/AFFiNE Phase 5 prerelease without Docker."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = '0.6.0-alpha.4'
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
    for relative in ('homelab/affine.py', 'modules/affine/images.json',
                     'modules/affine/fixture.mjs', 'tests/test_affine.py',
                     'docs/affine-module.md', 'docs/validation/affine.md',
                     'docs/releases/v0.6.0-alpha.4.md'):
        require((root / relative).is_file(), f'missing AFFiNE release file {relative}')
    require("add_parser('paperless'" in cli, 'missing Paperless CLI command')
    require("'paperless-vault'" in cli, 'missing Paperless encrypted-vault CLI command')
    require("add_parser('affine'" in cli, 'missing AFFiNE CLI command')
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
    fixture = (root / 'modules/affine/fixture.mjs').read_text(encoding='utf-8')
    for contract in ('HOMELAB_FIXTURE_PASSWORD', '/api/setup/create-admin-user',
                     'space:join', 'space:push-doc-update', 'space:load-doc',
                     'HomeLab AFFiNE Phase 5 recovery marker v1'):
        require(contract in fixture, f'AFFiNE fixture contract missing {contract}')
    return ('PASS: Phase 5 0.6.0-alpha.4 validates Paperless off-host recovery and '
            'the digest-pinned AFFiNE sync, backup and independent-restore contract')


def main() -> int:
    try:
        print(validate_phase5())
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
