# firefly-iii

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope. Version `0.6.0-alpha.8` adds a separate [synthetic application-aware recovery candidate](../firefly-iii-module.md); it does not adopt or certify this observed personal deployment.

## Evidence and ownership

- Lifecycle owner: Compose: firefly.
- Observed containers assigned to this module: 3.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `firefly/docker-compose.yml`
- `firefly/firefly-backup.ps1`
- `firefly/firefly-recover.ps1`
- `firefly/nginx/remoteip.conf`
- `firefly/FIREFLY-PRODUCTION.md`

## Observed configuration

Core 6.6.6, MariaDB 10.11.18 and cron image pinned by digest; loopback 8085.

## Installation and dependencies

The experimental `firefly` command can create only a new, empty, separately owned project with compatible digest-pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted. Use the [module operator workflow](../firefly-iii-module.md#operator-workflow) for disposable validation; it is not a production migration command.

## Configuration mapping

- Reusable after review: File-based secret injection, single cron owner and trusted-proxy configuration.
- Private installation values: APP_KEY, finance data, user identity, hostname and SMTP configuration.
- Manual/platform-specific work: Create portable encrypted secret export while original Windows identity is available; never test with real finance data.

## Storage and secrets

Database and secrets named volumes; upload/export binds; reverse-proxy configuration.

Secret names/purposes only: app_key, db_password and static_cron_token secret files; DPAPI-encrypted backup bundle.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed against the observed deployment for Phase 1 or `0.6.0-alpha.8`. The synthetic adapter uses a separate root, project identity, loopback port and volumes, and requires the complete reviewed plan ID for mutation.

## Backup and recovery

The observed daily task reported result 0. Its script dumps the database and saves configuration/DPAPI secrets, but the inspected implementation does not copy upload/export directories.

The separate candidate fixes those design gaps for generated data: it stops application writers, verifies `mariadb-check` and the logical dump independently, captures upload/export trees and required private inputs, checks every file, restores into fresh resources and verifies the exact synthetic finance content after restart. Its local staging backup remains plaintext-sensitive and is not a replacement for the observed backup.

Follow the [recovery contract](../recovery.md) and [Firefly validation record](../validation/firefly-iii.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Restore synthetic transactions, attachments and exports with the original test APP_KEY; separately validate the database dump, live database and recovered stop/start behavior. The isolated candidate passes this bounded check.

## Limitations and follow-up

The observed dump pipeline can mask the database command failing because gzip determines pipeline success. DPAPI alone is not portable disaster recovery. The candidate corrects dump failure detection and local asset coverage, but encrypted off-host recovery, production adoption and real independent key custody remain unproven.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
