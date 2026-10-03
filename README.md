# HomeLab-SelfHosting

A reproducible, local-first homelab: deploy what you need, choose where your data lives, and know how to recover it.

This project grows out of a working Windows Docker Desktop homelab with personal cloud, documents, photos, development, communication, and monitoring services. Its goal is to turn that operational experience into documented, testable deployment modules for Windows, Linux, and macOS.

**Release 0.3.0 adds a settings wizard, read-only doctor and deterministic planner, not a working installer.** Choose services, propose storage and resource budgets, and review conflicts. No application deployment, adoption, backup, or restore command is implemented yet. Existing deployments are not modified by these tools.

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
| [Planning CLI guide](docs/planning.md) | Run the wizard, check your host and review a redacted plan |
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
python -m unittest discover -s tests -v
```

The planner is offline by default. `doctor` makes read-only local host/Docker queries; it does not start Docker, deploy anything or change settings. The example above can be planned on any platform; select the corresponding Linux or macOS settings file for live host checks. Do not point fresh-install settings at an existing deployment.

Windows also supports `./bootstrap.ps1 catalog`; Linux/macOS supports `sh ./bootstrap.sh catalog`. These launchers find Python 3.12+ without installing anything. The [guide](docs/planning.md) explains wizard output locations, port overrides, resource estimates, exit codes and limitations. Older `*.plan.example.json` files remain architecture fixtures; the CLI accepts `*.settings.example.json` files instead.

For the opt-in Windows/PowerShell 7 read-only metadata collector, see [evidence and privacy instructions](docs/discovery/evidence.md). Its report belongs outside Git. Windows collector regression tests use mocks and can be run with `./tests/Test-ReferenceCollector.ps1`.

Deployment and recovery remain future capabilities described in [architecture](docs/architecture.md#planned-user-workflow). Do not run a remotely downloaded script with administrator privileges on trust alone.

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

See [SECURITY.md](SECURITY.md), [contribution guidance](CONTRIBUTING.md), and [release notes](docs/releases/v0.3.0.md).

## License

Original project code and documentation use the [MIT License](LICENSE). Application images, upstream code, names, and any future imported patches remain subject to their respective licenses. No third-party application source is bundled in this release.
