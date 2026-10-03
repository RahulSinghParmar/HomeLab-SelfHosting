# glances

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Windows scheduled task.
- Observed containers assigned to this module: 0.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `glance/glances/Start-Glances.ps1`
- `glance/glances/glances.conf`
- `glance/glances/README.md`

## Observed configuration

Native Python listener confirmed on loopback 61208; task running.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Three-second sampling; public-info hiding; autodiscovery/config execution disabled; process listing disabled in current startup.
- Private installation values: Executable paths and host-specific sensor labels.
- Manual/platform-specific work: Build Linux/macOS startup and sensor adapters; lock actual Python package versions before packaging.

## Storage and secrets

Configuration, Python dependency lock and startup definition; no authoritative user-content database identified.

Secret names/purposes only: No credential values inspected; keep endpoint private and review future authentication requirements.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

Back up configuration and reproducible environment manifest; recreate generated runtime data.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Read live hardware statistics and test restart/startup recovery on the target OS.

## Limitations and follow-up

Host metrics are not equivalent to metrics from a container; existing process-list suppression is intentional, not missing data.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
