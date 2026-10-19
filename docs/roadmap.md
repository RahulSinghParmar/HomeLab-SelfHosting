# Roadmap and release gates

The version numbers below are proposed milestone targets, not promises that unfinished work is released. Each phase ends with reviewed evidence, a coherent commit, a pushed tag/release, and a handoff before the next phase. If a phase is too large, use prerelease milestones and stop at a safe application boundary.

## Phase summary

| Phase | Target | Deliverable | Required exit evidence |
| --- | --- | --- | --- |
| 0 | 0.1.0 | Public foundation, sanitized inventory, architecture, prompts | Catalog/docs validate; tests pass; publication review |
| 1 | 0.2.0 | Detailed configuration discovery and extraction mapping | Every service has an evidence source, data map, secret map and owner; no live changes |
| 2 | 0.3.0 | Cross-platform coordinator, doctor, selection wizard and plan | Dependency/port/resource checks; deterministic dry run; no deployment yet |
| 3 | 0.4.0 | Storage, secrets, owned-state journal and safe execution | Synthetic module deploy/retry/failure tests; no adoption or data deletion |
| 4 | 0.5.0 | Visibility and utility modules | Glance, Kuma, Beszel, Stirling-PDF and opt-in Portainer tested in isolation |
| 5 | 0.6.0 | Personal-data apps and application-aware recovery | AFFiNE, Paperless, Nextcloud, Firefly, Vaultwarden, Karakeep tested one by one |
| 6 | 0.7.0 | Media stack and resource policies | Immich, optional media management, Jellyfin adapter; originals survive restore |
| 7 | 0.8.0 | Development, communications and host integrations | code-server, Matrix, Coolify adapter and native lifecycle tests |
| 8 | 0.9.0 | Optional public/private remote access | Tunnel/VPN/proxy setup with external browser/client/WebSocket tests |
| 9 | 0.10.0 | Portability and clean-machine disaster recovery | Declared platforms tested; off-host restore with nonempty data; support matrix published |
| 10 | 1.0.0 | Production release and final handoff | All selected supported modules meet security, lifecycle, recovery and documentation gates |

## Phase 0 — Repository foundation

Deliver the working catalog validator, tests, architecture, design plans, service runbook requirements, public-access boundary, and this phased execution plan. Do not label the future installer production-ready. Do not import production secrets or data.

## Phase 1 — Discover and document the real deployment

Delivered in the 0.2.0 discovery milestone: [evidence and boundaries](discovery/evidence.md), [runbooks](discovery/runbooks.md), and [findings requiring later work](discovery/findings.md). Completion means the declared discovery scope is mapped, not that the applications are already reproducibly deployable.

- Inventory effective Compose sources and overrides, versions/digests, custom image sources, native services, scheduled tasks, storage, backup scripts and external integrations.
- Read sensitive settings locally only as necessary; publish secret **names/purposes**, never values. Keep any detailed inventory outside the repository.
- Map existing customization to upstream default, safe reusable template, private installation value, or unsupported/manual step.
- Verify original licensing and patch provenance before copying any third-party code.
- Produce one human runbook per module with install/configuration/operations/backup/recovery/update sections and evidence links.
- Identify missing backups and nonportable paths/builds. Do not fix the production environment during discovery.

Exit: coverage ledger explains every discovered component, including intentionally excluded experimental deployments. No unsupported values are silently guessed.

## Phase 2 — Coordinator and planning

Delivered in the 0.3.0 planning milestone: [CLI and safety boundaries](planning.md). This implements selection and review, not application execution. No module is deployment-certified by this milestone.

- Implement shared Python CLI, thin platform bootstrap wrappers, interactive and file-based configuration, and schema validation.
- Doctor checks OS/architecture/runtime/context, available resources, free disk, path permissions, port conflicts, time synchronization and prerequisite readiness.
- Resolve selected modules and dependencies; calculate a resource budget and emit a redacted deterministic execution plan.
- Support Windows paths with spaces, Linux/macOS paths, missing drives, unavailable Docker, remote Docker contexts, and invalid selections.

Exit: unit tests on all three operating systems and a reviewed plan; no application deployment command permitted yet.

## Phase 3 — Safe installation primitives

Delivered in the 0.4.0 synthetic-files milestone: [safe execution guide](safe-execution.md). The executor has no Docker/network operations and accepts no production module. Recovery at completed operation boundaries is tested; incomplete initialization or atomic-publication residue is preserved and requires manual review.

- Implement private storage setup, permissions, credentials, protected manifests, operation locking and ownership tracking.
- Execute only a synthetic disposable module first. Test interruption, retry, failed dependencies, occupied resources and cleanup.
- Add reviewed-plan confirmation and per-operation scoped elevation; no global always-admin requirement.
- Preserve data on stop/removal. Destructive operations remain separate and explicit.

Exit: repeated application is idempotent; failure recovery does not rotate keys, delete data, or touch foreign resources.

## Phase 4 — Visibility and utility modules

First bounded milestone: **0.5.0-alpha.1**, an experimental isolated Glance starter with Windows live lifecycle/rendering and starter-configuration recovery evidence. See [module guide](glance-module.md) and [release scope](releases/v0.5.0-alpha.1.md).

Additional Glance candidate work: the [reusable operations profile and collectors](glance-operations-layout.md) provide seven sanitized pages, strict allowlisted host snapshots and an internal read-only metrics sidecar. The generated profile passed pinned Glance validation and a disposable Windows Docker rendered-fragment trial. Production migration, scheduler installation, cross-platform runtime evidence and rollback rehearsal remain pending, so this work is not a new release by itself.

Second bounded milestone: **0.5.0-alpha.2**, [synthetic Uptime Kuma](kuma-module.md) with real up/down/up transitions, selected status-page rendering, idempotent registration, restart persistence and independent stopped-state recovery. Full Glance customization, production-monitor import/notifications, Beszel/host adapter, Stirling-PDF and opt-in Portainer remain pending. Phase 4 is not complete; 0.5.0 is not released by these milestones. The next bounded module is Beszel, subject to a separate go-ahead.

Unreleased Kuma candidate work now adds a [closed-schema desired-state adapter](kuma-configuration.md) for bounded HTTP monitors, grouped status-page membership, private webhook/SMTP providers, explicit test delivery, drift inspection and notification-aware v2 backups. Its pinned Windows Docker Desktop [live trial and independent recovery](validation/kuma-configuration.md) passed without touching the observed household deployment. SMTP inbox delivery, cross-platform runtime evidence and release packaging remain pending.

In progress: [upstream Beszel hub and restricted agent](beszel-module.md), with [explicit validation gates](validation/beszel-trial.md). This candidate does not include the custom native Windows host adapter or authentication-origin email patch; those remain separate follow-up work, not implicitly completed by upstream deployment.

In progress separately: the [Windows host adapter](beszel-windows-host.md) packages a reviewed 0.18.7 source patch and a drift-checked, rollback-safe existing-service binary upgrade. The live reference agent was upgraded successfully, returned to automatic/running and produced fresh GPU and restricted Windows-service records in the hub; its rollback copy remains retained. It does not install a fresh service or include the authentication-origin patch. Authenticated rendered-UI, controlled service-state and Windows reboot acceptance gates remain pending.

Candidate complete locally: the [isolated Stirling-PDF module](stirling-pdf-module.md) pins 2.14.2 by digest, enforces loopback/read-only/bounded execution, verifies a real in-memory 90-degree PDF rotation and restores a stopped five-volume snapshot into an independent healthy project. The [Windows Docker Desktop record](validation/stirling-pdf.md) documents measured near-1-GiB memory use and the intentionally narrow certified scope. Authentication/public exposure, advanced conversion workloads, encrypted off-host recovery, cross-platform evidence and release packaging remain pending.

Candidate complete locally: the [optional Portainer module](portainer-module.md) requires an explicit `isolated-engine-only` grant, gives Portainer control of only an ephemeral internal Docker-in-Docker daemon, and never mounts the host socket. A real create/inspect/delete API exercise and stopped backup into an independent authenticated restore both passed on Windows Docker Desktop; see the [validation record](validation/portainer.md). Host-engine control, public access, real workloads, encrypted off-host recovery, cross-platform evidence and release packaging remain intentionally uncertified.

Integrated release review: **0.5.0-rc.1** packages all five bounded adapters and adds one offline contract validator covering CLI surfaces, documentation/evidence presence and exact image digests. The [combined validation record](validation/phase4-integrated.md) and [release review](releases/v0.5.0-rc.1.md) intentionally retain a **no-go for stable 0.5.0** until the authenticated Beszel chart is inspected, the Windows host adapter passes its controlled state/reboot checks, and the stable platform-runtime policy is settled. Linux/macOS application-runtime support is not inferred from Python CI.

Substages: Glance/Kuma -> Beszel/host adapter -> Stirling-PDF -> optional Portainer. Use independent test names and ports. Synthetic endpoints and credentials only.

Migrate approved dashboard layouts and metric collectors without publishing personal statistics. Register checks idempotently. Keep administrative Docker control opt-in. Measure idle and active resources rather than guessing minimal limits.

Exit: rendered dashboard, real monitoring state transitions, restart persistence, permissions checks, and settings restore for each module.

## Phase 5 — Personal data and backups

Substages: Paperless -> AFFiNE -> Nextcloud -> Firefly -> Vaultwarden -> Karakeep. Stop after each tested application's milestone if further work would broaden the current approved scope.

First bounded milestone: **0.6.0-alpha.1**, an [isolated Paperless-ngx recovery candidate](paperless-ngx-module.md) with a nonempty synthetic PDF, quiesced exporter/database/filesystem set, independent importer restore and Windows Docker Desktop evidence. The snapshot remains plaintext-sensitive; encrypted restic storage, production migration and the remaining five applications are not delivered by this prerelease.

Second bounded milestone: **0.6.0-alpha.2**, a [Paperless encrypted recovery vault](paperless-vault.md) that validates a reviewed restic 0.19.1 Windows amd64 binary, binds one verified nonempty application backup, checks all encrypted repository data, decrypts and revalidates it, then proves independent Paperless importer recovery and restart persistence. The live repository and key copies were local and disposable; off-host media, offline-key recovery, scheduling, production migration and the remaining five applications are still not delivered.

Third bounded milestone: **0.6.0-alpha.3**, a portable [Paperless off-host recovery gate](validation/paperless-off-host-recovery.md). It adds reviewed Linux amd64 Restic support and separates an encrypted synthetic repository artifact from its Actions recovery secret, then decrypts and application-restores it on a fresh hosted runner without source-machine state. It proves the mechanism only: production data, durable off-host storage, real offline-key custody, scheduling and the remaining five applications are still not delivered.

Implement application-consistent backup/restore before considering a module complete. Build a portable encrypted recovery kit and retention policy. Test with nonempty synthetic data. Choose a maintained encryption/backup tool after validating its current platform support; do not invent cryptography.

Exit: upload/open/edit/restart/backup/restore checks and a verified recovery-secret workflow for every implemented module. No real financial records or password vaults in test fixtures.

## Phase 6 — Media and acceleration

Implement compatible Immich releases, separately limited ML, and correct storage mappings. Add media-management modules only as selected. Rebuildable thumbnails are distinct from originals; no automatic mass regeneration, deletion, or transcoding.

Jellyfin native versus container deployment must be an explicit platform choice. GPU enablement requires a capability probe and real synthetic workload test; unsupported systems use CPU mode. Media integrations must respect lawful ownership and user-provided credentials.

Exit: verified original-file integrity, content browsing and restoration, measured concurrency, and explicit GPU support results.

## Phase 7 — Development, chat and native lifecycle

Reproduce the code-server build, extension/settings persistence and architecture-correct toolchain downloads. Preserve private workspaces and authentication. Implement Matrix identity/key handling, Element and TURN tests; bridges remain optional.

Handle Coolify as its own controller. Document upstream Linux support and prove any Windows adapter separately. Do not absorb dynamically managed projects into generic Compose ownership.

Finish native startup/scheduling adapters, Glances and optional VPN integrations. Task definitions and startup recovery must survive reboot tests on actual platforms.

Exit: editing/compilation/session persistence, chat and call behavior where enabled, controlled deployment and reboot recovery evidence.

## Phase 8 — Remote access

Document dashboard-assisted and optional automated setup for user-owned DNS, tunnels, VPN, SMTP and OAuth. External credentials and changes require explicit user configuration. Test real clients and WebSockets, not just home-page HTTP status.

Exit: local operation remains independent of the public-access provider; no internal database/admin endpoint is accidentally exposed.

## Phase 9 — Clean-machine portability and recovery

Test Windows/Linux/macOS and each declared CPU architecture on appropriate machines. Mark unavailable test environments unverified; do not simulate a passing runtime result with a mock.

Rebuild on a clean machine from a tagged release, an encrypted off-host backup and the independent recovery key. Include power loss/interrupted upgrade, wrong secret, missing drive, unavailable registry, and insufficient-memory scenarios.

Exit: declared recovery-point and recovery-time measurements, content checksums, compatibility matrix, and documented limitations. Unsupported optional modules must be blocked clearly without breaking supported selections.

## Phase 10 — Production release

Finalize install and operations guides, troubleshooting, annotated screenshots with synthetic data, upgrade/rollback policy, release checksums, dependency review and secret scans. Test the instructions as a new user.

Only label a platform/module combination supported when its evidence is complete. A stable core may coexist with clearly labeled experimental modules. Production readiness means defined support, tested recovery and observable failure handling—not a guarantee of zero bugs.

## Rules shared by every phase

- Keep the existing homelab untouched unless a separate request explicitly authorizes a specific change.
- Show what changed, what was tested, and what remains unverified.
- Scan the complete staged public artifact set; `.gitignore` alone is not a security control.
- Do not release a failed phase as complete. Use a clearly marked draft/prerelease if needed.
- Publish only approved repository content, never local inventory exports or recovery secrets.
