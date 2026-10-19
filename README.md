# HomeLab-SelfHosting

A reproducible, local-first homelab: deploy what you need, choose where your data lives, and know how to recover it.

This project grows out of a working Windows Docker Desktop homelab with personal cloud, documents, photos, development, communication, and monitoring services. Its goal is to turn that operational experience into documented, testable deployment modules for Windows, Linux, and macOS.

**Prerelease 0.6.0-alpha.2 adds a bounded encrypted recovery vault to the isolated Paperless-ngx candidate.** It checksum-validates a reviewed restic binary, encrypts only a verified nonempty Paperless backup, checks all repository data, proves decryption plus independent application recovery, and gates retention on a successful restore. The existing personal deployment remains untouched, the general planner remains planning-only, and same-machine encryption is not presented as off-host disaster recovery.

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
python -m unittest discover -s tests -v
```

The planner is offline by default. `doctor` makes read-only local host/Docker queries; it does not start Docker, deploy anything or change settings. The example above can be planned on any platform; select the corresponding Linux or macOS settings file for live host checks. Do not point fresh-install settings at an existing deployment.

Windows also supports `./bootstrap.ps1 catalog`; Linux/macOS supports `sh ./bootstrap.sh catalog`. These launchers find Python 3.12+ without installing anything. The [guide](docs/planning.md) explains wizard output locations, port overrides, resource estimates, exit codes and limitations. Older `*.plan.example.json` files remain architecture fixtures; the CLI accepts `*.settings.example.json` files instead.

For the opt-in Windows/PowerShell 7 read-only metadata collector, see [evidence and privacy instructions](docs/discovery/evidence.md). Its report belongs outside Git. Windows collector regression tests use mocks and can be run with `./tests/Test-ReferenceCollector.ps1`.

General application deployment and recovery remain future capabilities described in [architecture](docs/architecture.md#planned-user-workflow). Separate experimental `glance`, `kuma`, `beszel`, `stirling`, opt-in `portainer`, `paperless` and `paperless-vault` candidates are bounded execution paths; they do not enable the general planner. The Portainer candidate controls only its disposable nested engine and cannot see host workloads. Do not run a remotely downloaded script with administrator privileges on trust alone.

## Service families

- Visibility: Glance, Uptime Kuma, Beszel, native Glances.
- Personal data: Nextcloud, AFFiNE, Paperless-ngx, Firefly III, Vaultwarden, Karakeep.
- Media: Immich, native Jellyfin, and an optional media-management stack.
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

See [SECURITY.md](SECURITY.md), [contribution guidance](CONTRIBUTING.md), and the [0.6.0-alpha.2 release review](docs/releases/v0.6.0-alpha.2.md).

## License

Original project code and documentation use the [MIT License](LICENSE). Application images, upstream code, names, and any future imported patches remain subject to their respective licenses. No third-party application source is bundled in this release.
