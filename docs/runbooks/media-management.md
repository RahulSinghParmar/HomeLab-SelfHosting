# media-management

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: arr-stack.
- Observed containers assigned to this module: 8.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `arr-stack/docker-compose.yml`
- `arr-stack/backup-arr.ps1`
- `arr-stack/test-stack.ps1`

## Observed configuration

Eight services use floating latest tags. UI ports 8989, 7878, 8686, 9696, 6767, 5055, 8191, 8095; torrent 6881 TCP/UDP.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Common paths, selective module model and health-check structure.
- Private installation values: Library roots, indexers, credentials, preferences and historical state.
- Manual/platform-specific work: Prove filesystem hardlinks/atomic moves where wanted; initiate no searches/downloads automatically.

## Storage and secrets

Per-app config binds; shared /data for library/download paths; FlareSolverr has anonymous /config volume.

Secret names/purposes only: Per-app API keys and provider/download credentials stored in private application configuration.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

Scheduled ZIP job reports success but only Compress-Archive runs: its freeze-state comment is not implemented; age-based deletion follows without restore verification.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Restore synthetic configuration consistently; verify shared-path semantics without scanning/downloading production media.

## Limitations and follow-up

Live SQLite/config archiving and unverified retention are not a validated recovery plan; anonymous volume ownership needs explicit treatment.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
