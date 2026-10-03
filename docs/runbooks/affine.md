# affine

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: affine.
- Observed containers assigned to this module: 4.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `affine/compose.yaml`
- `affine/config/config.json`
- `affine/config/private.key`
- `affine/maintenance/Backup-Affine.ps1`
- `affine/maintenance/Test-AffineRestore.ps1`
- `affine/maintenance/Invoke-ScheduledAffineBackup.ps1`

## Observed configuration

Digest-pinned stable image, PostgreSQL pg16/pgvector and Redis 8; LAN bind port 3010. Migration exited 0.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Dependency readiness, one-shot migration, persistent config/storage and bounded resources.
- Private installation values: Workspace identity, origins, public hostname, signing material and users.
- Manual/platform-specific work: Choose signup/guest/AI/SMTP policy deliberately; confirm settings in config and application state before templating.

## Storage and secrets

Named PostgreSQL and Redis volumes; config and workspace-storage bind mounts.

Secret names/purposes only: DATABASE_URL/POSTGRES_PASSWORD and config/private.key; owner-configured SMTP and integration credentials.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

Daily/monthly metadata reports passed restore tests. Script stops app for dump/file snapshot; table counts are captured before stop. Weekly task has not yet run.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Create nonempty synthetic document, restore database/config/storage, verify document and asset content across two sessions.

## Limitations and follow-up

Preserve private.key securely. Rework stopped/paused-state handling and concurrent-write inventory ordering before adopting backup script.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
