# host-metrics

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: glance; native scheduled tasks.
- Observed containers assigned to this module: 2.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `glance/docker-compose.yml`
- `glance/metrics/`
- `glance/maintenance/resource_collector.py`
- `glance/maintenance/application_collector.py`
- `glance/maintenance/storage_collector.py`
- `glance/maintenance/media_dev_collector.py`
- `glance/maintenance/security_collector.py`

## Observed configuration

Python metrics sidecar plus restricted socket-proxy; resource collector scheduled task running.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Schema, caching, redaction, freshness indicators and read-only Docker API permissions.
- Private installation values: Drive letters, process/service lists, application endpoints and generated resource payloads.
- Manual/platform-specific work: Replace Windows probes with per-platform adapters; preserve unknown/unavailable rather than reporting false zero.

## Storage and secrets

Collector source/configuration and generated resource-data; generated readings are replaceable, not authoritative app data.

Secret names/purposes only: Application API credentials and Windows task identity; review collector-specific secret carriers during extraction.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

Preserve approved source/configuration and task definition. Regenerate readings after recovery; never restore stale success results as live evidence.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Compare Windows host, Docker VM and container readings; simulate missing sources and confirm stale/error indicators.

## Limitations and follow-up

Runtime metrics, dashboard and socket-proxy containers currently have no explicit CPU/RAM caps; this is not a safe universal resource preset.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
