# stirling-pdf

Phase 1 production inventory plus bounded Phase 4 synthetic implementation. The existing production deployment remains outside module ownership.

## Observed deployment

- Lifecycle owner: existing Compose project `stirling-pdf`.
- Observed image: Stirling-PDF 2.14.2; host port 9000; 4 CPUs and 2 GiB runtime limit.
- Private sources: `Stirling-PDF/docker-compose.yml` and `Stirling-PDF/stirling-data/configs/` relative to the private stack root.
- Persistent concerns: configuration/authentication state, custom files, pipelines, OCR assets and any document-related logs. Do not publish their values or copy production state into a synthetic trial.

Read-only checks use the verified production container with `docker ps -a`, `docker inspect` and `docker stats --no-stream`. Do not paste unfiltered environment, inspect or log output into public issues. Preserve deliberately stopped/paused state; do not run generic pull/up or image-only rollback against production.

## Reusable candidate

The separate [experimental module](../stirling-pdf-module.md) provides digest-pinned fresh planning, loopback-only lifecycle, one real synthetic PDF operation, stopped snapshots and independent recovery. Its [validation record](../validation/stirling-pdf.md) documents Windows Docker Desktop evidence and limits.

The candidate does **not** adopt or migrate this deployment. Reusable settings need individual review: login policy, JVM/resource limits, upload limits, job concurrency, OCR languages and optional feature flags. Accounts, secrets, hostnames and custom documents remain private. Public access, authentication recovery, OCR/office/browser workloads, update/rollback and platform portability are not certified.

Before any future production migration: take an application-consistent encrypted backup; verify account and secret recovery; restore into an isolated project; exercise representative private workflows; measure peak memory/CPU; test the intended proxy/auth boundary; and retain the prior complete state until rollback is proven.

For upstream provenance, see `modules/stirling-pdf/image.json`. No third-party source is copied into this repository.
