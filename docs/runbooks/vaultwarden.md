# vaultwarden

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope. Version `0.6.0-alpha.11` adds a separate [synthetic encrypted off-host recovery candidate](../vaultwarden-vault.md) on top of the [application-aware module](../vaultwarden-module.md); it does not adopt or certify this observed personal deployment.

## Evidence and ownership

- Lifecycle owner: Compose: vaultwarden.
- Observed containers assigned to this module: 1.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `vaultwarden/docker-compose.yml`
- `vaultwarden/vw-data/config.json`
- `vaultwarden/maintenance/Apply-ProductionConfig.ps1`

## Observed configuration

Server 1.37.1; host port 9445; db.sqlite3 exists and no database URL found in inspected config/runtime env.

## Installation and dependencies

The bounded `vaultwarden` CLI can create a new disposable, loopback-only project from a reviewed plan. It is not a production installer and cannot adopt existing state. Use the [module guide](../vaultwarden-module.md) and [platform matrix](../platform-support.md).

## Configuration mapping

- Reusable after review: Rate limits and application security-policy structure, after review.
- Private installation values: All vault content, administrative token, SMTP identity and hostname.
- Manual/platform-specific work: The observed deployment remains a read-only inventory. The synthetic adapter independently validates Vaultwarden's SQLite backup path without querying personal records.

## Storage and secrets

Complete /data bind including SQLite state, attachments, sends, configuration and RSA/key material.

Secret names/purposes only: config.json admin_token and SMTP credentials; vault database/key material is sensitive.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed against the observed deployment for Phase 1, `0.6.0-alpha.10` or `0.6.0-alpha.11`. The synthetic adapter uses a separate root, project identity and loopback port, and requires the complete reviewed plan ID for every mutation.

## Backup and recovery

No dedicated scheduled production Vaultwarden backup was identified. The synthetic module uses Vaultwarden's built-in backup command for a consistent SQLite snapshot, then quiesces the app while copying RSA keys, attachments, sends and optional configuration into one checksummed recovery set. The separate encrypted-vault module accepts only a verified set, reads every Restic data pack and requires fresh-project browser recovery before retention can prune it.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Use only a synthetic vault for decryption/login/attachment/restore checks.

## Limitations and follow-up

Configuration JSON contains secrets and must never be published; file existence alone is not database-integrity evidence. The staging set remains plaintext-sensitive until encrypted. The recovery candidate does not supply durable owner-operated off-host storage, real offline-key custody or production scheduling.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
