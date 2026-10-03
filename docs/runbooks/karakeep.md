# karakeep

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: karakeep.
- Observed containers assigned to this module: 3.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `karakeep/docker-compose.yml`
- `karakeep/.env`

## Observed configuration

App and browser use release tags; Meilisearch 1.11.1; port 3030. db.db and queue.db filenames observed in data root.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Independent browser/search services and configurable AI endpoint contract.
- Private installation values: Bookmarks/assets, account identity, provider keys and data-root mapping.
- Manual/platform-specific work: Determine authoritative SQLite/assets versus rebuildable search/queue data before implementing restore.

## Storage and secrets

App /data bind on separate storage drive; search-index bind; browser has no persistent mount.

Secret names/purposes only: NEXTAUTH_SECRET, MEILI_MASTER_KEY, OPENAI_API_KEY and any provider credentials; key presence is not proof a feature is active.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

No dedicated scheduled backup identified. Preserve consistent app database/assets and declared search recovery policy.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Create synthetic bookmark with attachment, restore, then verify browsing and search.

## Limitations and follow-up

Floating release tags and optional external AI integration need explicit opt-in and compatible version locking.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
