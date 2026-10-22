# Nextcloud application-aware recovery module

Version `0.6.0-alpha.7` retains the bounded Nextcloud recovery candidate for new synthetic deployments and adds a separately gated encrypted off-host layer. It does not inspect user files, adopt, restart, upgrade or copy the existing personal Nextcloud deployment.

## Release boundary

The module uses exact image digests for Nextcloud 34.0.5 Apache, PostgreSQL 18 and Redis 8.2 Alpine. It creates separate app and cron services, exposes only the app on a loopback port, keeps PostgreSQL and Redis on an internal network, and supplies generated credentials through private files. Docker socket, host devices, public registration, mail, external storage and GPU access are absent.

Resource ceilings are 192 MiB for Redis, 768 MiB for PostgreSQL, 1536 MiB for the app and 512 MiB for cron. They are limits, not idle reservations. In the recovered idle snapshot the app used about 84 MiB, PostgreSQL 29 MiB, Redis 4 MiB and cron under 1 MiB.

## Operator workflow

Use a new root and keep the private plan outside it:

```powershell
python -m homelab nextcloud plan --root C:\Docker\homelab-nextcloud-trial --port 18030 --output C:\Docker\homelab-nextcloud-plan.json
python -m homelab nextcloud up --plan C:\Docker\homelab-nextcloud-plan.json --confirm <plan-id>
python -m homelab nextcloud status --plan C:\Docker\homelab-nextcloud-plan.json
python -m homelab nextcloud exercise --plan C:\Docker\homelab-nextcloud-plan.json --confirm <plan-id>
python -m homelab nextcloud backup --plan C:\Docker\homelab-nextcloud-plan.json --output C:\Docker\homelab-nextcloud-backup --confirm <plan-id>
python -m homelab nextcloud stop --plan C:\Docker\homelab-nextcloud-plan.json --confirm <plan-id>
python -m homelab nextcloud remove --plan C:\Docker\homelab-nextcloud-plan.json --confirm <plan-id>
```

Mutating commands require the complete reviewed plan ID. `remove` retains named volumes and private files; deletion is a separate reviewed cleanup action.

## Content and cron exercise

The exercise uploads a fixed nonempty text file through WebDAV and downloads it again for exact byte and SHA-256 comparison. To avoid racing the always-running cron loop, it briefly stops only the owned cron service, selects cron mode, executes one real `cron.php` cycle as `www-data`, and restores the cron service in a `finally` block.

## Consistent backup

Backup requires a healthy owned project and the exact WebDAV fixture. It stops cron, enables maintenance mode, stops the app, creates and catalog-validates a PostgreSQL custom archive, and captures:

- the Nextcloud application database role and password required by restored `config.php`;
- `config`, `data`, `custom_apps` and `themes`;
- the private Compose definition and generated recovery credentials;
- sanitized configuration, complete tree checksums and semantic fixture evidence.

The app is restarted, maintenance mode is disabled, cron is restored and health is checked in all exit paths. The backup is plaintext-sensitive and must stay outside Git or public synchronization. Use the separately reviewed [Nextcloud encrypted vault](nextcloud-vault.md) before moving a recovery set off-host.

## Independent restore

Create a second plan with a different absent root and port plus `--restore-backup`. Restore accepts only a complete checksum-valid backup into never-started resources. It initializes cache/database, seeds the derived HTML volume from the exact pinned app image, restores the private application role before the PostgreSQL archive, preserves original database object ownership, restores authoritative trees, disables maintenance mode and verifies the exact WebDAV bytes. A subsequent project stop/start repeats the semantic check.

The HTML core and Redis data are derived. They are not authoritative backup inputs and are recreated from reviewed images. The [official Docker image](https://github.com/nextcloud/docker) documents the container layout and file-secret variables; the [Nextcloud backup](https://docs.nextcloud.com/server/stable/admin_manual/maintenance/backup.html) and [restore](https://docs.nextcloud.com/server/stable/admin_manual/maintenance/restore.html) guides define the application data boundary.

## Current no-go items

- adoption, update or migration of the personal deployment;
- external storage, broad drive mappings, SMB client additions or the existing custom image;
- desktop/mobile client, sharing, mail, SSO, encryption-app or public-domain behavior;
- scheduling, durable owner-operated storage or real offline-key custody;
- representative data size, concurrent users, upgrade rehearsal, Linux/macOS or ARM64 runtime certification.

See the [Windows validation record](validation/nextcloud.md), [encrypted clean-runner gate](validation/nextcloud-off-host-recovery.md), [vault operator guide](nextcloud-vault.md) and [observed deployment runbook](runbooks/nextcloud.md).
