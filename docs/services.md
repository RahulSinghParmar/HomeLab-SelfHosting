# Application runbook requirements

These are requirements for subsequent implementation, not complete installation instructions. Phase 1 must replace unknowns with discovered evidence before templates are released. Each module needs a pinned compatible release set, storage/secret map, configuration guide, health check, resource measurements, backup/restore procedure, and upgrade/rollback test.

## Visibility

**Glance:** preserve the useful layout while making service links, feeds and enabled pages configurable. Reproduce custom collector source; distinguish Windows-host, Docker-VM and container measurements. Protect metrics and Docker API access. Test rendered values and stale-data behavior, not only JSON parsing.

**Uptime Kuma:** separate private administration from public status pages. Allow users to select which checks become public; never publish every internal endpoint automatically. Reconcile checks idempotently without duplicates. Preserve history and notifications through database recovery where selected.

**Beszel and Glances:** host agents need native platform adapters and correct permissions. Distinguish unavailable GPU/service statistics from genuine zero usage. Package custom patches with provenance. Test hub/agent authentication and system identity across reboot.

## Personal data

**Paperless-ngx:** preserve document storage, database, exporter settings, parser/OCR language and concurrency, timezone, duplicate handling and scheduled processing. Optional Tika/Gotenberg must not run unless selected. Acceptance: ingest a synthetic multi-page PDF, verify search/metadata, export, restore and download the same document.

**AFFiNE:** retain PostgreSQL with required extensions, config/storage and release-compatible Redis. A migration container exiting successfully is normal for a one-shot job; it should not be kept running. Signup, guests, telemetry, AI and mail are explicit owner choices. Acceptance: create/edit a document, sync a second session, restart, restore and read the content.

**Nextcloud:** reproduce permitted custom image additions, app list, cron, database/cache, trusted domains/proxies, file permissions and storage. Validate background jobs and a WebDAV/native-client path. Do not disable required background activity merely to reduce idle memory. Preserve instance identity and encryption-related material.

**Firefly III:** protect APP_KEY, database, uploads and cron credentials. Confirm scheduled jobs execute once. Use synthetic transactions for create/export/restore tests; never publish personal balances or account metadata.

**Vaultwarden:** discover the active backend and backup transaction requirements; preserve attachments/sends and necessary keys. Use a synthetic vault to verify login, decryption, attachment access and restore. SMTP and registration policy require explicit configuration. Keep administration private; never test using real passwords.

**Karakeep:** identify authoritative database/assets versus rebuildable search state. Preserve bookmarks/tags and optional browser settings. Disable optional AI or browser features unless requested. Test capture/search and recovery with synthetic public content.

## Media

**Immich:** keep server, database extensions and ML release compatibility. Preserve originals and metadata; classify thumbnails and encoded videos separately. Test upload, browsing, album metadata and download after restore. Any regeneration or cleanup is separately requested, bounded and observable.

**Media management:** implement individually selectable components rather than an inseparable eight-service package. Keep download and library paths consistent; validate hardlink and atomic-move support on the actual filesystem. Preserve configuration and app databases; obtain all external credentials from the owner. Do not bundle indexer accounts or initiate downloads automatically.

**Jellyfin:** preserve database/configuration, metadata and media path mappings. A container is an option, not an automatic replacement for a native installation. Verify clients and a synthetic playback/transcode job; hardware acceleration must be proven on the target machine.

## Development and communication

**code-server:** build pinned, architecture-aware toolchains; preserve workspace files, autosave, settings, extension manifests and long-running development workflows. Explain extension marketplace/licensing differences from desktop VS Code; do not promise all desktop extensions work remotely. Repository/SSH/GPG authentication remains private. Test reconnect and server-side compilation with a sample project.

**Coolify:** discover the real source of app, database, realtime, proxy and sentinel lifecycle configuration. Preserve APP_KEY and SSH credentials. Test dashboard, terminal and real-time communication. Manage generated applications through Coolify instead of rewriting their ownership labels. Use upstream-supported Linux for the portable baseline; experimental adapters require explicit selection.

**Matrix:** server identity is not a cosmetic URL and cannot be casually renamed during restore. Preserve signing keys, database/media, client configuration and optional bridges. E2EE client recovery material is a separate concern. Test account login, message persistence and federation/calls only when enabled; TURN/UDP needs its own network design.

## Utilities and host infrastructure

**Stirling-PDF:** preserve authentication and security configuration, measure idle and real job memory, and test a synthetic PDF conversion. Low resource limits must not cause silent job failures. Do not remove components until their selected features and upstream behavior are understood.

**Portainer:** treat as privileged administration, not an ordinary public app. Preserve its configuration/database and document Docker API access. Avoid conflicting lifecycle management of the same resources across Portainer, this coordinator and Coolify.

**Cloudflare Tunnel and Tailscale:** preserve only reusable setup guidance publicly. Owner credentials, device identities and route approvals belong in private installation state. Disable these integrations in restore-test environments so a rehearsal cannot replace production routes or advertise production networks.

## Required runbook sections per module

```text
Purpose and supported scope
Verified upstream sources and licensing
Prerequisites and architecture support
Dependencies and lifecycle owner
Ports, networks and access policy
Storage and authoritative-data map
Secret names, generation and recovery requirements
Configuration and optional features
Start/stop/status and scheduled jobs
Resource measurements and limits
Backup/restore with actual content checks
Upgrade, migration and rollback
Troubleshooting and known limitations
Test evidence and supported release versions
```
