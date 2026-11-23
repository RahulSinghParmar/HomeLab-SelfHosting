# glances

Phase 1 reference runbook, observed 2026-10-03 and superseded operationally by the [Phase 7 native-lifecycle module](../native-lifecycle.md). Inventory coverage remains historical; version 0.8.0 adds live startup, privacy, controlled-restart and actual reboot evidence for the reviewed Windows host.

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

The Phase 7 adapter audits an existing installation and supplies an example policy plus reboot-evidence workflow; it still does not install Glances or implicitly adopt an unknown host. Review the exact version, listener, flags, task and paths against the [platform matrix](../platform-support.md).

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

Phase 1 performed no lifecycle action. Phase 7 later exported the task definitions and passed a controlled restart of Glances and the resource collector after correcting direct process ownership. Use the [native lifecycle workflow](../native-lifecycle.md), which never restarts hosted applications or Windows automatically.

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
