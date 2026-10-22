# Nextcloud 0.6.0-alpha.6 validation

Date: **2026-10-22**

Scope: isolated generated content only; no personal users, files, credentials, external drives or production database rows

Decision: **Go for the bounded experimental local recovery candidate. No-go for production adoption, encrypted/off-host backup replacement or completed Phase 5.**

## Production boundary

The existing `nextcloud-stack` was inspected read-only for component and storage shape. It was not restarted, updated, queried for file content, used as a backup source or changed. The synthetic projects used separate roots, identities, ports and named volumes.

## Windows Docker Desktop evidence

The validated environment was Docker Engine 29.9.2 under Docker Desktop with Compose 5.6.0, eight available CPUs and a 10 GiB engine ceiling. Exact linux/amd64 image digests supplied Nextcloud 34.0.5 Apache, PostgreSQL 18.6 Alpine and Redis 8.2.10 Alpine.

A fresh source on loopback port 18030 uploaded and downloaded `phase5-nextcloud-recovery.txt` through WebDAV. The 52-byte content SHA-256 was `ce476256f7b98256056b7509ad26b09cba63be843bc0f0ac025095681da9522d`. A quiesced real cron cycle completed and the cron service returned to running state.

## Backup and restore evidence

Maintenance mode, stopped cron/app writes, a readable PostgreSQL custom archive and checksummed config/data/custom-apps/themes produced manifest ID `f3e8153ce80bc4b2b5f7611ae24e9dc4fc8289e76c96533c96727485bf8594a1`. The private recovery set also included the Nextcloud-created application database role; omitting it was proven to cause restored authentication failure.

A different project on loopback port 18031 initialized fresh Redis/PostgreSQL/HTML volumes, restored the application role and original table ownership, restored the authoritative trees and returned the exact WebDAV bytes. The recovered project was stopped and started again; all four services returned healthy/running and the module repeated the same semantic fixture check.

Clean recovered-app logs had zero matches for the four failures discovered and corrected during rehearsal: failed Nextcloud installation, `.htaccess` permission failure, PostgreSQL password failure and table privilege denial. The final idle snapshot was approximately 84 MiB app, 29 MiB PostgreSQL, 4 MiB Redis and under 1 MiB cron. All disposable containers and volumes were removed and temporary credential directories deleted.

## Automated checks

Twelve focused tests cover deterministic plans, exact image/network/port/resource contracts, file secrets, bounded database-role handling, WebDAV bytes, deterministic cron execution, confirmation gates, readable backup contracts, complete checksums, tamper rejection, derived-core initialization and ownership-preserving restore commands. The offline Phase 5 validator checks the module, CLI, images, docs and recovery markers. Repository validation, publication history, complete regression, cross-platform CI and whitespace checks remain release gates.

## Not proven

- personal deployment recovery or production-scale data;
- desktop/mobile sync, sharing, external storage, SMB, custom apps or encryption-app keys;
- public access, mail, SSO, rate limiting or Cloudflare behavior;
- image/database upgrades or rollback across versions;
- encrypted off-host storage, offline-key recovery, scheduling or retention;
- live Linux/macOS/ARM64 runtime behavior.

The next Nextcloud gate is a separately encrypted off-host clean-runner recovery rehearsal. Production adoption requires explicit owner paths, external-storage inventory, key custody, scheduling and a real-data rehearsal.
