# HomeLab-SelfHosting

A reproducible, local-first homelab: deploy what you need, choose where your data lives, and know how to recover it.

This project grows out of a working Windows Docker Desktop homelab with personal cloud, documents, photos, development, communication, and monitoring services. Its goal is to turn that operational experience into documented, testable deployment modules for Windows, Linux, and macOS.

**Release 0.2.0 adds read-only discovery and configuration mapping, not a working installer.** No application deployment, adoption, backup, or restore command is implemented yet. Repository validation and a Windows metadata collector are implemented. Existing deployments are not modified by these tools.

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
python tools/validate_repository.py
python -m unittest discover -s tests -v
```

These commands validate the repository's catalog, example plans, and documentation. They do not access Docker or change your server. Example plans are design fixtures, **not deployable configurations**.

For the opt-in Windows/PowerShell 7 read-only metadata collector, see [evidence and privacy instructions](docs/discovery/evidence.md). Its report belongs outside Git. Windows collector regression tests use mocks and can be run with `./tests/Test-ReferenceCollector.ps1`.

The future interface is intentionally documented separately in [architecture](docs/architecture.md#planned-user-workflow). Do not run a remotely downloaded script with administrator privileges on trust alone.

## Service families

- Visibility: Glance, Uptime Kuma, Beszel, native Glances.
- Personal data: Nextcloud, AFFiNE, Paperless-ngx, Firefly III, Vaultwarden, Karakeep.
- Media: Immich, native Jellyfin, and an optional media-management stack.
- Development and communication: code-server, Coolify, Matrix/Element.
- Utilities and infrastructure: Stirling-PDF, Portainer, Cloudflare Tunnel, Tailscale.

The machine-readable [catalog](catalog/services.json) describes 21 modules. Inclusion means planned coverage, not tested deployment support. Native integrations and Coolify have additional platform constraints.

## Safety and scope

- No live credentials, user documents, photographs, database dumps, private keys, real tunnel identifiers, or production configuration files belong in this repository.
- Installing templates is not disaster recovery. Recovery also needs verified data backups and an independently recoverable encrypted secret bundle.
- Existing services are never automatically adopted, restarted, upgraded, or removed.
- Public exposure and GPU access are opt-in. Heavy reindexing, OCR, thumbnail, and ML jobs require explicit approval.
- Database migrations may make an image-only rollback unsafe. Recovery must be application-aware.
- Cross-platform support is earned through tests; Docker alone does not make every application portable.

See [SECURITY.md](SECURITY.md), [contribution guidance](CONTRIBUTING.md), and [release notes](docs/releases/v0.2.0.md).

## License

Original project code and documentation use the [MIT License](LICENSE). Application images, upstream code, names, and any future imported patches remain subject to their respective licenses. No third-party application source is bundled in this release.
