# HomeLab-SelfHosting

A reproducible, local-first homelab: deploy what you need, choose where your data lives, and know how to recover it.

This project grows out of a working Windows Docker Desktop homelab with personal cloud, documents, photos, development, communication, and monitoring services. Its goal is to turn that operational experience into documented, testable deployment modules for Windows, Linux, and macOS.

**Version 0.7.0-alpha.6 proves encrypted Jellyfin application and owner-managed media recovery.** A native-Windows rehearsal stores Jellyfin's built-in archive and a separately managed synthetic media original in a checksum-pinned Restic repository, deletes all source state and the operational key, then recovers through a clean same-version target using only transported encrypted material and an independently held recovery key. Exact direct play passes before backup, after recovery and after restart; production Jellyfin and media remain untouched.

## What this project is building

- An interactive service-selection wizard and an equivalent configuration-file workflow.
- Separate configuration, database, media, and backup storage choices.
- Independent Docker Compose projects managed through one understandable entry point.
- Resource budgets, health checks, controlled updates, and application-aware recovery.
- Optional native-host integrations, GPU acceleration, and documented public access.
- A portable, sanitized blueprint, not a copy of anyone's private server.

One entry point does **not** mean one giant container or one shared database. Each application keeps its own dependencies, lifecycle, and recovery boundary.

## Start here

| Read | Purpose |
| --- | --- |
| [Documentation hub](docs/README.md) | Navigate setup, modules, operations, validation and releases |
| [Planning CLI guide](docs/planning.md) | Run the wizard, check your host and review a redacted plan |
| [Synthetic execution guide](docs/safe-execution.md) | Phase 3 permissions, ownership, secrets, retries and data-preserving retirement |
| [Experimental Glance module](docs/glance-module.md) | Isolated starter lifecycle plus reusable operations layouts and privacy-filtered collectors |
| [Glance operations profile](docs/glance-operations-layout.md) | Seven-page reusable layout, host snapshots and internal read-only metrics sidecar |
| [Experimental Uptime Kuma module](docs/kuma-module.md) | Synthetic lifecycle, selected status page, outage exercise and stopped-state recovery |
| [Kuma desired-state configuration](docs/kuma-configuration.md) | Reusable HTTP checks, status groups, private webhook/SMTP profiles and delivery testing |
| [Beszel module candidate](docs/beszel-module.md) | Isolated upstream hub/agent, limited metrics scope and recovery; validation gates pending |
| [Beszel Windows host adapter](docs/beszel-windows-host.md) | Existing NSSM agent audit, version-local host metrics, rollback-safe upgrade candidate |
| [Stirling-PDF module candidate](docs/stirling-pdf-module.md) | Isolated PDF rotation exercise, bounded resources and stopped-state recovery |
| [Optional Portainer module](docs/portainer-module.md) | Explicit isolated-engine control, loopback HTTPS and stopped-state recovery |
| [Paperless-ngx recovery module](docs/paperless-ngx-module.md) | Isolated document lifecycle, consistent backup set and independent semantic restore |
| [Paperless encrypted vault](docs/paperless-vault.md) | Reviewed restic tool, key custody, encrypted store/check/restore and retention workflow |
| [0.6.0-alpha.2 validation](docs/validation/paperless-vault.md) | Windows encryption, independent recovery, cleanup and production-safety evidence |
| [0.6.0-alpha.3 recovery gate](docs/validation/paperless-off-host-recovery.md) | Off-host transport and fresh-runner recovery contract |
| [AFFiNE recovery module](docs/affine-module.md) | Isolated workspace sync, consistent backup and independent semantic restore |
| [0.6.0-alpha.4 validation](docs/validation/affine.md) | Windows Docker Desktop sync, restart, backup and restore evidence |
| [AFFiNE encrypted vault](docs/affine-vault.md) | Reviewed Restic, separate key custody, portable manifests and retention gates |
| [0.6.0-alpha.5 recovery gate](docs/validation/affine-off-host-recovery.md) | Browser-rendered local proof and independent clean-runner recovery contract |
| [Nextcloud recovery module](docs/nextcloud-module.md) | Isolated WebDAV/cron exercise, consistent backup and independent restore |
| [0.6.0-alpha.6 validation](docs/validation/nextcloud.md) | Windows Docker Desktop recovery and restart evidence |
| [Nextcloud encrypted vault](docs/nextcloud-vault.md) | Reviewed Restic, separate key custody, portable manifest and retention gates |
| [0.6.0-alpha.7 recovery gate](docs/validation/nextcloud-off-host-recovery.md) | Encrypted-only transfer and independent clean-runner application recovery |
| [Firefly III recovery module](docs/firefly-iii-module.md) | Isolated finance fixture, consistent backup and independent restore |
| [0.6.0-alpha.8 validation](docs/validation/firefly-iii.md) | Windows Docker Desktop content, cron, backup, restore and restart evidence |
| [Firefly III encrypted vault](docs/firefly-vault.md) | Reviewed Restic, separate key custody, portable manifest and retention gates |
| [0.6.0-alpha.9 recovery gate](docs/validation/firefly-off-host-recovery.md) | Encrypted-only transfer and independent clean-runner finance recovery |
| [Vaultwarden recovery module](docs/vaultwarden-module.md) | Isolated Web Vault note/attachment lifecycle, consistent SQLite/files backup and independent restore |
| [0.6.0-alpha.10 validation](docs/validation/vaultwarden.md) | Browser-rendered decryption, attachment bytes, restart and fresh-project recovery evidence |
| [Vaultwarden encrypted vault](docs/vaultwarden-vault.md) | Reviewed Restic, separate key custody, portable manifest and retention gates |
| [0.6.0-alpha.11 recovery gate](docs/validation/vaultwarden-off-host-recovery.md) | Encrypted-only transfer and independent clean-runner browser recovery |
| [Karakeep recovery module](docs/karakeep-module.md) | Isolated bookmark/asset lifecycle, logical export, quiesced SQLite/assets backup and search-rebuilt restore |
| [0.6.0-alpha.12 validation](docs/validation/karakeep.md) | Rendered title, full-text search, exact asset bytes, restart and fresh-project recovery evidence |
| [Karakeep encrypted vault](docs/karakeep-vault.md) | Reviewed Restic encryption, independent key custody, portable recovery manifest and restore-gated retention |
| [0.6.0-alpha.13 off-host validation](docs/validation/karakeep-off-host-recovery.md) | Two clean runners, encrypted-only transfer, exact asset/search/browser recovery and restart persistence |
| [Phase 5 integrated validation](docs/validation/phase5-integrated.md) | Six reusable encrypted-recovery workflows, shared assurance contract and stable-release blockers |
| [0.6.0-rc.1 release review](docs/releases/v0.6.0-rc.1.md) | Exact integrated scope, release gates and production-adoption boundaries |
| [Owner-operated backup design](docs/owner-operated-backups.md) | Storage topology, capacity, scheduling, key custody and activation gates |
| [0.6.0-rc.2 design validation](docs/validation/phase5-owner-backup-design.md) | Offline policy evidence and read-only Windows task reconciliation |
| [0.6.0-rc.2 release review](docs/releases/v0.6.0-rc.2.md) | Exact non-activating scope and remaining production gates |
| [Phase 5 encrypted recovery kit](docs/phase5-recovery-kit.md) | Runtime kit layout, semantic content checks, encryption and retention contract |
| [Phase 5 closure validation](docs/validation/phase5-closure.md) | Final six-module consistency and clean-runner restore gate |
| [0.6.0 release review](docs/releases/v0.6.0.md) | Completed Phase 5 scope and production-adoption boundary |
| [Phase 6 media foundation](docs/phase6-media-foundation.md) | Originals policy, heavy-job controls, resource ceilings and acceleration gate |
| [0.7.0-alpha.1 validation](docs/validation/phase6-media-foundation.md) | Read-only Docker/NVIDIA evidence and CPU fallback decision |
| [0.7.0-alpha.1 release review](docs/releases/v0.7.0-alpha.1.md) | Exact first Phase 6 scope and remaining Immich/Jellyfin gates |
| [Immich recovery module](docs/immich-module.md) | Protected originals, consistent PostgreSQL backup and separately bounded ML |
| [0.7.0-alpha.2 validation](docs/validation/immich.md) | Exact upload/download, ML isolation and fresh-project recovery evidence |
| [0.7.0-alpha.2 release review](docs/releases/v0.7.0-alpha.2.md) | Bounded Immich candidate scope and remaining production gates |
| [Immich encrypted vault](docs/immich-vault.md) | Restic key custody, full-data checks, portable manifests and restore-gated retention |
| [0.7.0-alpha.3 off-host validation](docs/validation/immich-off-host-recovery.md) | Encrypted-only transfer and independent clean-runner exact-original recovery |
| [0.7.0-alpha.3 release review](docs/releases/v0.7.0-alpha.3.md) | Encrypted Immich recovery scope and remaining owner-adoption gates |
| [Jellyfin deployment-selection module](docs/jellyfin-module.md) | Native/container platform rules, read-only adoption audit and Linux Compose renderer |
| [0.7.0-alpha.4 validation](docs/validation/jellyfin.md) | Live native Windows detection, immutable image review and CPU fallback evidence |
| [0.7.0-alpha.4 release review](docs/releases/v0.7.0-alpha.4.md) | Exact Jellyfin selection scope and remaining playback/recovery gates |
| [Jellyfin recovery trial](docs/jellyfin-recovery.md) | Disposable same-version built-in backup, independent restore and exact direct play |
| [0.7.0-alpha.5 validation](docs/validation/jellyfin-recovery.md) | Live isolated recovery, restart persistence and production-isolation evidence |
| [0.7.0-alpha.5 release review](docs/releases/v0.7.0-alpha.5.md) | Exact recovery scope and remaining production/off-host gates |
| [Jellyfin encrypted recovery](docs/jellyfin-vault.md) | Separate application/media recovery set, encryption, key custody and validators |
| [0.7.0-alpha.6 validation](docs/validation/jellyfin-off-host-recovery.md) | Source-loss, full-data-check, exact media and application recovery evidence |
| [0.7.0-alpha.6 release review](docs/releases/v0.7.0-alpha.6.md) | Verified scope and remaining owner-adoption gates |
| [Phase 4 integrated validation](docs/validation/phase4-integrated.md) | Combined release gates, live Windows evidence and unresolved manual checks |
| [0.5.0-rc.1 release review](docs/releases/v0.5.0-rc.1.md) | Exact candidate scope, support boundaries and stable-release decision |
| [Architecture](docs/architecture.md) | Components, installation modes, storage, security boundaries |
| [Current inventory](docs/inventory.md) | What was observed and what still needs verification |
| [Phase 1 findings](docs/discovery/findings.md) | Recovery risks and reproducibility gaps found in the real configuration |
| [Individual runbooks](docs/discovery/runbooks.md) | Sources, owners, storage, secrets and recovery requirements for all 21 modules |
| [Configuration mapping](docs/discovery/configuration-mapping.md) | Reusable settings versus private and platform-specific state |
| [Phases and release gates](docs/roadmap.md) | Work breakdown from foundation to stable release |
| [Copy-paste phase prompts](docs/phase-prompts.md) | Instructions to implement one reviewed milestone at a time |
| [Service runbook requirements](docs/services.md) | App-specific data, risks, and acceptance checks |
| [Recovery design](docs/recovery.md) | Backups, keys, restore rehearsals, hardware failure |
| [Platform support](docs/platform-support.md) | Honest Windows/Linux/macOS and architecture status |
| [Public access](docs/public-access.md) | Local-first networking, DNS, tunnels, and authentication |

## What runs today

With Python 3.12 or newer, from the repository root:

```sh
python -m homelab catalog
python -m homelab plan --config examples/windows.settings.example.json
python -m homelab doctor
python tools/validate_repository.py
python tools/validate_phase4.py
python tools/validate_phase5.py
python tools/validate_phase5_closure.py
python tools/validate_phase6.py
python homelab_cli.py owner-backup validate --policy modules/phase5/owner-backup-policy.example.json
python -m homelab media audit
python -m homelab jellyfin audit
python -m homelab jellyfin validate-recovery --evidence /private/jellyfin-recovery.json
python -m homelab jellyfin-vault validate-proof --proof /private/jellyfin-off-host-proof.json
python -m unittest discover -s tests -v
```

The planner is offline by default. `doctor` makes read-only local host/Docker queries; it does not start Docker, deploy anything or change settings. The example above can be planned on any platform; select the corresponding Linux or macOS settings file for live host checks. Do not point fresh-install settings at an existing deployment.

Windows also supports `./bootstrap.ps1 catalog`; Linux/macOS supports `sh ./bootstrap.sh catalog`. These launchers find Python 3.12+ without installing anything. The [guide](docs/planning.md) explains wizard output locations, port overrides, resource estimates, exit codes and limitations. Older `*.plan.example.json` files remain architecture fixtures; the CLI accepts `*.settings.example.json` files instead.

For the opt-in Windows/PowerShell 7 read-only metadata collector, see [evidence and privacy instructions](docs/discovery/evidence.md). Its report belongs outside Git. Windows collector regression tests use mocks and can be run with `./tests/Test-ReferenceCollector.ps1`.

General application deployment and recovery remain future capabilities described in [architecture](docs/architecture.md#planned-user-workflow). Separate experimental `glance`, `kuma`, `beszel`, `stirling`, opt-in `portainer`, `paperless`, `paperless-vault`, `affine`, `affine-vault`, `nextcloud`, `nextcloud-vault`, `firefly`, `firefly-vault`, `vaultwarden`, `vaultwarden-vault`, `karakeep`, `karakeep-vault`, `immich` and `immich-vault` candidates are bounded execution paths; they do not enable the general planner. `owner-backup` and `media` only audit, validate or save disabled private designs. `jellyfin` validates application-recovery evidence, while `jellyfin-vault` validates the separate encrypted application/media contracts; their rehearsal tools require explicit confirmation and disposable paths. The Portainer candidate controls only its disposable nested engine and cannot see host workloads. Do not run a remotely downloaded script with administrator privileges on trust alone.

## Service families

- Visibility: Glance, Uptime Kuma, Beszel, native Glances.
- Personal data: Nextcloud, AFFiNE, Paperless-ngx, Firefly III, Vaultwarden, Karakeep.
- Media: Immich, explicitly selected native/Linux-container Jellyfin, and an optional media-management stack.
- Development and communication: code-server, Coolify, Matrix/Element.
- Utilities and infrastructure: Stirling-PDF, Portainer, Cloudflare Tunnel, Tailscale.

The machine-readable [catalog](catalog/services.json) describes 21 modules whose general-coordinator integration remains planned. Phase 4's five separately gated adapters do not enable the general planner or certify production migration. Native integrations and Coolify have additional platform constraints.

## Safety and scope

- No live credentials, user documents, photographs, database dumps, private keys, real tunnel identifiers, or production configuration files belong in this repository.
- Installing templates is not disaster recovery. Recovery also needs verified data backups and an independently recoverable encrypted secret bundle.
- Existing services are never automatically adopted, restarted, upgraded, or removed.
- Public exposure and GPU access are opt-in. Heavy reindexing, OCR, thumbnail, and ML jobs require explicit approval.
- Database migrations may make an image-only rollback unsafe. Recovery must be application-aware.
- Cross-platform support is earned through tests; Docker alone does not make every application portable.

See [SECURITY.md](SECURITY.md), [contribution guidance](CONTRIBUTING.md), and the [0.7.0-alpha.6 release review](docs/releases/v0.7.0-alpha.6.md).

## License

Original project code and documentation use the [MIT License](LICENSE). Application images, upstream code, names, and any future imported patches remain subject to their respective licenses. No third-party application source is bundled in this release.
