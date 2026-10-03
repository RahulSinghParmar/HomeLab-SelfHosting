# Reference inventory

## Evidence and limits

Read-only discovery on 2026-10-03 observed 54 Docker containers: 53 running and one successfully exited AFFiNE migration job. Configured health checks reported healthy at that snapshot. This is not a functional audit of every application, a backup guarantee, or a claim that future users need 54 containers.

Observed Docker Engine: 29.8.1; Compose: 5.5.1. The reference WSL configuration set an 8-processor ceiling, 10 GB memory ceiling, 8 GB swap, and gradual memory reclamation. Older local documentation listed different values. Live configuration and dated evidence must take priority over old notes.

The public inventory intentionally omits private domains, accounts, credentials, actual storage paths, tunnel IDs, personal project IDs, and document contents.

## Discovered deployment groups

| Group | Components | Packaging work required |
| --- | --- | --- |
| Visibility | Glance, custom metrics collector, Docker API proxy, Uptime Kuma | Separate reusable widgets from private endpoints; document check registration |
| AFFiNE | Server, one-shot migration, PostgreSQL/pgvector, Redis | Preserve workspace storage and migration ordering |
| Paperless-ngx | Web/worker, PostgreSQL, Valkey | Preserve exporter workflow and low-concurrency OCR configuration |
| Nextcloud | Custom app and cron images, PostgreSQL, Redis | Reproduce SMB-related image additions; preserve cron and app configuration |
| Immich | Server, ML worker, PostgreSQL extensions, Valkey | Pin the compatible release set and document originals versus derived files |
| code-server | Custom developer image | Rebuild toolchains/extensions; remove hard-coded x64 build assumptions |
| Coolify | App, database, cache, real-time service, custom host integration | Reconcile effective Compose sources and lifecycle ownership |
| Coolify-managed components | Proxy, sentinel, generated deployments | Do not force these into an unrelated Compose owner |
| Matrix | Synapse, database, Element, TURN, optional bridge/admin/DDNS | Protect identity/signing keys; separate optional integrations |
| Firefly III | App, MariaDB, scheduler | Preserve application encryption key and reliable cron |
| Karakeep | App, browser worker, search index | Verify authoritative storage and avoid unnecessary browser concurrency |
| Media management | Sonarr, Radarr, Lidarr, Prowlarr, Bazarr, Seerr, FlareSolverr, qBittorrent | Consistent media paths, permissions, and optional integrations |
| Beszel | Custom hub image and native Windows agent | Publish permitted patch/build provenance and host-statistics adapter |
| Portainer | Administrative container | Restricted endpoint and explicit Docker control permission |
| Stirling-PDF | PDF utility | Document authentication and measured low-idle configuration |
| Vaultwarden | Password manager | Verify actual database backend, attachments, keys, and restore completeness |

## Native and scheduled components

Windows service discovery found Cloudflared, Tailscale, BeszelAgent, and WSLService running with automatic startup. Native Jellyfin and Glances belong to the intended inventory, but their full current configuration and recovery paths still need Phase 1 verification.

Scheduled-task discovery found daily/weekly/monthly AFFiNE and Paperless backup tasks, media-stack backup, Coolify backup, Firefly backup, and custom monitoring/resource-check tasks. A scheduled task existing does **not** establish that its most recent backup is complete or recoverable.

Existing application documents describe prior AFFiNE and Paperless restore exercises. The recorded Paperless exercise used an empty document set, so it cannot serve as proof of real document recovery. The new release process requires nonempty synthetic content tests.

## Important extraction gaps

- Full effective configuration includes override files, environment references, image layers, generated settings, databases, and native tasks—not just a directory's first Compose file.
- Local images are not reproducible until Dockerfiles, permitted patches, dependencies, and build context have been reviewed.
- Some upstream image references float; observed tags are not a supported-version lockfile.
- Older backup metadata deliberately omitted raw secrets. A separate encrypted recovery-secret export is required for complete disaster recovery.
- Custom dashboards and metrics may contain private endpoints, tokens, identifiers, or personal financial/media statistics.
- Machine-generated project names and monitoring records are installation state, not universal defaults.

Phase 1 will produce a private detailed inventory and a reviewed public configuration mapping. No live files have been bulk-copied into this repository.
