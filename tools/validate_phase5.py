"""Validate the bounded personal-data Phase 5 prerelease without Docker."""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RELEASE = '0.7.0-alpha.5'
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
INTEGRATED_CONTRACT = 'phase5-integrated-recovery-v1'
EXPECTED_INTEGRATED_MODULES = (
    {
        'id': 'paperless-ngx', 'command': 'paperless-vault',
        'workflow': 'paperless-disaster-recovery.yml',
        'secret': 'PAPERLESS_DR_TEST_PASSWORD',
        'vault': 'homelab/paperless_vault.py',
        'restic': 'modules/paperless-ngx/restic.json',
        'trial': 'tools/paperless_dr_trial.py',
        'application_validation': 'docs/validation/paperless-ngx.md',
        'off_host_validation': 'docs/validation/paperless-off-host-recovery.md',
    },
    {
        'id': 'affine', 'command': 'affine-vault',
        'workflow': 'affine-disaster-recovery.yml',
        'secret': 'AFFINE_DR_TEST_PASSWORD',
        'vault': 'homelab/affine_vault.py',
        'restic': 'modules/affine/restic.json',
        'trial': 'tools/affine_dr_trial.py',
        'application_validation': 'docs/validation/affine.md',
        'off_host_validation': 'docs/validation/affine-off-host-recovery.md',
    },
    {
        'id': 'nextcloud', 'command': 'nextcloud-vault',
        'workflow': 'nextcloud-disaster-recovery.yml',
        'secret': 'NEXTCLOUD_DR_TEST_PASSWORD',
        'vault': 'homelab/nextcloud_vault.py',
        'restic': 'modules/nextcloud/restic.json',
        'trial': 'tools/nextcloud_dr_trial.py',
        'application_validation': 'docs/validation/nextcloud.md',
        'off_host_validation': 'docs/validation/nextcloud-off-host-recovery.md',
    },
    {
        'id': 'firefly-iii', 'command': 'firefly-vault',
        'workflow': 'firefly-disaster-recovery.yml',
        'secret': 'FIREFLY_DR_TEST_PASSWORD',
        'vault': 'homelab/firefly_vault.py',
        'restic': 'modules/firefly-iii/restic.json',
        'trial': 'tools/firefly_dr_trial.py',
        'application_validation': 'docs/validation/firefly-iii.md',
        'off_host_validation': 'docs/validation/firefly-off-host-recovery.md',
    },
    {
        'id': 'vaultwarden', 'command': 'vaultwarden-vault',
        'workflow': 'vaultwarden-disaster-recovery.yml',
        'secret': 'VAULTWARDEN_DR_TEST_PASSWORD',
        'vault': 'homelab/vaultwarden_vault.py',
        'restic': 'modules/vaultwarden/restic.json',
        'trial': 'tools/vaultwarden_dr_trial.py',
        'application_validation': 'docs/validation/vaultwarden.md',
        'off_host_validation': 'docs/validation/vaultwarden-off-host-recovery.md',
    },
    {
        'id': 'karakeep', 'command': 'karakeep-vault',
        'workflow': 'karakeep-disaster-recovery.yml',
        'secret': 'KARAKEEP_DR_TEST_PASSWORD',
        'vault': 'homelab/karakeep_vault.py',
        'restic': 'modules/karakeep/restic.json',
        'trial': 'tools/karakeep_dr_trial.py',
        'application_validation': 'docs/validation/karakeep.md',
        'off_host_validation': 'docs/validation/karakeep-off-host-recovery.md',
    },
)


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


def validate_reusable_workflow(text: str, module: dict) -> None:
    secret = module['secret']
    prefix = module['workflow'].removesuffix('-disaster-recovery.yml')
    normalized = text.replace('\r\n', '\n')
    require(re.search(r'^  workflow_dispatch:\s*$', normalized, re.MULTILINE)
            and re.search(r'^  workflow_call:\s*$', normalized, re.MULTILINE),
            f'{module["id"]}: recovery workflow must remain manual and reusable')
    secret_declaration = re.compile(
        rf'^  workflow_call:\s+^    secrets:\s+^      {re.escape(secret)}:'
        rf'\s+^        required:\s+true$',
        re.MULTILINE)
    require(secret_declaration.search(text) is not None,
            f'{module["id"]}: reusable workflow secret declaration changed')
    require('permissions:\n  contents: read' in normalized,
            f'{module["id"]}: workflow permissions must remain read-only')
    require('\n  push:' not in text and '\n  pull_request:' not in text,
            f'{module["id"]}: recovery workflow must not run automatically')
    require(text.count('Prepare encrypted off-host artifact') == 1
            and text.count('Recover on independent clean runner') == 1,
            f'{module["id"]}: two-runner recovery boundary changed')
    require(f'test "${{#{secret}}}" -ge 48' in text,
            f'{module["id"]}: minimum recovery-secret check changed')
    require('actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09' in text
            and 'actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1' in text,
            f'{module["id"]}: reviewed source/runtime action revisions changed')
    require('actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9' in text
            and 'actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333' in text,
            f'{module["id"]}: reviewed artifact action revisions changed')
    require(f'name: {prefix}-encrypted-repository-${{{{ github.run_id }}}}' in text
            and f'name: {prefix}-recovery-proof-${{{{ github.run_id }}}}' in text,
            f'{module["id"]}: artifact names must remain run-scoped and isolated')
    require('retention-days: 7' in text and 'retention-days: 30' in text,
            f'{module["id"]}: encrypted/proof artifact retention changed')


def validate_integrated_contract(root: Path = ROOT) -> str:
    manifest = load_json(root / 'modules/phase5/recovery.json')
    require(set(manifest) == {'contract', 'release', 'restic_version',
                              'retention', 'modules'},
            'integrated Phase 5 manifest fields changed')
    require(manifest['contract'] == INTEGRATED_CONTRACT,
            'integrated Phase 5 contract identifier changed')
    require(manifest['release'] == RELEASE,
            'integrated Phase 5 release mismatch')
    require(manifest['restic_version'] == RESTIC_VERSION,
            'integrated Phase 5 Restic version changed')
    require(manifest['retention'] == {'daily': 7, 'weekly': 4, 'monthly': 3},
            'integrated Phase 5 retention policy changed')
    require(manifest['modules'] == list(EXPECTED_INTEGRATED_MODULES),
            'integrated Phase 5 module inventory changed')
    require(len({item['secret'] for item in manifest['modules']}) == 6,
            'each Phase 5 module requires a distinct workflow secret')
    require(len({item['workflow'] for item in manifest['modules']}) == 6,
            'each Phase 5 module requires a distinct reusable workflow')

    reference_restic = None
    reference_shape = None
    for module in manifest['modules']:
        for field in ('vault', 'restic', 'trial', 'application_validation',
                      'off_host_validation'):
            require((root / module[field]).is_file(),
                    f'{module["id"]}: missing integrated evidence {module[field]}')
        restic = load_json(root / module['restic'])
        if reference_restic is None:
            reference_restic = restic
        require(restic == reference_restic,
                f'{module["id"]}: reviewed Restic identity differs across Phase 5')
        tree = ast.parse((root / module['vault']).read_text(encoding='utf-8'))
        shape = (
            tuple(node.name for node in tree.body
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))),
            tuple(node.targets[0].id for node in tree.body
                  if isinstance(node, ast.Assign) and len(node.targets) == 1
                  and isinstance(node.targets[0], ast.Name)),
        )
        if reference_shape is None:
            reference_shape = shape
        require(shape == reference_shape,
                f'{module["id"]}: encrypted-vault API shape differs across Phase 5')
        workflow = (root / '.github/workflows' / module['workflow']).read_text(
            encoding='utf-8')
        validate_reusable_workflow(workflow, module)

    integrated = (root / '.github/workflows/phase5-integrated-recovery.yml').read_text(
        encoding='utf-8')
    normalized = integrated.replace('\r\n', '\n')
    require('workflow_dispatch:' in integrated
            and 'permissions:\n  contents: read' in normalized,
            'integrated recovery review must be manual and read-only')
    require('runs-on:' not in integrated and '\n    steps:' not in integrated,
            'integrated recovery review must only call reviewed workflows')
    for module in manifest['modules']:
        require(f'uses: ./.github/workflows/{module["workflow"]}' in integrated,
                f'{module["id"]}: missing integrated reusable-workflow call')
        mapping = f'{module["secret"]}: ${{{{ secrets.{module["secret"]} }}}}'
        require(mapping in integrated,
                f'{module["id"]}: integrated secret mapping changed')
    require(integrated.count('uses: ./.github/workflows/') == 6,
            'integrated review must call exactly six recovery workflows')
    return ('PASS: Phase 5 integrated contract aligns six reusable encrypted '
            'recovery workflows, distinct secrets, one Restic identity, one '
            'vault API shape and restore-gated 7/4/3 retention')


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
    for relative in ('homelab/vaultwarden.py',
                     'homelab/vaultwarden_vault.py',
                     'modules/vaultwarden/images.json',
                     'modules/vaultwarden/browser.json',
                     'modules/vaultwarden/restic.json',
                     'modules/vaultwarden/browser/Dockerfile',
                     'modules/vaultwarden/browser/package.json',
                     'modules/vaultwarden/browser/package-lock.json',
                     'modules/vaultwarden/browser/validate.mjs',
                     'tests/test_vaultwarden.py',
                     'tests/test_vaultwarden_vault.py',
                     'tools/vaultwarden_dr_trial.py',
                     '.github/workflows/vaultwarden-disaster-recovery.yml',
                     'docs/vaultwarden-module.md',
                     'docs/vaultwarden-vault.md',
                     'docs/validation/vaultwarden.md',
                     'docs/validation/vaultwarden-off-host-recovery.md',
                     'docs/releases/v0.6.0-alpha.10.md',
                     'docs/releases/v0.6.0-alpha.11.md'):
        require((root / relative).is_file(), f'missing Vaultwarden release file {relative}')
    for relative in ('homelab/karakeep.py',
                     'homelab/karakeep_vault.py',
                     'modules/karakeep/images.json',
                     'modules/karakeep/browser.json',
                     'modules/karakeep/restic.json',
                     'modules/karakeep/browser/Dockerfile',
                     'modules/karakeep/browser/validate.mjs',
                     'tests/test_karakeep.py',
                     'tests/test_karakeep_vault.py',
                     'tools/karakeep_dr_trial.py',
                     '.github/workflows/karakeep-disaster-recovery.yml',
                     'docs/karakeep-module.md',
                     'docs/karakeep-vault.md',
                     'docs/validation/karakeep.md',
                     'docs/validation/karakeep-off-host-recovery.md',
                     'docs/releases/v0.6.0-alpha.12.md',
                     'docs/releases/v0.6.0-alpha.13.md'):
        require((root / relative).is_file(), f'missing Karakeep release file {relative}')
    for relative in ('modules/phase5/recovery.json',
                     'modules/phase5/owner-backup-policy.example.json',
                     'modules/phase5/closure.json',
                     'homelab/owner_backup.py',
                     'tests/test_owner_backup.py',
                     'docs/owner-operated-backups.md',
                     'docs/validation/phase5-owner-backup-design.md',
                     'docs/phase5-recovery-kit.md',
                     'docs/validation/phase5-closure.md',
                     'docs/releases/v0.6.0.md',
                     'docs/releases/v0.6.0-rc.2.md',
                     '.github/workflows/phase5-integrated-recovery.yml',
                     'tests/test_phase5_integrated.py',
                     'docs/validation/phase5-integrated.md',
                     'docs/releases/v0.6.0-rc.1.md'):
        require((root / relative).is_file(),
                f'missing integrated Phase 5 release file {relative}')
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
    require("add_parser(\n        'vaultwarden'" in cli,
            'missing Vaultwarden CLI command')
    require("'vaultwarden-vault'" in cli,
            'missing Vaultwarden encrypted-vault CLI command')
    require("add_parser(\n        'karakeep'" in cli,
            'missing Karakeep CLI command')
    require("'karakeep-vault'" in cli,
            'missing Karakeep encrypted-vault CLI command')
    require("add_parser(\n        'owner-backup'" in cli,
            'missing owner backup policy CLI command')
    require("args.command == 'owner-backup'" in cli,
            'missing owner backup policy CLI dispatch')
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
    vaultwarden = load_json(root / 'modules/vaultwarden/images.json')
    require(set(vaultwarden) == {'app'},
            'Vaultwarden image manifest fields changed')
    require(DIGEST.fullmatch(vaultwarden['app']) is not None,
            'Vaultwarden app exact sha256 image digest required')
    vaultwarden_browser = load_json(root / 'modules/vaultwarden/browser.json')
    require(set(vaultwarden_browser) == {'image', 'playwright', 'browser',
                                         'upstream_tag'},
            'Vaultwarden browser manifest fields changed')
    require(DIGEST.fullmatch(vaultwarden_browser['image']) is not None
            and vaultwarden_browser['playwright'] == '1.64.0'
            and vaultwarden_browser['browser'] == 'chromium'
            and vaultwarden_browser['upstream_tag'] == 'v1.64.0-noble',
            'Vaultwarden browser runtime differs from the reviewed pinned release')
    vaultwarden_restic = load_json(root / 'modules/vaultwarden/restic.json')
    require(set(vaultwarden_restic) == {'version', *RESTIC_HASHES},
            'Vaultwarden restic manifest fields changed')
    require(vaultwarden_restic['version'] == RESTIC_VERSION,
            'Vaultwarden restic reviewed version changed')
    for target, expected in RESTIC_HASHES.items():
        item = vaultwarden_restic[target]
        require(set(item) == {'archive_url', 'archive_sha256', 'executable_sha256'},
                f'Vaultwarden restic {target} manifest fields changed')
        require(item['archive_url'] ==
                f'https://github.com/restic/restic/releases/download/v{RESTIC_VERSION}/restic_{RESTIC_VERSION}_{target}.{expected["extension"]}',
                f'Vaultwarden restic {target} archive URL changed')
        require(item['archive_sha256'] == expected['archive']
                and item['executable_sha256'] == expected['executable'],
                f'Vaultwarden restic {target} reviewed checksums changed')
    vaultwarden_code = (root / 'homelab/vaultwarden.py').read_text(encoding='utf-8')
    for contract in ('vaultwarden-isolated-recovery-v1',
                     'sqlite-vacuum-filesystem-restore',
                     'vaultwarden-consistent-backup-v1',
                     'phase5-vaultwarden-attachment.txt',
                     "'/vaultwarden', 'backup'", 'DISABLE_ADMIN_TOKEN',
                     'browser_fingerprint', 'runtime_user', 'windows_acl'):
        require(contract in vaultwarden_code,
                f'Vaultwarden recovery contract missing {contract}')
    vaultwarden_driver = (root / 'modules/vaultwarden/browser/validate.mjs').read_text(
        encoding='utf-8')
    for contract in ('vaultwarden-browser-vault-v1', 'independent_sessions',
                     'attachment_downloaded', 'decrypted_body',
                     'phase5-vaultwarden-attachment.txt'):
        require(contract in vaultwarden_driver,
                f'Vaultwarden browser validation contract missing {contract}')
    vaultwarden_workflow = (
        root / '.github/workflows/vaultwarden-disaster-recovery.yml').read_text(
            encoding='utf-8')
    require('workflow_dispatch:' in vaultwarden_workflow
            and 'VAULTWARDEN_DR_TEST_PASSWORD' in vaultwarden_workflow,
            'Vaultwarden off-host workflow must be manual and use separate secret custody')
    require('Prepare encrypted off-host artifact' in vaultwarden_workflow
            and 'Recover on independent clean runner' in vaultwarden_workflow,
            'Vaultwarden off-host workflow must separate preparation and recovery jobs')
    require('actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9' in vaultwarden_workflow
            and 'actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333' in vaultwarden_workflow,
            'Vaultwarden off-host artifact actions must use immutable reviewed revisions')
    vaultwarden_vault = (root / 'homelab/vaultwarden_vault.py').read_text(
        encoding='utf-8')
    for contract in ('vaultwarden-restic-vault-v1',
                     'vaultwarden-portable-recovery-v1',
                     'vaultwarden-off-host-restore-v1',
                     'CREATE-VAULTWARDEN-RECOVERY-KEY', 'check', '--read-data',
                     'recovery-verified', 'attachment_sha256'):
        require(contract in vaultwarden_vault,
                f'Vaultwarden encrypted recovery contract missing {contract}')
    vaultwarden_trial = (root / 'tools/vaultwarden_dr_trial.py').read_text(
        encoding='utf-8')
    for contract in ('browser_rendered', 'decrypted_note_verified',
                     'attachment_download_verified', 'independent_sessions_verified',
                     'restart_persistence_verified', 'production_data_used'):
        require(contract in vaultwarden_trial,
                f'Vaultwarden clean-runner proof missing {contract}')
    karakeep = load_json(root / 'modules/karakeep/images.json')
    require(set(karakeep) == {'app', 'chrome', 'search'},
            'Karakeep image manifest fields changed')
    for name, image in karakeep.items():
        require(DIGEST.fullmatch(image) is not None,
                f'Karakeep {name} exact sha256 image digest required')
    karakeep_browser = load_json(root / 'modules/karakeep/browser.json')
    require(set(karakeep_browser) == {'image', 'playwright', 'browser', 'upstream_tag'},
            'Karakeep browser manifest fields changed')
    require(DIGEST.fullmatch(karakeep_browser['image']) is not None
            and karakeep_browser['playwright'] == '1.64.0'
            and karakeep_browser['browser'] == 'chromium'
            and karakeep_browser['upstream_tag'] == 'v1.64.0-noble',
            'Karakeep browser runtime differs from the reviewed pinned release')
    karakeep_code = (root / 'homelab/karakeep.py').read_text(encoding='utf-8')
    for contract in ('karakeep-isolated-recovery-v1',
                     'sqlite-quiesced-assets-reindex-restore',
                     'karakeep-consistent-backup-v1',
                     'phase5-karakeep-asset.png', 'application-logical-export',
                     'meilisearch-index', 'search_reindexed', 'runtime_user',
                     'windows_acl'):
        require(contract in karakeep_code,
                f'Karakeep recovery contract missing {contract}')
    karakeep_driver = (root / 'modules/karakeep/browser/validate.mjs').read_text(
        encoding='utf-8')
    for contract in ('karakeep-browser-bookmarks-v1', 'full_text_search',
                     'asset_downloaded', 'search_reindexed',
                     'phase5-karakeep-asset.png', '/api/v1/admin/jobs/trigger/reindex',
                     "baseUrl + '/signin'"):
        require(contract in karakeep_driver,
                f'Karakeep browser validation contract missing {contract}')
    karakeep_restic = load_json(root / 'modules/karakeep/restic.json')
    require(set(karakeep_restic) == {'version', *RESTIC_HASHES},
            'Karakeep restic manifest fields changed')
    require(karakeep_restic['version'] == RESTIC_VERSION,
            'Karakeep restic reviewed version changed')
    for target, expected in RESTIC_HASHES.items():
        item = karakeep_restic[target]
        require(set(item) == {'archive_url', 'archive_sha256', 'executable_sha256'},
                f'Karakeep restic {target} manifest fields changed')
        require(item['archive_url'] ==
                f'https://github.com/restic/restic/releases/download/v{RESTIC_VERSION}/restic_{RESTIC_VERSION}_{target}.{expected["extension"]}',
                f'Karakeep restic {target} archive URL changed')
        require(item['archive_sha256'] == expected['archive']
                and item['executable_sha256'] == expected['executable'],
                f'Karakeep restic {target} reviewed checksums changed')
    karakeep_workflow = (
        root / '.github/workflows/karakeep-disaster-recovery.yml').read_text(
            encoding='utf-8')
    require('workflow_dispatch:' in karakeep_workflow
            and 'KARAKEEP_DR_TEST_PASSWORD' in karakeep_workflow,
            'Karakeep off-host workflow must be manual and use separate secret custody')
    require('Prepare encrypted off-host artifact' in karakeep_workflow
            and 'Recover on independent clean runner' in karakeep_workflow,
            'Karakeep off-host workflow must separate preparation and recovery jobs')
    require('actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9' in karakeep_workflow
            and 'actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333' in karakeep_workflow,
            'Karakeep off-host artifact actions must use immutable reviewed revisions')
    karakeep_vault = (root / 'homelab/karakeep_vault.py').read_text(
        encoding='utf-8')
    for contract in ('karakeep-restic-vault-v1',
                     'karakeep-portable-recovery-v1',
                     'karakeep-off-host-restore-v1',
                     'CREATE-KARAKEEP-RECOVERY-KEY', 'check', '--read-data',
                     'recovery-verified', 'asset_sha256',
                     'application_export_bytes'):
        require(contract in karakeep_vault,
                f'Karakeep encrypted recovery contract missing {contract}')
    karakeep_trial = (root / 'tools/karakeep_dr_trial.py').read_text(
        encoding='utf-8')
    for contract in ('browser_rendered', 'full_text_search_verified',
                     'asset_download_verified', 'search_rebuild_verified',
                     'restart_persistence_verified', 'production_data_used'):
        require(contract in karakeep_trial,
                f'Karakeep clean-runner proof missing {contract}')
    validate_integrated_contract(root)
    owner_policy = load_json(root / 'modules/phase5/owner-backup-policy.example.json')
    from homelab.owner_backup import make_plan
    owner_plan = make_plan(owner_policy)
    require(owner_plan['execution'] == 'disabled-design-only'
            and owner_plan['readiness']['status'] == 'blocked'
            and owner_plan['readiness']['activation_included'] is False,
            'owner backup example must remain a blocked, non-activating design')
    return ('PASS: Phase 5 0.6.0 validates six application-aware encrypted '
            'off-host recovery modules, one integrated reusable-workflow gate and '
            'a disabled owner storage/schedule/key-custody policy; production '
            'adoption remains a separate owner decision')


def main() -> int:
    try:
        print(validate_phase5())
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
