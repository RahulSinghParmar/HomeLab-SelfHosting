# paperless-ngx

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: paperless-ngx.
- Observed containers assigned to this module: 3.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `paperless-ngx/compose.yaml`
- `paperless-ngx/maintenance/Backup-Paperless.ps1`
- `paperless-ngx/maintenance/Test-PaperlessRestore.ps1`
- `paperless-ngx/maintenance/Invoke-ScheduledPaperlessBackup.ps1`

## Observed configuration

3.2.1 image pinned by digest; PostgreSQL 18 and Valkey 9; loopback port 8010.

## Installation and dependencies

The separate [Paperless recovery candidate](../paperless-ngx-module.md) creates a fresh digest-pinned project with synthetic content. Its [0.6.0-alpha.2 encrypted vault](../paperless-vault.md) accepts only that verified backup contract. Neither adapter adopts this observed deployment. Follow their private plan, loopback, ownership and confirmation boundaries; never point a synthetic plan at these live directories or volumes.

## Configuration mapping

- Reusable after review: Low-concurrency OCR, polling/stability delay, duplicate protection and explicit proxy configuration.
- Private installation values: Documents, mail credentials, owner origins, accounts and branding.
- Manual/platform-specific work: Select OCR languages and optional parsers; never enable batch OCR or imports during discovery.

## Storage and secrets

Named database/broker volumes; consume, data, media and export bind mounts.

Secret names/purposes only: PAPERLESS_SECRET_KEY, PAPERLESS_DBPASS, POSTGRES_PASSWORD, VALKEY_PASSWORD and credential-bearing broker URL.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

Read-only review on 2026-10-16 found daily, weekly, monthly and manual reports marked passed, but every recorded semantic inventory contained zero documents. The production script also exports and records inventory before stopping the webserver, then dumps/copies afterward, so the artifacts can represent different instants under concurrent writes. Treat those sets as useful backups, not Phase-5-certified representative recovery points.

The isolated candidate corrects that boundary by stopping application processes before exporter, semantic inventory, database dump and file capture, then restores through the documented importer into a new project. Its [validation record](../validation/paperless-ngx.md) uses a nonempty synthetic PDF. It does not modify or replace the production schedule.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

The candidate passes a nonempty synthetic PDF, searchable marker, metadata edit, original-file checksum and independent semantic restore. Production content, encrypted off-host copies and API-token recovery remain unverified.

## Limitations and follow-up

The live production scripts still have the earlier exporter/database timing gap and zero-document restore evidence. Review them separately before migration. The candidate's plaintext staging contains credentials and documents. The new vault proves local restic encryption, full data check, decryption and independent synthetic application restore, but off-host repository media, offline-key recovery, scheduling and production migration remain pending.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
