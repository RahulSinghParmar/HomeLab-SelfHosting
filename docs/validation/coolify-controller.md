# Coolify controller validation record

Validated on 2026-11-18 against the existing Windows Docker Desktop installation. Reports and plans were retained outside Git; no token, environment value, SSH key, database row, application content or generated deployment configuration was published.

## Live result

| Check | Result |
| --- | --- |
| Host | Windows, Docker Desktop `desktop-linux`, Linux amd64 engine 29.9.3 |
| Compose | 5.7.0 |
| WSL adapter | `docker-desktop` host mount accessible |
| Installed Coolify | 4.5.3; all seven reviewed components healthy/running |
| Official stable target | 4.7.5 |
| Root and proxy Compose | Valid |
| Dashboard | Local and public health returned HTTP 200 |
| Windows tasks | Daily backup, startup reconcile and weekly optimize exist; last result 0; actions match the reviewed maintenance root |
| Local backup | Fresh PostgreSQL dump plus manifest |
| Updater shim | Current upstream anchors matched exactly once |
| Sentinel limits | 0.5 CPU, 256 MiB memory, 512 MiB memory+swap and 128 PIDs |
| Controller API | Not configured; no credential was created or read |
| Generic update ownership | Denied for root, proxy and both generated application projects |

The controller correctly reported `update_available: true` and `update_ready: false`.

## Blocking gates

- Windows Docker Desktop is not an upstream-supported Coolify host.
- Encrypted off-host control-plane recovery has not been proven by an independent restore.
- The optional read-only API token is absent, so active deployments cannot be authoritatively counted.
- The target crosses the 4.6 Soketi-to-Reverb migration while the custom override still contains the legacy realtime service and its ports.

These are safety decisions, not health failures. The running deployment remained available throughout validation.

## Controlled host changes

The central update policy now names `coolify` as the controller for the root project, generated proxy and generated applications. `Manage-HomelabUpdates.ps1 -Action Controller` runs the sanitized audit and plan through the same operator entry point as generic updates while preserving separate ownership.

Sentinel had previously been recreated without its local ceilings. The existing reviewed limit script was reapplied, then the full Coolify health test and controller audit confirmed the expected limits. No Coolify image pull, database migration, restart, stop, deployment or application change was performed.

## Decision

The controller integration and Windows compatibility audit are accepted for the existing home-lab instance. Coolify 4.7.5 is not approved for this host until the off-host restore, API deployment gate and disposable Reverb migration rehearsal pass. This record does not certify fresh Windows installation, high availability, automatic updates or recovery of managed workload data.
