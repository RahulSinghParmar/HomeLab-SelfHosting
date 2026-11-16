# Coolify adapter validation record

Validated on 2026-11-16 against the existing Windows Docker Desktop installation.

## Live read-only audit

- Dashboard `4.5.3`, PostgreSQL 15 Alpine, Redis 7 Alpine and realtime `1.0.19` were healthy in the root Compose project.
- The digest-pinned testing host was running; Traefik `3.7` and Sentinel `1.1.5` were healthy under their separate lifecycle owners.
- No component was privileged.
- Docker-socket access existed only on the testing host, proxy and Sentinel, matching the reviewed control boundary.
- Dashboard and realtime control ports were loopback-only; application proxy ports 80/443 remained the intentional public ingress.
- Both root and proxy Compose configurations validated and the loopback dashboard health endpoint returned HTTP 200.

The sanitized audit and matching plan were written outside Git. No `.env`, `APP_KEY`, credential, SSH-key content, database row or managed application data was read.

## Backup classification

The latest scheduled control-plane backup was approximately 14.8 hours old and contained a PostgreSQL dump plus manifest. The daily backup, startup reconciliation and weekly optimization tasks last returned success.

The backup was correctly classified as unencrypted local storage with no verified off-host restore. It must not be used to claim recovery of applications, databases or volumes deployed through Coolify.

## Result and remaining gate

The current topology is healthy and the adapter generated a non-owning review plan. No production container, task, proxy, Sentinel, application, configuration or backup was changed.

The next Coolify milestone is a separately approved encrypted off-host control-plane recovery exercise using independent key custody. Fresh Windows installation, automatic updates, high availability and Coolify-managed workload recovery remain unsupported by this adapter.
