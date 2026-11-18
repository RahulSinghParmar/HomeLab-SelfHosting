# Changelog

## 0.8.0-alpha.8 — 2026-11-18

- Normalized the reviewed Windows custom-Compose path with `PureWindowsPath` before joining it to a test/runtime root, preserving Windows behavior while making the controller contract portable on Linux and macOS validators.
- Superseded the alpha.7 candidate after GitHub CI exposed the platform-specific path interpretation; no live Coolify state or controller policy changed.

## 0.8.0-alpha.7 — 2026-11-18

- Added a dedicated Coolify controller audit and fail-closed plan with official stable-channel discovery, Windows Docker Desktop/WSL compatibility checks, scheduled-task validation, updater-shim anchor checks and Sentinel resource-limit verification.
- Made controller ownership explicit in generic Docker audits and redirected root, proxy and generated Coolify projects away from generic apply planning.
- Added a central PowerShell controller action with optional transient token-file support for aggregate active-deployment checks; no credential is persisted.
- Validated the healthy 4.5.3 reference instance against stable 4.7.5 while correctly blocking update readiness on upstream Windows support, encrypted off-host recovery, missing API visibility and the Soketi-to-Reverb migration.
- Reapplied and verified existing Sentinel limits after controller recreation; no Coolify image pull, restart, update or migration was performed.

## 0.8.0-alpha.6 — 2026-11-18

- Added a cross-platform Docker Compose update manager with read-only project/image inventory, optional remote digest checks and exact remote OCI version inspection.
- Separated audit, plan and apply; rejected rolling target tags, repository switches, changed Compose files, changed running images, unreviewed services and controller-managed projects.
- Added stopped application-path backups with byte-hash verification, exact single-service image pinning, Compose validation, bounded recreation, health checks, update locks and retained recovery journals.
- Recorded a sanitized 19-project/56-service Windows reference audit while keeping private paths, reports, plans, application data and credentials outside Git.
- Exercised the workflow on the ARR stack with exact image targets, isolated recovery sets and successful HTTP/log/database validation; this is installation evidence, not automatic production adoption for other stacks.

## 0.8.0-alpha.5 — 2026-11-16

- Added a strict Matrix/Element integration plan and evidence contract that preserves the server name and signing key, requires loopback direct HTTP bindings, and validates public endpoints after restart.
- Added a secret-free UDP/TCP STUN probe plus a manual external workflow with optional temporary authenticated relay credentials; selected TURN cannot pass without independent relay and real audio/video call evidence.
- Validated the live Synapse 1.164.2, Element 1.12.33, `.well-known`, native Cloudflare Tunnel, coturn 4.18.0 and shared-secret parity without reading accounts, messages, media or secret values.
- Restricted live Synapse and Element direct ports to loopback with an exact rollback copy and no image pull, then passed local/public health, identity, signing-key equality and controlled-restart checks.
- Diagnosed the public TURN failure as a stale direct DNS record caused by the dedicated DDNS token's client-IP restriction after the ISP address changed; TURN remains explicitly uncertified.

## 0.8.0-alpha.4 — 2026-11-16

- Added a deterministic, nonexecuting code-server migration policy and strict evidence validator bound to the reviewed 4.145.0/Node 24.19.0 candidate and Restic 0.19.1 checksums.
- Created a stopped-state encrypted snapshot of production config, editor state, Linux secure volume, workspace and build metadata; repository data was fully read and the recovery key was placed on a physical disk separate from the repository and source.
- Restored the encrypted snapshot into an independent temporary root, verified archive hashes, 20 persisted extensions, server-side compilation, HTTP health and restart persistence, then removed every plaintext staging/restore copy.
- Migrated the live container from the mismatched 4.144.0 tag/4.131.0 binary to exact 4.145.0, retained all four mounts and 6 CPU/6 GiB/512 MiB/2,048 PID limits, bound port 8443 to loopback, and passed local/public health after a Compose restart.

## 0.8.0-alpha.3 — 2026-11-16

- Added a read-only existing-instance Coolify adapter for the reviewed Windows Docker Desktop topology without claiming upstream production support or fresh-install capability.
- Recorded separate lifecycle ownership for the five root Compose services, Coolify-generated Traefik proxy and scheduler-managed Sentinel instead of relabeling them as one Compose project.
- Audited all seven live components, both Compose definitions, the loopback health endpoint and the latest control-plane backup without reading `.env`, `APP_KEY`, credentials or managed application data.
- Kept updates manual and blocked update-readiness until encrypted off-host control-plane recovery is proven; each managed application's data remains outside the Coolify instance-backup claim.

## 0.8.0-alpha.2 — 2026-11-16

- Added digest-pinned multi-architecture Synapse 1.164.2, PostgreSQL 15.19 and Element Web 1.12.35 planning with a loopback-only, resource-bounded Compose renderer.
- Made the Matrix server name and signing key explicit immutable recovery material and kept client E2EE-key recovery as a separate owner-validated responsibility.
- Passed an isolated account/login, private-room, text-event and exact-media exercise followed by quiesced PostgreSQL backup, source deletion and independent-root recovery.
- Audited the healthy seven-container production Matrix stack read-only, recorded its floating-image risk and left its users, rooms, messages, credentials, media, bridges, TURN and public routing unchanged.

## 0.8.0-alpha.1 — 2026-11-16

- Started Phase 7 with a digest-pinned, architecture-aware code-server 4.145.0 build and verified Node 24.19.0 archives for amd64 and arm64.
- Added 18 pinned extensions, broad server-side toolchains, copy-once editor persistence defaults and a loopback-only restricted Compose renderer.
- Passed an isolated Windows Docker Desktop compile, forced recreation, stopped-state backup and independent-root recovery trial without reading or changing production workspaces or credentials.
- Recorded the live tag/binary mismatch (`4.144.0` tag versus `4.131.0` binary) as a migration blocker instead of replacing the healthy production container.

## 0.7.0 — 2026-11-15

- Added eight individually selectable, digest-pinned media-management integrations with dependency validation, loopback/internal access, resource limits and no implicit provider or download activity.
- Proved stopped-state configuration recovery across all eight integrations using two low-memory internal-network rehearsals, 24 SQLite checks, shared `/data` hardlink/atomic-move validation and independent healthy restores.
- Added a separate native Jellyfin acceleration contract: Intel QSV passed CPU, single-stream, two-stream and HEVC synthetic output validation while retaining CPU fallback.
- Kept the reference GeForce GT 730 NVENC path blocked at driver 391.35, below Jellyfin's current Windows requirement; HDR, low-power encoding and four-stream concurrency remain unapproved.
- Revalidated retained Jellyfin application and encrypted off-host media recovery evidence, preserved prior Immich clean-runner evidence, and added a final Phase 6 closure validator.
- Left the existing production media stack, Jellyfin configuration, personal media, external providers and private credentials unchanged.

## 0.7.0-alpha.6 — 2026-11-11

- Added a strict Jellyfin recovery set containing the built-in application archive and a separately managed synthetic media original, each bound by SHA-256.
- Added checksum-pinned Restic 0.19.1 encryption, separate operational/recovery-key custody, a tamper-evident portable manifest and complete repository-data checks.
- Deleted all source application/media state and operational custody before recovering through a clean same-version target from encrypted transport plus the independent recovery key.
- Proved exact direct play before backup, after recovery and after restart; added reusable validators and focused contract tests.
- Kept production Jellyfin, media, users, playlists, settings, GPU and transcoding unchanged; physical owner off-host storage and scheduling remain unconfigured.

## 0.7.0-alpha.5 — 2026-11-10

- Added a disposable native-Windows Jellyfin 12.4 application-recovery rehearsal using generated credentials and a synthetic MP4 only.
- Created and validated Jellyfin's built-in database/configuration/metadata/subtitle/trickplay archive, deleted the source application state and restored into an unrelated initialized same-version target.
- Proved byte-exact HTTP direct play before backup, after restore and after a full recovered-instance restart.
- Added strict recovery-evidence validation and documented the independent media-original backup boundary.
- Kept the production Jellyfin service, media, users, playlists, settings, GPU and transcoding unchanged.

## 0.7.0-alpha.4 — 2026-11-09

- Added a privacy-bounded Jellyfin audit that distinguishes native, container, absent and conflicting ownership without reading media or credentials.
- Required an explicit native/container choice, blocked unsupported Windows/macOS containers and refused implicit deployment-type migration.
- Pinned the official Jellyfin 12.4 image by immutable digest and added a Linux-only loopback/read-only/non-root/bounded Compose renderer with no host control or device access.
- Recorded the running native Windows 12.4.0 reference result and retained CPU fallback for the GT 730/391.35 pending a separately approved codec-level synthetic transcode.
- Defined the built-in archive and same-version restore boundary without creating a production backup or changing the live service.

## 0.7.0-alpha.3 — 2026-11-03

- Added a checksum-pinned Restic vault for verified Immich PostgreSQL and protected-original recovery sets with separate operational and recovery-key references.
- Added encrypted snapshots, complete repository-data reads, exact manifest/original validation, portable recovery manifests and restore-gated 7-daily/4-weekly/3-monthly retention.
- Added a two-runner clean-room workflow that transports only the encrypted synthetic repository and nonsecret manifest while injecting the recovery key independently.
- Proved local encryption, decryption, exact original recovery and stop/start persistence without reading or changing production media; the rehearsal now removes its source stack before recovered startup to reduce peak Docker Desktop memory.

## 0.7.0-alpha.2 — 2026-11-02

- Added a loopback-only Immich 3.3.5 lifecycle with private database secret injection, exact image digests, internal backend networking and ownership/drift checks.
- Protected PostgreSQL plus `library`, `upload` and `profile` in a quiesced, hash-bound recovery set while excluding derived media, Valkey state and ML model cache.
- Preserved only required derived-directory `.immich` integrity markers so a minimal recovery set passes application startup without retaining thumbnails or encoded video.
- Proved exact synthetic original upload/download, continued browsing with ML stopped, independent fresh-project restore and recovered stop/start persistence on Windows Docker Desktop.
- Limited CPU machine learning independently to 1 CPU, 1536 MiB, 256 PIDs, one worker/thread lane, one-item face/OCR batches and a 60-second idle model TTL.

## 0.7.0-alpha.1 — 2026-11-02

- Started Phase 6 with a strict authoritative/derived/cache media policy that protects originals and keeps destructive cleanup confirmation-gated.
- Pinned the compatible Immich 3.3.5 server, machine-learning, Valkey and PostgreSQL release set to immutable image digests without pulling or starting it.
- Added privacy-bounded read-only Docker/NVIDIA capability auditing and deterministic disabled planning with CPU fallback.
- Kept thumbnail, OCR, recognition, indexing, scanning and transcoding work manual and bounded the proposed four-component stack to 6 GiB.
- Recorded the reference GT 730/391.35 result as unsupported for current Immich CUDA requirements; no GPU workload or production-media operation was attempted.

## 0.6.0 — 2026-11-02

- Closed Phase 5 with one machine-readable recovery-kit contract covering six application-consistent backups and their authoritative recovery material.
- Bound every module to nonempty synthetic fixture content and application-level clean-runner restore proof, including restart persistence rather than backup-file existence alone.
- Added a final closure validator for separate-key Restic encryption, complete repository data checks, portable manifests and restore-gated 7/4/3 retention.
- Preserved production boundaries: no owner repository, recovery key, scheduled task, notification credential or personal data was created or adopted by the public release.

## 0.6.0-rc.2 — 2026-11-01

- Added a strict owner-operated Phase 5 policy for two off-host encrypted repositories, two independently custodied offline recovery-key copies, capacity reserves, RPO/RTO inputs and all six application schedules.
- Added deterministic disabled planning with terminal path/device redaction, secret-value rejection, storage separation checks, restore-gated 7/4/3 retention and explicit production-readiness blockers.
- Documented hidden/non-overlapping Windows task requirements and reconciled existing task patterns read-only without installing, changing or replacing any task.
- Retained no-go boundaries for stable 0.6.0 and production adoption until owner media, real keys, replica transport, notification delivery, reboot-tested scheduling and representative production-data recovery pass.

## 0.6.0-rc.1 — 2026-11-01

- Integrated all six Phase 5 application-aware encrypted recovery modules behind one manual exact-commit release gate.
- Made each off-host workflow reusable while preserving manual dispatch, read-only permissions, separate module secrets, immutable actions and two-runner artifact/recovery isolation.
- Added a machine-readable assurance matrix enforcing one reviewed Restic identity, vault API parity, distinct workflow secrets, evidence coverage and restore-gated 7/4/3 retention.
- Added focused integrated-contract regression tests plus combined architecture, recovery, platform, validation and release documentation.
- Retained a no-go for stable 0.6.0 and production adoption until durable owner storage, real offline-key custody, scheduling, alerts and representative production-data restore drills are approved and verified.

## 0.6.0-alpha.13 — 2026-11-01

- Added a checksum-pinned Restic vault for verified Karakeep SQLite/assets recovery sets with distinct operational and recovery-key custody.
- Added encrypted storage, full repository data checks, exact snapshot restore, portable off-host manifests and restore-gated 7-daily/4-weekly/3-monthly retention.
- Added a manual two-runner clean-room workflow that transports only the encrypted synthetic repository and nonsecret manifest while injecting its recovery key separately.
- Added clean-runner Karakeep restoration with Meilisearch rebuild, rendered bookmark verification, full-text search, exact asset download and restart persistence.
- Added eighteen focused encrypted-vault tests, expanded Phase 5 validation and retained no-go boundaries for personal-data adoption, durable owner storage, scheduling and stable 0.6.0.

## 0.6.0-alpha.12 — 2026-10-31

- Added a digest-pinned, loopback-only Karakeep 0.34.1 recovery adapter with separate Chrome and Meilisearch services on a private bridge.
- Added rendered synthetic signup/API-key creation, searchable text bookmark and exact PNG asset validation without exposing generated credentials in public evidence.
- Added built-in logical export inspection plus quiesced SQLite/assets backup with `PRAGMA quick_check`, sanitized metadata and complete checksums.
- Added fresh-project restore that excludes queue/index state, triggers authenticated Meilisearch reindexing and repeats rendered title, full-text search and byte-exact asset checks after restart.
- Added focused planning, hardening, ownership, secret, semantic, integrity and tamper tests plus expanded Phase 5 release validation.
- Preserved no-go boundaries for production adoption, personal data, encrypted off-host recovery, scheduling, retention, external AI, public access and stable 0.6.0.

## 0.6.0-alpha.11 — 2026-10-30

- Added a Vaultwarden Restic 0.19.1 vault with exact Windows/Linux amd64 checksums, distinct operational/recovery key custody, complete repository data checks and portable recovery manifests.
- Added confirmation-gated encrypted store, decrypt, status and restore-gated 7/4/3 retention commands under `vaultwarden-vault`.
- Added a manual two-runner rehearsal that transfers only the encrypted synthetic repository and nonsecret manifest, injects the recovery key separately and reconstructs a fresh Vaultwarden project.
- Bound recovery proof to the complete backup manifest, vault-item count, exact attachment size/hash, rendered secure-note decryption, independent browser sessions and recovered restart persistence.
- Bound Linux Vaultwarden execution to the private host directory's numeric owner and matched the private tmpfs ownership, preserving capability-free execution without world-readable recovery data.
- Added eighteen focused vault tests and expanded repository, platform, recovery and release validation without touching the personal Vaultwarden deployment.
- Preserved no-go boundaries for production adoption, durable backup hosting, scheduling, real offline-key custody, advanced Vaultwarden features, Karakeep and stable 0.6.0.

## 0.6.0-alpha.10 — 2026-10-30

- Added a digest-pinned, loopback-only Vaultwarden 1.37.1 recovery adapter with a private bridge, read-only root, dropped capabilities, no-new-privileges and bounded CPU, memory, PID and log resources.
- Added a Playwright/Chromium Web Vault fixture that registers a generated user, creates and decrypts one secure note, uploads/downloads exact attachment bytes, and proves reload, independent-session and restart persistence.
- Added application-consistent backup using Vaultwarden's built-in SQLite snapshot plus quiesced RSA keys, attachments, sends, optional configuration, generated recovery inputs, sanitized metadata and complete checksums.
- Restored the recovery set into an unrelated fresh project and repeated browser decryption, attachment download and recovered restart validation on Windows Docker Desktop.
- Added nine focused tests and expanded repository/Phase 5 documentation and validation while retaining no-go boundaries for personal-vault adoption, encrypted off-host recovery, scheduling, Karakeep and stable 0.6.0.
- Increased the unchanged cross-platform matrix job ceiling from 20 to 30 minutes after Windows/Python 3.12 reached the old limit while its regression assertions were still passing; no test or platform gate was removed.

## 0.6.0-alpha.9 — 2026-10-23

- Added a Firefly III Restic 0.19.1 vault with exact Windows/Linux amd64 checksums, distinct operational/recovery key custody, full-data checks and portable recovery manifests.
- Added confirmation-gated encrypted store, decrypt, status and restore-gated 7/4/3 retention commands under `firefly-vault`.
- Added a manual two-runner rehearsal that transfers only the encrypted synthetic repository and nonsecret manifest, injects the key separately and reconstructs a fresh Firefly project.
- Bound recovery proof to the complete backup manifest, transaction count, raw attachment size/hash, upload/export file counts and recovered stop/start persistence.
- Added eighteen focused vault tests and expanded repository, security, platform and release validation without touching the personal Firefly deployment.
- Preserved no-go boundaries for production adoption, durable backup hosting, scheduling, real offline-key custody, bank/import integrations and stable 0.6.0.

## 0.6.0-alpha.8 — 2026-10-23

- Added a digest-pinned, loopback-only Firefly III 6.6.6/MariaDB 10.11.18/Alpine 3.22 adapter with private generated secrets, an internal dependency network and bounded resources.
- Added one exact synthetic finance transaction, raw 49-byte attachment round trip, two supported exports, the Firefly integrity report and a controlled real cron call.
- Added application-quiesced backup of an independently checked logical MariaDB dump, upload/export trees, private recovery inputs, sanitized metadata, complete checksums and semantic fixture evidence.
- Restored into an unrelated fresh project, verified the live database and exact application content, and repeated verification after a recovered stop/start cycle on Windows Docker Desktop.
- Fixed Windows-copied restore ownership with a disposable root helper limited to `CAP_CHOWN`; long-running services retain their non-privileged security profile.
- Added twelve focused tests and expanded repository/Phase 5 documentation and validation while retaining no-go boundaries for production adoption, encryption/off-host retention, scheduling and stable 0.6.0.

## 0.6.0-alpha.7 — 2026-10-23

- Added a Nextcloud Restic 0.19.1 vault with exact Windows/Linux amd64 checksums, distinct operational/recovery key custody, complete data checks and portable recovery manifests.
- Added confirmation-gated encrypted store, check, decrypt, status and restore-gated 7/4/3 retention commands under `nextcloud-vault`.
- Added a manual two-runner rehearsal that transfers only the encrypted synthetic repository and nonsecret manifest, injects the recovery secret separately and reconstructs a fresh Nextcloud project.
- Repeated exact WebDAV content and recovered stop/start persistence checks after clean-runner decryption, with production data explicitly excluded.
- Fixed recovered-project restart validation so an already-owned stopped Compose project does not mistake its retained or recently released loopback binding for a foreign listener; Docker still enforces the bind on restart.
- Preserved no-go boundaries for production adoption, external-drive recovery, durable backup hosting, scheduling, real offline-key custody and stable 0.6.0.

## 0.6.0-alpha.6 — 2026-10-22

- Added a digest-pinned, loopback-only Nextcloud 34.0.5/PostgreSQL 18/Redis 8.2 adapter with file-based secrets, internal dependency networking, separate cron and bounded resources.
- Added a deterministic WebDAV upload/download fixture and quiesced real cron execution, including contention-safe cron service handling.
- Added maintenance-mode, application-quiesced backup of a readable PostgreSQL custom archive, the application database role, config, data, custom apps, themes, private recovery inputs, sanitized metadata and complete checksums.
- Restored into an unrelated fresh project with derived-core initialization, original PostgreSQL ownership, exact WebDAV comparison and recovered stop/start persistence on Windows Docker Desktop.
- Added twelve focused tests, batched Windows tree ACL verification and explicit no-go boundaries for production adoption, external storage, custom SMB builds, encryption/off-host retention, public access and stable 0.6.0.

## 0.6.0-alpha.5 — 2026-10-21

- Added a digest-pinned Playwright/Chromium validator that creates and renders a synthetic AFFiNE note through the supported UI, then proves reload, independent-session, source-restart, restored-state and recovered-restart persistence.
- Added Windows-safe private screenshot evidence transfer without weakening directory ACLs, plus idempotent recovery verification and automatic cleanup of disposable validation volumes.
- Added an AFFiNE Restic 0.19.1 vault with separate operational/recovery key custody, complete data checks, portable manifests, recovery-gated retention and exact Windows/Linux amd64 checksums.
- Added a manual two-runner GitHub Actions rehearsal that transfers only the encrypted synthetic repository and nonsecret manifest, injects the test key separately and performs application/browser recovery on a clean runner.
- Preserved the production AFFiNE deployment untouched and retained no-go boundaries for production adoption, durable backup hosting, real offline-key custody, scheduling, native clients, representative scale and stable 0.6.0.

## 0.6.0-alpha.4 — 2026-10-20

- Added a digest-pinned, loopback-only AFFiNE 0.27.4/PostgreSQL pgvector/Redis adapter with a normal one-shot migration, private generated credentials, internal dependency networking and bounded resources.
- Added a nonempty server-sync exercise that creates an AFFiNE workspace, writes a bounded Yjs marker, verifies it through a second independent authenticated session and proves application restart persistence.
- Added application-quiesced PostgreSQL/config/storage backup with private recovery inputs, sanitized metadata, complete checksums and post-backup content verification.
- Restored into an unrelated fresh project, ran the pinned migration, verified semantic state equality and repeated verification after restart on Windows Docker Desktop.
- Added ten focused tests, expanded the offline Phase 5 validator and retained explicit no-go boundaries for production adoption, browser/client feature coverage and encrypted off-host recovery.

## 0.6.0-alpha.3 — 2026-10-19

- Added a path-independent Paperless recovery manifest and confirmation-gated clean-host recovery plan.
- Added reviewed Restic 0.19.1 Linux amd64 archive/executable checksums alongside the Windows amd64 contract.
- Added a manual two-runner GitHub Actions rehearsal: the first runner creates and uploads only the encrypted synthetic repository; the second independently downloads, checks, decrypts, imports and restart-tests it.
- Kept the synthetic recovery key in a repository Actions secret rather than the uploaded repository artifact, and pinned artifact actions by immutable commit.
- Retained explicit no-go boundaries for production-data migration, permanent backup hosting, scheduling, real offline-key custody, API-token recovery and stable 0.6.0.

## 0.6.0-alpha.2 — 2026-10-19

- Added a separate Paperless encrypted-vault workflow for reviewed restic validation, dual key files, repository initialization, store, full data check, restore, status and restore-gated retention.
- Locked restic 0.19.1 Windows amd64 to its official release URL and reviewed archive/executable SHA-256 values; no automatic or global installation is performed.
- Bound encrypted snapshots to complete nonempty Paperless manifests and required full decrypted backup verification before adding the protected recovery tag.
- Verified one generated document through application backup, encryption, repository check, decryption, independent Paperless import and stop/start persistence on Windows Docker Desktop.
- Added thirteen focused vault tests, expanded the offline Phase 5 validator, and made Phase 5 validation an explicit cross-platform CI step.
- Removed every synthetic container, volume, plaintext/key/repository artifact after validation; production Paperless remained healthy and unchanged.
- Retained explicit no-go boundaries for off-host/clean-machine recovery, scheduling, production migration, live prune, cross-platform runtime and stable 0.6.0.

## 0.6.0-alpha.1 — 2026-10-16

- Added a digest-pinned, loopback-only Paperless-ngx 3.2.1/PostgreSQL 18/Valkey 9 adapter with separate internal networking, private generated credentials, bounded resources and data-preserving lifecycle.
- Added a nonempty synthetic PDF exercise that verifies consumption, searchable text, metadata editing and exact original-file checksum.
- Added an application-quiesced exporter, semantic inventory, readable PostgreSQL custom dump, data/media/export capture, private/sanitized configuration and checksum manifest.
- Restored the exporter set into an independent project and verified semantic equality plus stop/start persistence on Windows Docker Desktop; production services remained read-only.
- Selected restic for a future encrypted repository layer, while explicitly retaining plaintext/off-host/key-custody/retention work as incomplete.

## 0.5.0-rc.1 — 2026-10-15

- Integrated the independently gated Glance, Uptime Kuma, Beszel, Stirling-PDF and opt-in Portainer adapters into one bounded Phase 4 release candidate without enabling general planner execution or production adoption.
- Added an offline Phase 4 contract validator covering the declared CLI surfaces, public module/evidence files and exact SHA-256 image pins.
- Added a combined validation record and support matrix that keep authenticated Beszel UI, Windows reboot/state, exact-commit CI and cross-platform runtime gates explicit; stable 0.5.0 remains a no-go until those declared gates pass.

- Added an opt-in Portainer CE 2.39.8 candidate with an exact `isolated-engine-only` permission grant, no host Docker socket, loopback HTTPS and a disposable internal Docker-in-Docker endpoint.
- Added strict image/command/privilege/mount/network/resource/ownership drift checks plus a real Portainer API create-inspect-delete exercise proving host resources remain invisible.
- Added private administrator and database-encryption secrets, stopped `portainer.edb` snapshots and a successful independent authenticated recovery exercise; nested workloads are deliberately ephemeral and excluded.
- Recorded low idle resource use, removed all disposable validation resources and left the existing 2.39.6 production Portainer deployment unchanged; host control, public access and production upgrade remain uncertified.
- Added an isolated digest-pinned Stirling-PDF 2.14.2 candidate with loopback-only access, a read-only root, minimal entrypoint capabilities, bounded tmpfs/resources and strict ownership/drift checks.
- Added an in-memory synthetic rotation exercise that validates Flate-compressed PDF page syntax, plus stopped five-volume snapshots and independent fresh-project recovery evidence.
- Recorded Windows Docker Desktop health, resource and recovery results without adopting or changing the existing production Stirling-PDF container; public/authenticated and advanced conversion workloads remain uncertified.
- Added a closed-schema Uptime Kuma desired-state adapter for bounded HTTP monitors, status-page groups, webhook/SMTP notification profiles, safe drift inspection and explicit delivery tests.
- Added exact private secret references, redacted public validation, notification-aware v2 backup evidence and backward verification for v1 synthetic snapshots.
- Preserved the isolated two-container ownership contract; no production Kuma state is discovered, imported or modified.

## 0.5.0-alpha.2 — 2026-10-04

- Added a separately gated, digest-pinned Uptime Kuma trial with two synthetic HTTP monitors, generated private credentials and one selected status-page monitor.
- Added bounded lifecycle, drift/ownership checks, idempotent registration and fixture-only up/down controls; no Docker socket, production adoption or notification configuration.
- Added stopped-state whole-data snapshots, SQLite/content verification and recovery into a fresh independent named volume, preserving account identity, monitor IDs and heartbeat history.
- Verified rendered up/down/up transitions, restart/retry persistence and restored page content on Windows Docker Desktop Linux amd64.
- Added 31 Kuma regression tests; documented plaintext snapshot sensitivity, optional DNS-daemon warning and unsupported monitor/platform/update cases.
- Existing services remain untouched; general deployment and full Phase 4 remain incomplete.

## 0.5.0-alpha.1 — 2026-10-04

- Added a separate experimental Glance starter: reviewed plans, private owned state, bounded Docker lifecycle, configuration export and independent starter recovery.
- Pinned the tested amd64 image by digest; loopback binding, dedicated bridge, no Docker socket, read-only configuration/root filesystem and fixed resource/log limits.
- Added drift, foreign-resource, context, port and interruption guards plus regression tests.
- Found and corrected an internal-only Docker network that accepted but did not publish the requested port; verify effective bindings as well as requested ones.
- Recorded Windows live rendering, retry, restart, configuration recovery and measured lightweight resource usage.
- Full Phase 4, general application execution, custom-dashboard recovery and other platform runtime certification remain pending. Existing deployments were not modified.

## 0.4.0 — 2026-10-03

- Added separately gated synthetic file-module planning, apply, verified status and non-destructive retirement.
- Added private local storage with Windows owner/DACL verification and POSIX owner/mode enforcement; no automatic elevation or existing-folder permission repair.
- Added reusable 256-bit generated credentials, reference-only reports, ownership markers and fingerprint checks.
- Added kernel operation locks, atomic state snapshots, ordered journals, retry reconciliation and fail-closed handling of ambiguous partial writes.
- Added real filesystem, lock contention/process death, interruption, tampering, retention and CLI privacy tests.
- Application deployment remains disabled; no existing containers, service settings or user data were changed.

## 0.3.0 — 2026-10-03

- Added a Python 3.12+ selection wizard, strict private settings validation, offline deterministic plans and read-only host doctor.
- Added thin PowerShell/POSIX launchers and runnable Windows/Linux/macOS settings examples.
- Added provisional module budgets, dependency ordering, TCP/UDP range conflicts, per-service storage proposals and redacted input-bound plan hashes.
- Refuse remote Docker endpoints, ambiguous environment overrides, occupied fresh-install paths, overlapping paths, Git-contained output and output overwrites.
- Added Windows live read-only evidence and cross-platform mocked regression/launcher checks; application runtime support remains unverified.
- No containers, live configuration, services, firewall rules or global Docker limits were changed.

## 0.2.0 — 2026-10-03

- Added a metadata-only Windows collector with outside-checkout output guards and mocked privacy tests.
- Reconciled all 54 observed containers: 52 assigned to blueprint modules and two private controller-generated applications explicitly excluded.
- Added 21 application runbooks, configuration/secret/storage mapping, evidence register and custom-build provenance ledger.
- Documented Coolify source drift, backup consistency/coverage gaps, Windows-bound recovery secrets and native startup limitations.
- Extended validation to enforce module coverage, logical source locators and runbook presence.
- No production service changes, backup jobs, restores or heavy application tasks were performed.

## 0.1.0 — 2026-10-03

- Added sanitized service-family inventory and 21-module catalog.
- Defined modular deployment architecture, platform adapters, storage policy, and recovery boundaries.
- Added an incremental roadmap with acceptance gates and copy-paste phase prompts.
- Added example design plans, a repository validator, regression tests, and static CI.
- No deployment or recovery automation is implemented in this foundation release.
