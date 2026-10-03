# coolify

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: coolify / coolify-proxy; Coolify controller owns sentinel.
- Observed containers assigned to this module: 7.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `coolify/docker-compose.yml`
- `coolify/source/docker-compose.yml`
- `coolify/source/docker-compose.prod.yml`
- `coolify/source/docker-compose.custom.yml`
- `coolify/proxy/docker-compose.yml`
- `coolify/proxy/docker-compose.override.yml`
- `coolify/maintenance/Manage-Coolify.ps1`
- `coolify/maintenance/Backup-Coolify.ps1`

## Observed configuration

Live/root Compose app 4.3.23; resolving source Compose set reports 4.3.19. Proxy 3.7; sentinel 1.0.1. Loopback 8000/6001/6002; proxy 80/443.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Windows path adapter and management workflow as an explicitly experimental adapter.
- Private installation values: Controller identity, project IDs, user apps, SSH credentials, canonical URL and routing rules.
- Manual/platform-specific work: Reconcile exact effective source/override/env invocation before offering an update command. Exclude personal generated applications from starter templates.

## Storage and secrets

Database/cache/proxy named volumes; application/service definitions, SSH/config/source binds; controller-managed sentinel path.

Secret names/purposes only: APP_KEY, DB_PASSWORD, REDIS_PASSWORD, PUSHER_APP_SECRET, SSH keys, root bootstrap credentials and tunnel/provider credentials.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

Daily task reports success. Script dumps database and copies configuration including raw .env and SSH keys; it warns to copy to encrypted second storage.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Restore isolated controller with outbound deployment disabled; verify dashboard, terminal, realtime and one synthetic deployment.

## Limitations and follow-up

Source drift can select a different app version. Generated resources and sentinel must retain controller ownership; backup is not encrypted by this script.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
