# glance

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: glance.
- Observed containers assigned to this module: 1.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `glance/docker-compose.yml`
- `glance/config/glance.yml`
- `glance/assets/`
- `glance/README-PRODUCTION.md`

## Observed configuration

Digest-pinned dashboard; host port 8081.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Layout/pages, widget structure and stale-data handling.
- Private installation values: Domains, API keys, account IDs, private feeds and personal statistics.
- Manual/platform-specific work: Re-register owner-selected feeds and API permissions; inspect every widget before export.

## Storage and secrets

Read-only dashboard YAML and assets; integrations consume the metrics sidecar.

Secret names/purposes only: GLANCE_CLOUDFLARE_AUTHORIZATION, GLANCE_IMMICH_API_KEY, GLANCE_JELLYFIN_API_KEY, GLANCE_NEXTDNS_API_KEY.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

Local backups-host directory exists; no dedicated scheduled Glance backup was identified. Include YAML, assets and private integration-secret bundle.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Verify each page renders real values and handles unavailable backends; restore synthetic widgets without revealing tokens.

## Limitations and follow-up

Never copy rendered screenshots or YAML wholesale into public templates; host collector paths are installation-specific.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
