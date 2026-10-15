# portainer

Phase 1 production reference plus the separate Phase 4 isolated-control candidate validated on 2026-10-15. The candidate does not adopt or replace the observed deployment.

## Evidence and ownership

- Lifecycle owner: Compose: portainer.
- Observed containers assigned to this module: 1.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `portainer/docker-compose.yml`

## Observed configuration

CE 2.39.6; ports 9090 HTTP and 9443 HTTPS; 1 CPU/512 MiB.

## Installation and dependencies

The optional candidate is documented in the [Portainer module guide](../portainer-module.md). It pins Portainer CE 2.39.8 and Docker-in-Docker 29.9.0 by digest and requires the exact `isolated-engine-only` permission grant. It runs as a separate project and cannot see the host Docker engine. Existing state is never implicitly adopted.

## Configuration mapping

- Reusable after review: Resource limits, loopback HTTPS and explicit isolated-engine administrative access.
- Private installation values: Users, endpoints, registry credentials and deployment metadata.
- Manual/platform-specific work: Avoid competing ownership with Coolify/coordinator; Docker Desktop socket path needs OS adapter.

## Storage and secrets

Observed production: named `/data` volume and Docker Desktop proxy socket mount.

Isolated candidate: one named Portainer `/data` volume; ephemeral nested-engine storage; private administrator password and database-encryption key mounted read-only as secrets. No host socket is mounted.

Secret names/purposes only: Admin credentials and endpoint credentials inside private configuration state.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual production Compose project for production. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues.

For the isolated candidate use only the reviewed-plan commands in the [module guide](../portainer-module.md). `exercise` performs one bounded nested-network create/inspect/delete operation and confirms cleanup. Stop, remove and backup require the complete plan ID. Remove retains data.

## Backup and recovery

No dedicated scheduled production backup was identified. The candidate implements a stopped `/data` snapshot with hashes plus the administrator password and encryption key. Its independent fresh-project restore passed; see [validation evidence](../validation/portainer.md). The snapshot is plaintext-sensitive and does not include managed workloads.

Follow the [recovery contract](../recovery.md); reported task success and old verification metadata are not a new restore rehearsal.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Restore synthetic settings and confirm only intended endpoints are reachable; test authentication/TLS separately.

## Limitations and follow-up

Administrative Docker access is effectively control of the configured Docker endpoint. The candidate exposes only a disposable nested engine; host control is not implemented. Never make public exposure the default.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
