# tailscale

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Windows service Tailscale.
- Observed containers assigned to this module: 0.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `NATIVE/WindowsService/Tailscale`
- `NATIVE/Tailscale/private-device-state`

## Observed configuration

Service running with automatic startup; no private network policy or device keys exported.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Optional private access and approval checkpoints.
- Private installation values: Tailnet policy, node identity, ACLs and advertised routes.
- Manual/platform-specific work: New-machine enrollment and route approvals are owner-controlled; cross-platform native installation required.

## Storage and secrets

Native device state and owner-managed account policy/routes.

Secret names/purposes only: Device keys and any enrollment/auth keys; do not reuse another owner's machine identity.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

Prefer documented re-enrollment for a new identity; any preserved device state belongs in encrypted private recovery.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Verify approved connectivity and least-privilege routing using a test node where authorized.

## Limitations and follow-up

Service state is not proof of peer reachability. No automatic copying of network identity into clone/fork installs.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
