"""Application planning and separately gated synthetic-only execution."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, catalogs, load_json, validate_config
from .doctor import diagnose
from .io import write_private
from .planner import create_plan
from .wizard import configure


def display(value: dict, json_output: bool) -> None:
    if json_output:
        print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True))
        return
    if value.get("kind") == "homelab-doctor":
        print("Doctor: " + value["status"] + " - deployment disabled")
        for check in value["checks"]:
            print(f"[{check['status'].upper()}] {check['name']}: {check['detail']}")
        return
    print("Review plan " + value["plan_id"][:16] + " - NO DEPLOYMENT")
    print("Services: " + ", ".join(row["id"] for row in value["services"]))
    print(f"Provisional allowance: {value['resources']['allowance_memory_mib']} MiB / {value['resources']['allowance_cpu_millicores'] / 1000:g} CPUs")
    print("Storage values redacted; configuration and catalog hashes bind this review to its inputs.")
    for port in value["ports"]:
        extent = str(port["first"]) if port["first"] == port["last"] else f"{port['first']}-{port['last']}"
        print(f"Proposed {port['key']}: {port['bind']}:{extent}/{port['protocol']}")
    for issue in value["issues"]:
        print("[BLOCK] " + issue["detail"])
    for warning in value["warnings"]:
        print("[REVIEW] " + warning)
    if "host_report" in value:
        display(value["host_report"], False)
    else:
        print("Host not checked. Use doctor --config or plan --check-host for live read-only checks.")


def main(arguments=None) -> int:
    parser = argparse.ArgumentParser(prog="homelab", description="Plan applications and run separately bounded module adapters.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("catalog", help="List all selectable, not-yet-deployable modules")
    listing.add_argument("--json", action="store_true")
    wizard = sub.add_parser("configure", help="Save settings through wizard or validated file input")
    wizard.add_argument("--output", type=Path, required=True)
    wizard.add_argument("--from", dest="source", type=Path, help="Validate/copy a settings example instead of running the wizard")
    validate = sub.add_parser("validate", help="Validate settings without probing the host")
    validate.add_argument("--config", type=Path, required=True)
    doctor = sub.add_parser("doctor", help="Read-only prerequisite checks, optionally against settings")
    doctor.add_argument("--config", type=Path)
    plan = sub.add_parser("plan", help="Create an offline deterministic review plan")
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--check-host", action="store_true", help="Attach a separate changing, read-only host report")
    for command in (doctor, plan):
        command.add_argument("--json", action="store_true")
        command.add_argument("--output", type=Path, help="Save redacted report outside Git; never overwrite")
    sandbox = sub.add_parser("sandbox", help="Synthetic local files only; no Docker or real applications")
    actions = sandbox.add_subparsers(dest="action", required=True)
    proposal = actions.add_parser("plan", help="Propose dedicated synthetic storage; save private plan")
    for name in ("root", "data-root", "backup-root", "output"):
        proposal.add_argument("--" + name, type=Path, required=True)
    for verb in ("apply", "status", "retire"):
        action = actions.add_parser(verb)
        action.add_argument("--plan", type=Path, required=True)
        if verb != "status":
            action.add_argument("--confirm", required=True, help="Exact full plan ID from the reviewed plan")
    glance = sub.add_parser("glance", help="Experimental isolated Glance deployment; no existing-state adoption")
    glance_actions = glance.add_subparsers(dest="action", required=True)
    glance_plan = glance_actions.add_parser("plan")
    glance_plan.add_argument("--root", type=Path, required=True)
    glance_plan.add_argument("--port", type=int, default=18081)
    glance_plan.add_argument("--output", type=Path, required=True)
    glance_plan.add_argument("--restore-config", type=Path)
    for verb in ("up", "status", "stop", "remove", "export"):
        action = glance_actions.add_parser(verb)
        action.add_argument("--plan", type=Path, required=True)
        if verb in ("up", "stop", "remove"):
            action.add_argument("--confirm", required=True)
        if verb == "export":
            action.add_argument("--output", type=Path, required=True)
    glance_layout = sub.add_parser("glance-layout", help="Render a certified reusable Glance layout; no deployment")
    layout_actions = glance_layout.add_subparsers(dest="action", required=True)
    layout_actions.add_parser("list")
    layout_render = layout_actions.add_parser("render")
    layout_render.add_argument("--profile", default="operations")
    layout_render.add_argument("--output", type=Path, required=True)
    glance_collector = sub.add_parser("glance-collector", help="Validate or sample privacy-filtered Glance host metrics")
    collector_actions = glance_collector.add_subparsers(dest="action", required=True)
    for verb in ("validate", "sample"):
        action = collector_actions.add_parser(verb)
        action.add_argument("--config", type=Path, required=True)
    kuma = sub.add_parser('kuma', help='Experimental isolated Kuma; no adoption of existing monitors')
    kuma_actions = kuma.add_subparsers(dest='action', required=True)
    kuma_plan = kuma_actions.add_parser('plan')
    kuma_plan.add_argument('--root', type=Path, required=True)
    kuma_plan.add_argument('--port', type=int, default=13001)
    kuma_plan.add_argument('--output', type=Path, required=True)
    kuma_plan.add_argument('--restore-backup', type=Path)
    kuma_validate_config = kuma_actions.add_parser('validate-config', help='Validate and redact desired monitor/notification state')
    kuma_validate_config.add_argument('--config', type=Path, required=True)
    for verb in ('apply-config', 'inspect-config', 'test-notifications'):
        action = kuma_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        action.add_argument('--config', type=Path, required=True)
        action.add_argument('--secrets', type=Path)
        if verb != 'inspect-config':
            action.add_argument('--confirm', required=True)
    for verb in ('up', 'status', 'stop', 'remove', 'seed', 'inspect-monitors', 'fixture-down', 'fixture-up', 'backup'):
        action = kuma_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb not in ('status', 'inspect-monitors'):
            action.add_argument('--confirm', required=True)
        if verb == 'backup':
            action.add_argument('--output', type=Path, required=True)
    stirling = sub.add_parser('stirling', help='Experimental isolated Stirling-PDF; no existing-state adoption')
    stirling_actions = stirling.add_subparsers(dest='action', required=True)
    stirling_plan = stirling_actions.add_parser('plan')
    stirling_plan.add_argument('--root', type=Path, required=True)
    stirling_plan.add_argument('--port', type=int, default=19000)
    stirling_plan.add_argument('--output', type=Path, required=True)
    stirling_plan.add_argument('--restore-backup', type=Path)
    for verb in ('up', 'status', 'stop', 'remove', 'exercise', 'backup'):
        action = stirling_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb != 'status':
            action.add_argument('--confirm', required=True)
        if verb == 'backup':
            action.add_argument('--output', type=Path, required=True)
    portainer = sub.add_parser('portainer', help='Experimental Portainer with isolated nested Docker control only')
    portainer_actions = portainer.add_subparsers(dest='action', required=True)
    portainer_plan = portainer_actions.add_parser('plan')
    portainer_plan.add_argument('--root', type=Path, required=True)
    portainer_plan.add_argument('--port', type=int, default=19443)
    portainer_plan.add_argument('--grant-docker-control', required=True,
                                help='Must be exactly isolated-engine-only')
    portainer_plan.add_argument('--output', type=Path, required=True)
    portainer_plan.add_argument('--restore-backup', type=Path)
    for verb in ('up', 'status', 'stop', 'remove', 'exercise', 'backup'):
        action = portainer_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb != 'status':
            action.add_argument('--confirm', required=True)
        if verb == 'backup':
            action.add_argument('--output', type=Path, required=True)
    paperless = sub.add_parser('paperless', help='Experimental isolated Paperless-ngx with application-aware recovery')
    paperless_actions = paperless.add_subparsers(dest='action', required=True)
    paperless_plan = paperless_actions.add_parser('plan')
    paperless_plan.add_argument('--root', type=Path, required=True)
    paperless_plan.add_argument('--port', type=int, default=18010)
    paperless_plan.add_argument('--output', type=Path, required=True)
    paperless_plan.add_argument('--restore-backup', type=Path)
    for verb in ('up', 'status', 'stop', 'remove', 'exercise', 'backup'):
        action = paperless_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb != 'status':
            action.add_argument('--confirm', required=True)
        if verb == 'backup':
            action.add_argument('--output', type=Path, required=True)
    affine = sub.add_parser('affine', help='Experimental isolated AFFiNE with application-aware recovery')
    affine_actions = affine.add_subparsers(dest='action', required=True)
    affine_plan = affine_actions.add_parser('plan')
    affine_plan.add_argument('--root', type=Path, required=True)
    affine_plan.add_argument('--port', type=int, default=18020)
    affine_plan.add_argument('--output', type=Path, required=True)
    affine_plan.add_argument('--restore-backup', type=Path)
    for verb in ('up', 'status', 'stop', 'remove', 'exercise', 'backup'):
        action = affine_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb != 'status':
            action.add_argument('--confirm', required=True)
        if verb == 'backup':
            action.add_argument('--output', type=Path, required=True)
    nextcloud = sub.add_parser(
        'nextcloud', help='Experimental isolated Nextcloud with WebDAV and consistent recovery')
    nextcloud_actions = nextcloud.add_subparsers(dest='action', required=True)
    nextcloud_plan = nextcloud_actions.add_parser('plan')
    nextcloud_plan.add_argument('--root', type=Path, required=True)
    nextcloud_plan.add_argument('--port', type=int, default=18030)
    nextcloud_plan.add_argument('--output', type=Path, required=True)
    nextcloud_plan.add_argument('--restore-backup', type=Path)
    for verb in ('up', 'status', 'stop', 'remove', 'exercise', 'backup'):
        action = nextcloud_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb != 'status':
            action.add_argument('--confirm', required=True)
        if verb == 'backup':
            action.add_argument('--output', type=Path, required=True)
    firefly = sub.add_parser(
        'firefly', help='Experimental isolated Firefly III with finance-aware recovery')
    firefly_actions = firefly.add_subparsers(dest='action', required=True)
    firefly_plan = firefly_actions.add_parser('plan')
    firefly_plan.add_argument('--root', type=Path, required=True)
    firefly_plan.add_argument('--port', type=int, default=18040)
    firefly_plan.add_argument('--output', type=Path, required=True)
    firefly_plan.add_argument('--restore-backup', type=Path)
    for verb in ('up', 'status', 'stop', 'remove', 'exercise', 'backup'):
        action = firefly_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb != 'status':
            action.add_argument('--confirm', required=True)
        if verb == 'backup':
            action.add_argument('--output', type=Path, required=True)
    paperless_vault = sub.add_parser(
        'paperless-vault', help='Encrypted restic repository for verified Paperless recovery sets')
    vault_actions = paperless_vault.add_subparsers(dest='action', required=True)
    vault_keys = vault_actions.add_parser('key-create')
    vault_keys.add_argument('--password-file', type=Path, required=True)
    vault_keys.add_argument('--recovery-key-file', type=Path, required=True)
    vault_keys.add_argument('--confirm', required=True)
    vault_plan = vault_actions.add_parser('plan')
    vault_plan.add_argument('--state-root', type=Path, required=True)
    vault_plan.add_argument('--repository', type=Path, required=True)
    vault_plan.add_argument('--password-file', type=Path, required=True)
    vault_plan.add_argument('--recovery-key-file', type=Path, required=True)
    vault_plan.add_argument('--restic', type=Path, required=True)
    vault_plan.add_argument('--output', type=Path, required=True)
    snapshot_plan = vault_actions.add_parser('snapshot-plan')
    snapshot_plan.add_argument('--plan', type=Path, required=True)
    snapshot_plan.add_argument('--source', type=Path, required=True)
    snapshot_plan.add_argument('--output', type=Path, required=True)
    portable_manifest = vault_actions.add_parser('portable-manifest')
    portable_manifest.add_argument('--plan', type=Path, required=True)
    portable_manifest.add_argument('--snapshot-plan', type=Path, required=True)
    portable_manifest.add_argument('--snapshot-id', required=True)
    portable_manifest.add_argument('--output', type=Path, required=True)
    recovery_plan = vault_actions.add_parser('recovery-plan')
    recovery_plan.add_argument('--repository', type=Path, required=True)
    recovery_plan.add_argument('--recovery-key-file', type=Path, required=True)
    recovery_plan.add_argument('--restic', type=Path, required=True)
    recovery_plan.add_argument('--manifest', type=Path, required=True)
    recovery_plan.add_argument('--output', type=Path, required=True)
    off_host_restore = vault_actions.add_parser('recover-off-host')
    off_host_restore.add_argument('--plan', type=Path, required=True)
    off_host_restore.add_argument('--target', type=Path, required=True)
    off_host_restore.add_argument('--confirm', required=True)
    for verb in ('init', 'status', 'store', 'check', 'restore',
                 'retention-preview', 'retention-apply'):
        action = vault_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb not in ('status', 'retention-preview'):
            action.add_argument('--confirm', required=True)
        if verb in ('store', 'restore'):
            action.add_argument('--snapshot-plan', type=Path, required=True)
        if verb == 'restore':
            action.add_argument('--snapshot-id', required=True)
            action.add_argument('--target', type=Path, required=True)
    affine_vault = sub.add_parser(
        'affine-vault', help='Encrypted restic repository for verified AFFiNE recovery sets')
    affine_vault_actions = affine_vault.add_subparsers(dest='action', required=True)
    affine_vault_keys = affine_vault_actions.add_parser('key-create')
    affine_vault_keys.add_argument('--password-file', type=Path, required=True)
    affine_vault_keys.add_argument('--recovery-key-file', type=Path, required=True)
    affine_vault_keys.add_argument('--confirm', required=True)
    affine_vault_plan = affine_vault_actions.add_parser('plan')
    affine_vault_plan.add_argument('--state-root', type=Path, required=True)
    affine_vault_plan.add_argument('--repository', type=Path, required=True)
    affine_vault_plan.add_argument('--password-file', type=Path, required=True)
    affine_vault_plan.add_argument('--recovery-key-file', type=Path, required=True)
    affine_vault_plan.add_argument('--restic', type=Path, required=True)
    affine_vault_plan.add_argument('--output', type=Path, required=True)
    affine_snapshot_plan = affine_vault_actions.add_parser('snapshot-plan')
    affine_snapshot_plan.add_argument('--plan', type=Path, required=True)
    affine_snapshot_plan.add_argument('--source', type=Path, required=True)
    affine_snapshot_plan.add_argument('--output', type=Path, required=True)
    affine_portable_manifest = affine_vault_actions.add_parser('portable-manifest')
    affine_portable_manifest.add_argument('--plan', type=Path, required=True)
    affine_portable_manifest.add_argument('--snapshot-plan', type=Path, required=True)
    affine_portable_manifest.add_argument('--snapshot-id', required=True)
    affine_portable_manifest.add_argument('--output', type=Path, required=True)
    affine_recovery_plan = affine_vault_actions.add_parser('recovery-plan')
    affine_recovery_plan.add_argument('--repository', type=Path, required=True)
    affine_recovery_plan.add_argument('--recovery-key-file', type=Path, required=True)
    affine_recovery_plan.add_argument('--restic', type=Path, required=True)
    affine_recovery_plan.add_argument('--manifest', type=Path, required=True)
    affine_recovery_plan.add_argument('--output', type=Path, required=True)
    affine_off_host = affine_vault_actions.add_parser('recover-off-host')
    affine_off_host.add_argument('--plan', type=Path, required=True)
    affine_off_host.add_argument('--target', type=Path, required=True)
    affine_off_host.add_argument('--confirm', required=True)
    for verb in ('init', 'status', 'store', 'check', 'restore',
                 'retention-preview', 'retention-apply'):
        action = affine_vault_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb not in ('status', 'retention-preview'):
            action.add_argument('--confirm', required=True)
        if verb in ('store', 'restore'):
            action.add_argument('--snapshot-plan', type=Path, required=True)
        if verb == 'restore':
            action.add_argument('--snapshot-id', required=True)
            action.add_argument('--target', type=Path, required=True)
    nextcloud_vault = sub.add_parser(
        'nextcloud-vault', help='Encrypted restic repository for verified Nextcloud recovery sets')
    nextcloud_vault_actions = nextcloud_vault.add_subparsers(dest='action', required=True)
    nextcloud_vault_keys = nextcloud_vault_actions.add_parser('key-create')
    nextcloud_vault_keys.add_argument('--password-file', type=Path, required=True)
    nextcloud_vault_keys.add_argument('--recovery-key-file', type=Path, required=True)
    nextcloud_vault_keys.add_argument('--confirm', required=True)
    nextcloud_vault_plan = nextcloud_vault_actions.add_parser('plan')
    nextcloud_vault_plan.add_argument('--state-root', type=Path, required=True)
    nextcloud_vault_plan.add_argument('--repository', type=Path, required=True)
    nextcloud_vault_plan.add_argument('--password-file', type=Path, required=True)
    nextcloud_vault_plan.add_argument('--recovery-key-file', type=Path, required=True)
    nextcloud_vault_plan.add_argument('--restic', type=Path, required=True)
    nextcloud_vault_plan.add_argument('--output', type=Path, required=True)
    nextcloud_snapshot_plan = nextcloud_vault_actions.add_parser('snapshot-plan')
    nextcloud_snapshot_plan.add_argument('--plan', type=Path, required=True)
    nextcloud_snapshot_plan.add_argument('--source', type=Path, required=True)
    nextcloud_snapshot_plan.add_argument('--output', type=Path, required=True)
    nextcloud_portable_manifest = nextcloud_vault_actions.add_parser('portable-manifest')
    nextcloud_portable_manifest.add_argument('--plan', type=Path, required=True)
    nextcloud_portable_manifest.add_argument('--snapshot-plan', type=Path, required=True)
    nextcloud_portable_manifest.add_argument('--snapshot-id', required=True)
    nextcloud_portable_manifest.add_argument('--output', type=Path, required=True)
    nextcloud_recovery_plan = nextcloud_vault_actions.add_parser('recovery-plan')
    nextcloud_recovery_plan.add_argument('--repository', type=Path, required=True)
    nextcloud_recovery_plan.add_argument('--recovery-key-file', type=Path, required=True)
    nextcloud_recovery_plan.add_argument('--restic', type=Path, required=True)
    nextcloud_recovery_plan.add_argument('--manifest', type=Path, required=True)
    nextcloud_recovery_plan.add_argument('--output', type=Path, required=True)
    nextcloud_off_host = nextcloud_vault_actions.add_parser('recover-off-host')
    nextcloud_off_host.add_argument('--plan', type=Path, required=True)
    nextcloud_off_host.add_argument('--target', type=Path, required=True)
    nextcloud_off_host.add_argument('--confirm', required=True)
    for verb in ('init', 'status', 'store', 'check', 'restore',
                 'retention-preview', 'retention-apply'):
        action = nextcloud_vault_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb not in ('status', 'retention-preview'):
            action.add_argument('--confirm', required=True)
        if verb in ('store', 'restore'):
            action.add_argument('--snapshot-plan', type=Path, required=True)
        if verb == 'restore':
            action.add_argument('--snapshot-id', required=True)
            action.add_argument('--target', type=Path, required=True)
    firefly_vault = sub.add_parser(
        'firefly-vault', help='Encrypted restic repository for verified Firefly III recovery sets')
    firefly_vault_actions = firefly_vault.add_subparsers(dest='action', required=True)
    firefly_vault_keys = firefly_vault_actions.add_parser('key-create')
    firefly_vault_keys.add_argument('--password-file', type=Path, required=True)
    firefly_vault_keys.add_argument('--recovery-key-file', type=Path, required=True)
    firefly_vault_keys.add_argument('--confirm', required=True)
    firefly_vault_plan = firefly_vault_actions.add_parser('plan')
    firefly_vault_plan.add_argument('--state-root', type=Path, required=True)
    firefly_vault_plan.add_argument('--repository', type=Path, required=True)
    firefly_vault_plan.add_argument('--password-file', type=Path, required=True)
    firefly_vault_plan.add_argument('--recovery-key-file', type=Path, required=True)
    firefly_vault_plan.add_argument('--restic', type=Path, required=True)
    firefly_vault_plan.add_argument('--output', type=Path, required=True)
    firefly_snapshot_plan = firefly_vault_actions.add_parser('snapshot-plan')
    firefly_snapshot_plan.add_argument('--plan', type=Path, required=True)
    firefly_snapshot_plan.add_argument('--source', type=Path, required=True)
    firefly_snapshot_plan.add_argument('--output', type=Path, required=True)
    firefly_portable_manifest = firefly_vault_actions.add_parser('portable-manifest')
    firefly_portable_manifest.add_argument('--plan', type=Path, required=True)
    firefly_portable_manifest.add_argument('--snapshot-plan', type=Path, required=True)
    firefly_portable_manifest.add_argument('--snapshot-id', required=True)
    firefly_portable_manifest.add_argument('--output', type=Path, required=True)
    firefly_recovery_plan = firefly_vault_actions.add_parser('recovery-plan')
    firefly_recovery_plan.add_argument('--repository', type=Path, required=True)
    firefly_recovery_plan.add_argument('--recovery-key-file', type=Path, required=True)
    firefly_recovery_plan.add_argument('--restic', type=Path, required=True)
    firefly_recovery_plan.add_argument('--manifest', type=Path, required=True)
    firefly_recovery_plan.add_argument('--output', type=Path, required=True)
    firefly_off_host = firefly_vault_actions.add_parser('recover-off-host')
    firefly_off_host.add_argument('--plan', type=Path, required=True)
    firefly_off_host.add_argument('--target', type=Path, required=True)
    firefly_off_host.add_argument('--confirm', required=True)
    for verb in ('init', 'status', 'store', 'check', 'restore',
                 'retention-preview', 'retention-apply'):
        action = firefly_vault_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb not in ('status', 'retention-preview'):
            action.add_argument('--confirm', required=True)
        if verb in ('store', 'restore'):
            action.add_argument('--snapshot-plan', type=Path, required=True)
        if verb == 'restore':
            action.add_argument('--snapshot-id', required=True)
            action.add_argument('--target', type=Path, required=True)
    beszel = sub.add_parser('beszel', help='Experimental upstream Beszel hub and restricted agent; no native-host adoption')
    beszel_actions = beszel.add_subparsers(dest='action', required=True)
    beszel_plan = beszel_actions.add_parser('plan')
    beszel_plan.add_argument('--root', type=Path, required=True)
    beszel_plan.add_argument('--port', type=int, default=18090)
    beszel_plan.add_argument('--output', type=Path, required=True)
    beszel_plan.add_argument('--restore-backup', type=Path)
    for verb in ('up', 'status', 'stop', 'remove', 'seed', 'inspect-metrics', 'agent-down', 'agent-up', 'backup'):
        action = beszel_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb not in ('status', 'inspect-metrics'):
            action.add_argument('--confirm', required=True)
        if verb == 'backup':
            action.add_argument('--output', type=Path, required=True)
    windows_agent = sub.add_parser('beszel-windows', help='Windows-only existing Beszel agent upgrade adapter')
    windows_actions = windows_agent.add_subparsers(dest='action', required=True)
    windows_audit = windows_actions.add_parser('audit')
    windows_audit.add_argument('--service', default='BeszelAgent')
    windows_plan = windows_actions.add_parser('plan')
    windows_plan.add_argument('--service', default='BeszelAgent')
    windows_plan.add_argument('--candidate', type=Path, required=True)
    windows_plan.add_argument('--backup-root', type=Path, required=True)
    windows_plan.add_argument('--output', type=Path, required=True)
    for verb in ('status', 'apply', 'rollback'):
        action = windows_actions.add_parser(verb)
        action.add_argument('--plan', type=Path, required=True)
        if verb != 'status':
            action.add_argument('--confirm', required=True)
    args = parser.parse_args(arguments)
    try:
        if args.command == "glance-layout":
            from . import glance_layouts as module
            if args.action == "list":
                result = {"profiles": [module.summary(name) for name in module.profiles()], "deployment_performed": False}
            else:
                result = module.render(args.profile, args.output)
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        if args.command == "glance-collector":
            from . import glance_collectors as module
            config = module.load_and_validate(args.config)
            result = module.public_config(config) if args.action == "validate" else module.collect(config)
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        if args.command == 'beszel-windows':
            from . import beszel_windows as module
            if args.action == 'audit':
                result = module.public_snapshot(module.read_service(args.service))
            elif args.action == 'plan':
                result = module.make_plan(args.candidate, args.backup_root, args.service)
                if args.output.resolve().is_relative_to(Path(result['backup_root'])):
                    raise ConfigError('Plan output must be outside backup storage')
                write_private(args.output, result)
                result = {**result, 'candidate': {'path': '<private-candidate>', **{k: v for k, v in result['candidate'].items() if k != 'path'}},
                          'backup_root': '<private-backup-root>', 'backup_directory': '<private-backup-directory>',
                          'expected_service': module.public_snapshot(result['expected_service'])}
            elif args.action == 'status':
                result = module.status(load_json(args.plan))
            else:
                result = getattr(module, args.action)(load_json(args.plan), args.confirm)
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        if args.command in ('kuma', 'beszel'):
            if args.command == 'kuma':
                from . import kuma as module
                if args.action == 'validate-config':
                    from . import kuma_config
                    result = kuma_config.public_config(kuma_config.load_and_validate(args.config))
                    print(json.dumps(result, sort_keys=True, indent=2))
                    return 0
                if args.action in ('apply-config', 'inspect-config', 'test-notifications'):
                    result = module.configure(load_json(args.plan), args.action, args.config, args.secrets,
                                              getattr(args, 'confirm', None))
                    print(json.dumps(result, sort_keys=True, indent=2))
                    return 0
            else:
                from . import beszel as module
            if args.action == 'plan':
                result = module.make_plan(args.root, args.port, module.local_runtime(), args.restore_backup)
                if args.output.resolve().is_relative_to(Path(result['root'])):
                    raise ConfigError('Plan output must be outside installation storage')
                write_private(args.output, result)
                result = {**result, 'root': '<installation-root>', 'runtime': '<local-engine-reference>',
                          'recovery': '<private-backup-reference>' if result['recovery'] else None}
            elif args.action == 'backup':
                result = module.backup(load_json(args.plan), args.output, args.confirm)
            else:
                result = module.operate(load_json(args.plan), args.action, getattr(args, 'confirm', None))
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        if args.command == 'stirling':
            from . import stirling as module
            if args.action == 'plan':
                result = module.make_plan(args.root, args.port, module.local_runtime(), args.restore_backup)
                if args.output.resolve().is_relative_to(Path(result['root'])):
                    raise ConfigError('Plan output must be outside installation storage')
                write_private(args.output, result)
                result = {**result, 'root': '<installation-root>', 'runtime': '<local-engine-reference>',
                          'recovery': '<private-backup-reference>' if result['recovery'] else None}
            elif args.action == 'backup':
                result = module.backup(load_json(args.plan), args.output, args.confirm)
            elif args.action == 'exercise':
                result = module.exercise(load_json(args.plan), args.confirm)
            else:
                result = module.operate(load_json(args.plan), args.action, getattr(args, 'confirm', None))
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        if args.command == 'portainer':
            from . import portainer as module
            if args.action == 'plan':
                result = module.make_plan(args.root, args.port, module.local_runtime(),
                                          args.grant_docker_control, args.restore_backup)
                if args.output.resolve().is_relative_to(Path(result['root'])):
                    raise ConfigError('Plan output must be outside installation storage')
                write_private(args.output, result)
                result = {**result, 'root': '<installation-root>',
                          'runtime': '<local-engine-reference>',
                          'recovery': '<private-backup-reference>' if result['recovery'] else None}
            elif args.action == 'backup':
                result = module.backup(load_json(args.plan), args.output, args.confirm)
            elif args.action == 'exercise':
                result = module.exercise(load_json(args.plan), args.confirm)
            else:
                result = module.operate(load_json(args.plan), args.action,
                                        getattr(args, 'confirm', None))
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        if args.command == 'paperless':
            from . import paperless as module
            if args.action == 'plan':
                result = module.make_plan(args.root, args.port, module.local_runtime(), args.restore_backup)
                if args.output.resolve().is_relative_to(Path(result['root'])):
                    raise ConfigError('Plan output must be outside installation storage')
                write_private(args.output, result)
                result = {**result, 'root': '<installation-root>',
                          'runtime': '<local-engine-reference>',
                          'recovery': '<private-backup-reference>' if result['recovery'] else None}
            elif args.action == 'backup':
                result = module.backup(load_json(args.plan), args.output, args.confirm)
            elif args.action == 'exercise':
                result = module.exercise(load_json(args.plan), args.confirm)
            else:
                result = module.operate(load_json(args.plan), args.action,
                                        getattr(args, 'confirm', None))
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        if args.command == 'affine':
            from . import affine as module
            if args.action == 'plan':
                result = module.make_plan(args.root, args.port, module.local_runtime(),
                                          args.restore_backup)
                if args.output.resolve().is_relative_to(Path(result['root'])):
                    raise ConfigError('Plan output must be outside installation storage')
                write_private(args.output, result)
                result = {**result, 'root': '<installation-root>',
                          'runtime': '<local-engine-reference>',
                          'recovery': '<private-backup-reference>' if result['recovery'] else None}
            elif args.action == 'backup':
                result = module.backup(load_json(args.plan), args.output, args.confirm)
            elif args.action == 'exercise':
                result = module.exercise(load_json(args.plan), args.confirm)
            else:
                result = module.operate(load_json(args.plan), args.action,
                                        getattr(args, 'confirm', None))
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        if args.command == 'nextcloud':
            from . import nextcloud as module
            if args.action == 'plan':
                result = module.make_plan(args.root, args.port, module.local_runtime(),
                                          args.restore_backup)
                if args.output.resolve().is_relative_to(Path(result['root'])):
                    raise ConfigError('Plan output must be outside installation storage')
                write_private(args.output, result)
                result = {**result, 'root': '<installation-root>',
                          'runtime': '<local-engine-reference>',
                          'recovery': '<private-backup-reference>' if result['recovery'] else None}
            elif args.action == 'backup':
                result = module.backup(load_json(args.plan), args.output, args.confirm)
            elif args.action == 'exercise':
                result = module.exercise(load_json(args.plan), args.confirm)
            else:
                result = module.operate(load_json(args.plan), args.action,
                                        getattr(args, 'confirm', None))
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        if args.command == 'firefly':
            from . import firefly as module
            if args.action == 'plan':
                result = module.make_plan(args.root, args.port, module.local_runtime(),
                                          args.restore_backup)
                if args.output.resolve().is_relative_to(Path(result['root'])):
                    raise ConfigError('Plan output must be outside installation storage')
                write_private(args.output, result)
                result = {**result, 'root': '<installation-root>',
                          'runtime': '<local-engine-reference>',
                          'recovery': '<private-backup-reference>' if result['recovery'] else None}
            elif args.action == 'backup':
                result = module.backup(load_json(args.plan), args.output, args.confirm)
            elif args.action == 'exercise':
                result = module.exercise(load_json(args.plan), args.confirm)
            else:
                result = module.operate(load_json(args.plan), args.action,
                                        getattr(args, 'confirm', None))
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        if args.command in ('paperless-vault', 'affine-vault', 'nextcloud-vault',
                            'firefly-vault'):
            if args.command == 'paperless-vault':
                from . import paperless_vault as module
                backup_label = '<verified-paperless-backup>'
            elif args.command == 'affine-vault':
                from . import affine_vault as module
                backup_label = '<verified-affine-backup>'
            elif args.command == 'nextcloud-vault':
                from . import nextcloud_vault as module
                backup_label = '<verified-nextcloud-backup>'
            else:
                from . import firefly_vault as module
                backup_label = '<verified-firefly-backup>'
            if args.action == 'key-create':
                result = module.create_keys(args.password_file, args.recovery_key_file, args.confirm)
                result = {**result, 'password_file': '<operational-key-file>',
                          'recovery_key_file': '<recovery-key-file>'}
            elif args.action == 'plan':
                result = module.make_plan(args.state_root, args.repository, args.password_file,
                                          args.recovery_key_file, args.restic)
                destination = args.output.resolve()
                private_paths = (Path(result['state_root']), Path(result['repository']),
                                 Path(result['key_custody']['password_file']),
                                 Path(result['key_custody']['recovery_key_file']))
                if any(destination.is_relative_to(path) or path.is_relative_to(destination)
                       for path in private_paths):
                    raise ConfigError('Plan output must not overlap vault storage or key custody')
                write_private(args.output, result)
                result = {**result, 'state_root': '<private-vault-state>',
                          'repository': '<encrypted-repository>',
                          'tool': {**result['tool'], 'path': '<reviewed-restic-binary>'},
                          'key_custody': {**result['key_custody'],
                                          'password_file': '<operational-key-file>',
                                          'recovery_key_file': '<recovery-key-file>'}}
            elif args.action == 'recovery-plan':
                result = module.make_recovery_plan(args.repository, args.recovery_key_file,
                                                   args.restic, load_json(args.manifest))
                write_private(args.output, result)
                result = {**result, 'repository': '<off-host-encrypted-repository>',
                          'recovery_key_file': '<offline-recovery-key-file>',
                          'tool': {**result['tool'], 'path': '<reviewed-restic-binary>'}}
            elif args.action == 'recover-off-host':
                result = module.recover_off_host(load_json(args.plan), args.target, args.confirm)
                result = {**result, 'restore_root': '<private-restored-backup>'}
            else:
                plan = load_json(args.plan)
                if args.action == 'snapshot-plan':
                    result = module.make_snapshot_plan(plan, args.source)
                    write_private(args.output, result)
                    result = {**result, 'source': backup_label}
                elif args.action == 'portable-manifest':
                    result = module.make_recovery_manifest(
                        plan, load_json(args.snapshot_plan), args.snapshot_id)
                    write_private(args.output, result)
                elif args.action == 'init':
                    result = module.initialize(plan, args.confirm)
                elif args.action == 'status':
                    result = module.status(plan)
                elif args.action == 'store':
                    result = module.store(plan, load_json(args.snapshot_plan), args.confirm)
                elif args.action == 'check':
                    result = module.check(plan, args.confirm)
                elif args.action == 'restore':
                    result = module.restore(plan, load_json(args.snapshot_plan), args.snapshot_id,
                                            args.target, args.confirm)
                    result = {**result, 'restore_root': '<private-restored-backup>'}
                else:
                    result = module.retention(plan, apply=args.action == 'retention-apply',
                                              confirmation=getattr(args, 'confirm', None))
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        if args.command == "glance":
            from . import glance as module
            if args.action == "plan":
                if args.restore_config:
                    module.restore_config(args.restore_config)
                result = module.make_plan(args.root, args.port, module.local_runtime())
                if args.output.resolve().is_relative_to(Path(result['root'])):
                    raise ConfigError("Plan output must be outside installation storage")
                write_private(args.output, result)
                result = {**result, 'root': '<installation-root>', 'runtime': '<local-engine-reference>'}
            elif args.action == "export":
                module.export_config(load_json(args.plan), args.output)
                result = {'configuration_exported': True, 'credentials_included': False}
            else:
                result = module.operate(load_json(args.plan), args.action, getattr(args, 'confirm', None))
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        if args.command == "sandbox":
            from . import sandbox as engine
            if args.action == "plan":
                result = engine.make_plan(args.root, args.data_root, args.backup_root)
                # The plan itself must not occupy future runtime storage.
                destination = args.output.resolve()
                need_outside = all(not destination.is_relative_to(Path(value)) for value in result['paths'].values())
                if not need_outside:
                    raise ConfigError("Plan output must be outside all proposed storage roots")
                write_private(args.output, result)
                result = engine.public_plan(result)
            else:
                reviewed = engine.validate_plan(load_json(args.plan))
                result = (engine.status(reviewed) if args.action == "status" else
                          getattr(engine, args.action)(reviewed, args.confirm))
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        modules, planning = catalogs()
        if args.command == "catalog":
            rows = [{"id": key, "name": value["name"], "kind": value["kind"], "status": value["status"]} for key, value in sorted(modules.items())]
            if args.json:
                print(json.dumps(rows, indent=2))
            else:
                for row in rows:
                    print(f"{row['id']:20} {row['kind']:8} not yet deployable")
            return 0
        if args.command == "configure":
            config = validate_config(load_json(args.source), modules, planning) if args.source else configure(modules, planning)
            if config is None:
                print("Cancelled. Nothing saved or deployed.")
                return 0
            write_private(args.output, config)
            print("Private settings saved to the requested file. Review with plan; no deployment occurred.")
            return 0
        config = validate_config(load_json(args.config), modules, planning) if args.config else None
        if args.command == "validate":
            print("Settings schema valid. Host resources and deployment support are not verified.")
            return 0
        result = diagnose(config, modules, planning) if args.command == "doctor" else create_plan(config, modules, planning)
        if args.command == "plan" and args.check_host:
            result["host_report"] = diagnose(config, modules, planning)
        if args.output:
            write_private(args.output, result)
        display(result, args.json)
        blocked = result.get("status") == "blocked" or bool(result.get("issues")) or result.get("host_report", {}).get("status") == "blocked"
        return 2 if blocked else 0
    except ConfigError as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError):
        print("ERROR: Input, host evidence or private state could not be processed safely. Sandbox work may be incomplete; retain files and inspect before retrying.", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("Cancelled. Retain any sandbox files and retry only with the same reviewed plan.", file=sys.stderr)
        return 130
