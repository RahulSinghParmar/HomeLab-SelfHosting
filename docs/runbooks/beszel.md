# beszel

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: beszel; Windows service BeszelAgent.
- Observed containers assigned to this module: 1.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `beszel/docker-compose.yml`
- `beszel/custom-src/Dockerfile.production`
- `beszel/custom-src/Dockerfile.agent-windows`
- `beszel/custom-src/AUTH-ORIGIN-PATCH.md`
- `beszel/Deploy-BeszelWindowsMetricsAgent.ps1`
- `beszel/README-PRODUCTION.md`

## Observed configuration

Local 0.18.7-windows-metrics-v2 image; hub port 8090; native agent running.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Auth-origin retention of 50, Windows service discovery and GPU counter fallback.
- Private installation values: System names, agent endpoints, credentials and alert history.
- Manual/platform-specific work: Extract a reviewed patch against recorded upstream commit; retain Beszel and PocketBase MIT notices. Build currently hard-codes amd64.

## Storage and secrets

Hub named volume /beszel_data, separate backup bind mount, socket directory and native agent identity.

Secret names/purposes only: Agent authentication keys/tokens and hub notification/SMTP credentials; do not export live database records.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

Existing documentation describes PocketBase backups; backup files are mounted separately. No new restore or live schedule-setting verification performed.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Restore synthetic hub state, pair an isolated agent, verify same-origin/new-origin alert behavior and unavailable GPU semantics.

## Limitations and follow-up

Modified tracked and untracked source both matter; a Git diff alone omits Windows collector files and vendored PocketBase.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
