# uptime-kuma

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: glance.
- Observed containers assigned to this module: 1.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `glance/docker-compose.yml`
- `glance/uptime-kuma/`
- `glance/maintenance/kuma-windows.ps1`
- `glance/maintenance/Set-KumaPublicStatusPage.js`

## Observed configuration

Digest-pinned Kuma; loopback port 3001; currently shares the Glance Compose project.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Idempotent monitor registration and explicit public-status selection.
- Private installation values: Check URLs, push tokens, monitor IDs, notifications and historical statistics.
- Manual/platform-specific work: Recreate host-specific checks and notification integrations; provide portable encrypted token recovery.

## Storage and secrets

Persistent /app/data bind mount; monitoring history, users, notification settings and status-page configuration.

Secret names/purposes only: Push-monitor tokens in a Windows-protected CLIXML file; notification credentials and account state in the application store.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

No dedicated scheduled Kuma backup identified. Preserve the complete application data with a version-compatible consistent backup; do not copy a live SQLite file alone.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Create a synthetic check, observe up/down transitions, restore settings/history and confirm only selected checks appear publicly.

## Limitations and follow-up

Separating from Glance later requires explicit ownership migration; never re-import checks on every run.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
