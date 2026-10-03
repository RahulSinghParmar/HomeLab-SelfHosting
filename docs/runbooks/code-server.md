# code-server

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: code-server.
- Observed containers assigned to this module: 1.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `code-server/docker-compose.yml`
- `code-server/Dockerfile`
- `code-server/extensions.txt`
- `code-server/scripts/install-extensions.sh`
- `code-server/data/code-server/config.yaml`

## Observed configuration

Custom 4.131.0 image; upstream base digest pinned; runtime limit 6 CPUs/6 GiB; host port 8443 maps HTTP 8080.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Autosave/reconnect configuration, curated extension manifest and server-side toolchain layout.
- Private installation values: Workspace paths, auth material, Git identities and extension state.
- Manual/platform-specific work: Replace hard-coded Node linux-x64 tarball and verify architecture-specific hashes; review extension licenses/availability.

## Storage and secrets

Config and local extension/tool state binds; named secure SSH/GPG volume; user-workspace bind.

Secret names/purposes only: Config password, SSH/GPG keys, Git credentials and private repositories.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

No dedicated scheduled backup identified. Preserve workspaces, settings/manifests and encrypted private credentials separately.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Rebuild isolated image, compile sample project, reconnect from another device and restore settings/workspace.

## Limitations and follow-up

Pinned base alone does not pin apt packages or unversioned extensions. Port number 8443 does not establish TLS.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
