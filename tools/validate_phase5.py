"""Validate the bounded Paperless-ngx Phase 5 prerelease without contacting Docker."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = '0.6.0-alpha.2'
DIGEST = re.compile(r'^[^@\s]+@sha256:[0-9a-f]{64}$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
RESTIC_VERSION = '0.19.1'
RESTIC_ARCHIVE_SHA256 = 'da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d'
RESTIC_EXECUTABLE_SHA256 = 'b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830'


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
                     'docs/releases/v0.6.0-alpha.1.md', 'docs/releases/v0.6.0-alpha.2.md'):
        require((root / relative).is_file(), f'missing Paperless release file {relative}')
    require("add_parser('paperless'" in cli, 'missing Paperless CLI command')
    require("'paperless-vault'" in cli, 'missing Paperless encrypted-vault CLI command')
    manifest = load_json(root / 'modules/paperless-ngx/images.json')
    require(set(manifest) == {'paperless', 'database', 'broker'}, 'Paperless image manifest fields changed')
    for name, image in manifest.items():
        require(isinstance(image, str) and DIGEST.fullmatch(image),
                f'Paperless {name}: exact sha256 image digest required')
    restic = load_json(root / 'modules/paperless-ngx/restic.json')
    require(set(restic) == {'version', 'windows_amd64'}, 'restic manifest fields changed')
    require(restic['version'] == RESTIC_VERSION, 'restic reviewed version changed')
    windows = restic['windows_amd64']
    require(set(windows) == {'archive_url', 'archive_sha256', 'executable_sha256'},
            'restic Windows manifest fields changed')
    require(windows['archive_url'] ==
            f'https://github.com/restic/restic/releases/download/v{RESTIC_VERSION}/restic_{RESTIC_VERSION}_windows_amd64.zip',
            'restic archive must use the reviewed upstream release URL')
    require(SHA256.fullmatch(windows['archive_sha256']) is not None
            and windows['archive_sha256'] == RESTIC_ARCHIVE_SHA256,
            'restic archive checksum changed')
    require(SHA256.fullmatch(windows['executable_sha256']) is not None
            and windows['executable_sha256'] == RESTIC_EXECUTABLE_SHA256,
            'restic executable checksum changed')
    return ('PASS: Phase 5 0.6.0-alpha.2 Paperless encrypted vault contract validates '
            'digest-pinned images, reviewed restic checksums, bounded CLI, documentation '
            'and Windows recovery evidence')


def main() -> int:
    try:
        print(validate_phase5())
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
