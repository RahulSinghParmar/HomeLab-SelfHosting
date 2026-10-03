# immich

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: immich.
- Observed containers assigned to this module: 4.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `immich/docker-compose.yml`
- `immich/IMMICH-OPTIMIZATION.md`
- `immich/immich-recover.ps1`
- `immich/jobs-start.ps1`
- `immich/jobs-stop.ps1`

## Observed configuration

Server/ML v3.2.2; PostgreSQL 14 with vector extensions; Valkey 9. Server uncapped; ML 2 CPUs/2 GiB.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Separate ML budget, priority for server, manual heavy-job controls.
- Private installation values: Originals, account/album metadata, drive mappings and credentials.
- Manual/platform-specific work: Verify complete originals path map and extension-compatible image set; GPU remains opt-in.

## Storage and secrets

Separate /data, thumbnails, encoded-video and ML-cache binds; named PostgreSQL volume.

Secret names/purposes only: DB_PASSWORD and owner integration API credentials; preserve account/application state.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

No dedicated scheduled Immich host backup task identified. App-internal backup policy was not queried; database-only copies cannot recover originals.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Restore synthetic originals/albums/metadata and compare hashes; no production thumbnail or ML job is triggered.

## Limitations and follow-up

Additional mounts under /data mean backing up only one host directory can omit thumbnails/encoded files; declare full policy explicitly.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
