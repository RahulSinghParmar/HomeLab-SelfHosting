# jellyfin

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Native Windows tray/user startup.
- Observed containers assigned to this module: 0.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `NATIVE/Jellyfin/Server/config/`
- `NATIVE/Jellyfin/Server/data/`
- `NATIVE/Jellyfin/Server/metadata/`
- `NATIVE/Windows/Run/JellyfinTray`

## Observed configuration

Native jellyfin process and 0.0.0.0:8096 listener confirmed; user Run entry JellyfinTray discovered.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Native-versus-container choice and synthetic playback checks.
- Private installation values: Media paths, library IDs, users, playback history and playlist state.
- Manual/platform-specific work: Resolve exact data-root/version and startup user context privately before migration; native service conversion is not automatic.

## Storage and secrets

Native data/config/metadata/plugins and separately mapped media; no media contents inspected.

Secret names/purposes only: Administrative/API credentials and integration tokens; private application database.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

No dedicated scheduled Jellyfin backup identified in scoped task discovery. Preserve consistent database/config plus media mappings.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Recover synthetic library and playlist state, verify playback and optional hardware transcode on target OS.

## Limitations and follow-up

Tray startup is user-context dependent and must not be described as a Windows service with unattended boot guarantees.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
