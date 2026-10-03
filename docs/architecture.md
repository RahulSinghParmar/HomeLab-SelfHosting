# Architecture

## Two deliverables, kept separate

**Public blueprint:** reusable automation, reviewed templates, documentation, tests, and release metadata.

**Private installation:** selected services, actual paths, secrets, application data, encrypted backups, and machine-specific state. This stays outside the repository and is not uploaded by support or inventory commands.

```text
User: interactive wizard or reviewed plan file
                    |
         shared deployment coordinator
          /         |              \
 service catalog  platform adapter  operation journal
       |          /      |      \          |
 app modules   Windows Linux   macOS   health / recovery
       |
 separate Compose projects + explicit native integrations
       |
 private config / database storage / media / backup destinations
```

Use a Python 3.12+ coordinator with a small dependency footprint, PowerShell and POSIX-shell entry points, JSON plans, and Compose v2-compatible application modules. Exact tested tool versions will be recorded per release. Bootstrap scripts will check prerequisites and explain installation; they will not silently install system software or force reboots.

## Module contract

Each module will provide:

- A stable ID, upstream source, licensing notes, supported platforms and CPU architectures.
- Dependency declarations and owned resources; no global database shared across unrelated applications by default.
- Reviewed Compose/build templates and pinned image versions/digests per supported architecture.
- Configuration schema, required secret references, storage mappings, resource budget, and port requirements.
- Configure, validate, start, health, stop, backup, restore, update, and removal behavior.
- A human-readable runbook and synthetic content tests.

Internal dependencies such as PostgreSQL, Redis, or a migration job belong to their application's lifecycle. Cross-module integrations such as dashboard links are optional and must not force installation of unrelated apps.

Coolify-managed proxy, sentinel, and generated applications must remain under their actual lifecycle owner. A single top-level command can coordinate them without relabeling or fighting the upstream control plane.

## Planned user workflow

In 0.3.0, `python -m homelab configure`, `validate`, `doctor` and `plan` are implemented. See the [planning guide](planning.md). They save explicit settings/reports and query the host read-only; they do not implement the deployment coordinator, ownership journal or recovery system shown above. The complete workflow remains a design target:

```text
bootstrap.ps1 or bootstrap.sh
  -> doctor: OS, architecture, runtime, resources, storage, port conflicts
  -> configure: select apps, paths, budgets, access mode, recovery strategy
  -> plan: show exact proposed operations and required privileges
  -> apply: confirm reviewed plan, deploy dependencies, validate each app
  -> status: display health, URLs, storage and backup status
```

Future commands include `apply`, `status`, `backup`, `restore`, and `update`. The implemented noninteractive settings path uses the same validation as the wizard. Only fresh-install intent is accepted; a Phase 2 plan has no executable operations.

### Required operating modes

| Mode | Meaning | Safety boundary |
| --- | --- | --- |
| Fresh install | New empty services and new credentials | Refuse occupied paths/projects/ports |
| Restore | Recover existing identity and content | Match backup manifest, versions, keys, and ownership |
| Replica | Independent copy for testing or another owner | New external identity; outbound jobs and notifications disabled |
| Adopt | Bring an existing deployment under management | Explicit approval after evidence-backed diff and backup |

Adoption is a separate later capability. The first installer must not identify a matching container name and assume it owns it.

## Deterministic and resumable execution

- Resolve selection and dependencies before changes; validate the entire plan first.
- Detect local versus remote Docker contexts and refuse ambiguous host-path mapping.
- Record plan hash, module versions, image digests, created resources, and completed steps in a private journal.
- Use an installation lock; prevent concurrent apply, backup, and upgrade jobs for the same app.
- Reuse generated credentials on retry; never rotate credentials implicitly.
- Re-running an unchanged plan should make no unnecessary changes.
- Resume only after checking real state; a journal entry is not proof of successful deployment.
- On failure, stop dependent operations, preserve diagnostics without secrets, and offer a scoped recovery action.
- Removal preserves data by default. Data deletion must name exact resources and require separate confirmation.

## Storage choices

| Category | Default design | User choice |
| --- | --- | --- |
| Templates and generated config | Private installation directory | Separate from this Git checkout |
| Database data | Application-specific named volumes on Linux-backed Docker storage | Expert bind mounts only where tested and upstream-compatible |
| Media and documents | Dedicated mapped data paths | SSD/HDD and per-app overrides |
| Backups | Separate destination, then encrypted off-host copy | Local disk, removable drive, or configured remote repository |
| Secrets | Protected local files and separate encrypted recovery bundle | Explicit secret provider later |

A named volume does not independently choose a Windows drive. Its physical location follows Docker Desktop's Linux disk storage. Changing that disk location is a separate Docker operation, not an installer promise. On Linux, path permissions and user/group IDs must be validated. On Desktop, check file sharing, VM storage, and host filesystem semantics.

Docker recommends Linux-backed storage for performant WSL workloads; blindly putting database files on arbitrary Windows bind mounts is not an equivalent choice. [Docker WSL best practices](https://docs.docker.com/desktop/features/wsl/best-practices/).

## Resource and network policy

Global Docker/VM memory limits and per-container limits are different controls. Offer measured presets and a combined budget with host headroom; do not assume every computer matches the reference machine. ML, OCR, browser workers, and large compilation jobs require explicit concurrency choices. GPU support is opt-in and must pass hardware, driver, runtime, and application checks.

Publish local application endpoints on loopback by default. LAN access is a distinct explicit choice with firewall guidance. Backend databases and caches remain internal. Do not attach every application to one flat network. Tunnel access uses a narrowly scoped network or documented host connection.

Compose dependency ordering alone does not establish readiness; modules need meaningful health checks and application-level tests. [Compose service specification](https://docs.docker.com/reference/compose-file/services/).

## Secrets and configuration

Generate fresh cryptographic secrets on new installations. Store only references in plans; never values in command lines, logs, CI, or public examples. Prefer mounted secret files where the application supports them. Compose secret mounts are not an encrypted backup vault. [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/).

Export nonsecret settings separately from a portable encrypted secret bundle. Windows-account-bound protection alone cannot be the disaster-recovery strategy for a failed Windows machine.

## Repository layout

```text
catalog/             sanitized module inventory
examples/            design plans, never real credentials
homelab/             implemented Python settings, doctor and planner
homelab_cli.py       entry point usable from another working directory
bootstrap.ps1/.sh    prerequisite-only platform launchers
docs/                architecture, runbooks, phases, release evidence
tools/               implemented repository validation
tests/               implemented regression tests
.github/workflows/   static validation, not deployment
```

Future phases will add application modules, execution adapters and disposable integration fixtures only when implemented. Empty folders and placeholder installers are not capabilities.
