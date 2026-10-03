# matrix

Phase 1 reference runbook, observed 2026-10-03. Inventory coverage is complete at the declared scope; deployment and restore certification remain planned.

## Evidence and ownership

- Lifecycle owner: Compose: matrix-synapse.
- Observed containers assigned to this module: 7.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `matrix-synapse/docker-compose.yml`
- `matrix-synapse/data/homeserver.yaml`
- `matrix-synapse/element-config.json`
- `matrix-synapse/secrets/turnserver.conf`
- `matrix-synapse/whatsapp-data/config.yaml`
- `matrix-synapse/MATRIX-OPERATIONS.md`

## Observed configuration

Synapse 1.159.0, PostgreSQL 15.18, Element 1.12.26, TURN 4.17.2-r0, bridge 0.2607.0, admin 0.11.4, DDNS 1.

## Installation and dependencies

There is no installer/template for this module in this release. Reproduce the observed component set only in a separately approved disposable project, using compatible pinned releases and the [platform matrix](../platform-support.md). Existing state must not be implicitly adopted.

## Configuration mapping

- Reusable after review: Optional component selection, private admin bind and explicit TURN networking.
- Private installation values: server_name, federation identity, bridge sessions, client recovery material and media.
- Manual/platform-specific work: Never rename server identity during restoration; approve bridges, federation and UDP exposure separately.

## Storage and secrets

Database/config binds; separate media drive; bridge /data; secret files; TURN anonymous state volume.

Secret names/purposes only: Database password, signing keys, registration_shared_secret, macaroon_secret_key, form_secret, TURN secret, bridge as_token/hs_token/pickle_key, SMTP and DDNS token.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues. Native status uses the OS service/task manager and the verified listener.

No start, stop, restart, migration, backup or restore was executed for Phase 1. Those operations must preserve deliberately stopped/paused state and require the later module's tested workflow.

## Backup and recovery

No dedicated scheduled Matrix backup identified. Restore a consistent database/media/config/key set; client E2EE recovery is separate.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Synthetic chat persistence and optional call/bridge tests; disable federation/mail/outbound bridge actions during rehearsal.

## Limitations and follow-up

Changing domains is not a simple generic URL substitution. External DDNS token is file-mounted and must remain private.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
