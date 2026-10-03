# vaultwarden

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

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

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Rate limits and application security-policy structure, after review.
- Private installation values: All vault content, administrative token, SMTP identity and hostname.
- Manual/platform-specific work: Confirm database backend authoritatively before backup implementation; detected files strongly indicate SQLite but no SQL/content queries were run.

## Storage and secrets

Complete /data bind including SQLite state, attachments, sends, configuration and RSA/key material.

Secret names/purposes only: config.json admin_token and SMTP credentials; vault database/key material is sensitive.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

No dedicated scheduled Vaultwarden backup identified. Use a consistent SQLite backup plus all required file assets and keys.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Use only a synthetic vault for decryption/login/attachment/restore checks.

## Limitations and follow-up

Configuration JSON contains secrets and must never be published; file existence alone is not database-integrity evidence.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
