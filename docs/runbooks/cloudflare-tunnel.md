# cloudflare-tunnel

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Windows service Cloudflared.
- Observed containers assigned to this module: 0.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `NATIVE/WindowsService/Cloudflared`
- `NATIVE/cloudflared/private-owner-configuration`

## Observed configuration

Service running with automatic startup; executable path recorded privately.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Local-first routing checklist and client/WebSocket tests.
- Private installation values: Tunnel UUID, owner domain, account, route targets and credentials.
- Manual/platform-specific work: Remote ingress/account configuration was not exported or changed; owner confirmation/API authorization needed before exact route reproduction.

## Storage and secrets

Owner-managed tunnel credentials/config and remote ingress/DNS configuration.

Secret names/purposes only: Tunnel token or credential file and account-scoped API permissions; full service arguments deliberately excluded.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

No dedicated tunnel recovery bundle verified. Re-enrollment may be appropriate for replicas; restoring a test must not replace live routing.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Validate tunnel-to-origin connectivity and selected public clients without exposing backend ports.

## Limitations and follow-up

A service being running does not prove every public route works; account-side state remains an explicit external dependency.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
