# Phase 5 integrated disaster-recovery review

Date: 2026-11-01

Candidate: **0.6.0-rc.1**

Reference host: Windows with Docker Desktop Linux amd64 engine 29.9.2

## Decision

The six bounded Phase 5 application and encrypted-recovery pairs are integrated as one release candidate. The review is a **go for repository-level `0.6.0-rc.1` testing** and a **no-go for stable `0.6.0` publication or production backup adoption**.

The release candidate may be tagged only after the exact pushed commit passes the standard six-job validation matrix and the manual `Phase 5 integrated recovery review`. That manual workflow invokes all six reviewed recovery workflows on the same commit, with an explicit separately named repository secret for each application. Every called workflow must prepare an encrypted artifact on one hosted runner and recover it on a different clean runner.

## Common assurance contract

`modules/phase5/recovery.json` and `python tools/validate_phase5.py` enforce:

- exactly six application modules and six distinct recovery-secret names;
- one checksum-pinned Restic 0.19.1 identity for Windows and Linux amd64;
- one consistent encrypted-vault API shape across all six modules;
- distinct operational and recovery-key paths, private state, non-overlapping plaintext/repository/key locations and hidden raw Restic output;
- full repository data-pack reads before recovery evidence is accepted;
- portable manifests bound to exact application backup and snapshot identities;
- restore-gated `7 daily / 4 weekly / 3 monthly` retention, with dry-run preview by default;
- manual-only reusable workflows, read-only repository permissions, explicit secret mappings, immutable action revisions and run-scoped artifact names;
- one integrated caller that contains no shell steps and can invoke only the six reviewed workflows.

The offline contract detects structural drift. It does not substitute for the live application and browser recovery workflows.

## Application evidence matrix

| Application | Authoritative recovery set | Semantic recovery proof | Recreated or excluded state |
| --- | --- | --- | --- |
| Paperless-ngx | Exporter result, PostgreSQL dump, data, media, export and required private inputs | Imported PDF content, metadata/search and restart persistence | Broker state is recreated |
| AFFiNE | PostgreSQL, config, storage and required private inputs | Rendered note, reload, independent session and restart persistence | Redis and migration runtime are recreated |
| Nextcloud | PostgreSQL archive and role, config, data, custom apps, themes and required private inputs | Exact WebDAV bytes, application role, cron and restart persistence | Redis and core image state are recreated |
| Firefly III | MariaDB dump, uploads, exports and required private inputs | Transaction, attachment bytes, exports, cron and restart persistence | Runtime cache is recreated |
| Vaultwarden | Consistent SQLite snapshot, RSA keys, attachments, sends and required private inputs | Rendered Web Vault decryption, exact attachment and restart persistence | Temporary runtime state is recreated |
| Karakeep | Quiesced SQLite database, assets, logical export evidence and required private inputs | Rendered bookmark, full-text search, exact asset and restart persistence | Queue state and Meilisearch index are excluded and rebuilt |

All fixtures are synthetic. No personal document, note, cloud file, financial record, password-vault item or bookmark is included in repository or hosted-runner evidence.

## Read-only production reconciliation

On 2026-11-01, read-only inspection found the existing Paperless-ngx, AFFiNE, Nextcloud, Firefly III, Vaultwarden and Karakeep service families running on the Windows Docker Desktop host. Services exposing health checks reported healthy; Karakeep Chrome and Nextcloud cron were running without a declared container health check. This observation does not certify their production backups and did not adopt, stop, restart, export or modify them.

## Stable-release blockers

1. Select durable owner-controlled off-host destinations with capacity, availability and access policies appropriate to each data set.
2. Generate and custody real recovery keys independently of the Windows host and backup destination; rehearse a lost-host/lost-operational-key scenario.
3. Schedule backups, full-data checks, retention and failure notifications without exposing secrets in command lines, logs or repository files.
4. Back up non-synthetic production data with approved downtime/quiesce windows, then restore representative content into an isolated environment.
5. Record measured recovery point and recovery time objectives, storage growth, large-archive behavior and operator ownership.
6. Decide the supported production platforms. Windows Docker Desktop and hosted Linux amd64 evidence does not establish macOS, ARM64 or every Linux distribution.
7. Repeat publication, secret, staged-diff and exact-commit CI review for the eventual stable release.

## Safe handoff

The integrated workflow is a synthetic release gate, not a scheduler or production backup service. Production adoption requires a separate owner-approved plan per application. Never point its fixtures, staging roots, repositories or cleanup commands at existing application paths or volumes.
