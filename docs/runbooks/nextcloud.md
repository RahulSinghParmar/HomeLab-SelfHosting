# nextcloud

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: nextcloud-stack.
- Observed containers assigned to this module: 4.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `nextcloud/docker-compose.yml`
- `nextcloud/Dockerfile`
- `nextcloud/config/config.php`
- `nextcloud/NEXTCLOUD-OPTIMIZATION-REPORT.md`

## Observed configuration

Custom app/cron images; PostgreSQL 15; Redis alpine; app port 8080.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: SMB client build additions, app/cron separation and cache configuration.
- Private installation values: Instance ID, trusted domains, database credentials, SMTP identity and all drive mappings.
- Manual/platform-specific work: Inventory external storage and enabled apps without reading user files; replace broad drive mounts with deliberate selections.

## Storage and secrets

Named HTML volume; config/custom-app binds; separate user-data drive; database bind; external drive mounts.

Secret names/purposes only: POSTGRES_PASSWORD; config.php secret, passwordsalt, database/SMTP credentials and external-storage credentials.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

No dedicated Nextcloud scheduled backup identified in scoped discovery. Full consistent database/data/config recovery must be implemented and rehearsed.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Synthetic upload/download and WebDAV test; verify cron and external-storage mapping without traversing production files.

## Limitations and follow-up

Dockerfile uses floating nextcloud:stable and unpinned OS packages; rebuilding today need not reproduce the running images.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
