# stirling-pdf

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: stirling-pdf.
- Observed containers assigned to this module: 1.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `Stirling-PDF/docker-compose.yml`
- `Stirling-PDF/stirling-data/configs/`

## Observed configuration

2.14.2; host 9000; 4 CPUs/2 GiB runtime limit.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Login policy, JVM/job-concurrency settings and optional OCR asset selection.
- Private installation values: Accounts, hostname and custom pipeline documents.
- Manual/platform-specific work: Measure actual jobs before reducing limits or excluding components; active conversion jobs must not be interrupted by automation.

## Storage and secrets

Config, logs, pipeline and OCR tessdata bind mounts.

Secret names/purposes only: Authentication database/settings and any configured SMTP/API credentials; values not inspected.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

No dedicated scheduled backup identified. Preserve config/authentication and required pipeline/OCR assets; logs are optional retention.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Run synthetic PDF conversions, login and settings restore; verify memory cap does not break selected operations.

## Limitations and follow-up

Port binding and authentication policy need explicit review; no claim that current feature settings are universal defaults.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
