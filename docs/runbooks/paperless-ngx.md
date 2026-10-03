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

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

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

Daily/monthly metadata reports passed restore tests. Exporter and content inventory run before webserver stops, then database/files are copied. Weekly has not yet run.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Use nonempty synthetic PDFs and metadata; verify download/search after isolated restore. Existing pass metadata alone does not prove representative content recovery.

## Limitations and follow-up

Exporter and database snapshots can represent different instants under concurrent writes; declare restore paths and consistency boundaries.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
