# Platform and architecture support

## Current status

The five bounded Phase 4 adapters have module-specific Windows Docker Desktop Linux-amd64 evidence in 0.5.0-rc.1. Paperless-ngx adds bounded Phase 5 application recovery in 0.6.0-alpha.1, encrypted Windows recovery in 0.6.0-alpha.2, and a separately gated Linux amd64 clean-runner rehearsal in 0.6.0-alpha.3. Their exact limits differ and are summarized below; this does not deployment-certify the complete application catalog. The existing homelab is design evidence, not proof that the installer can recreate it. Standard CI remains static/regression validation; the separately dispatched Paperless recovery workflow deploys synthetic containers only.

| Capability | Windows | Linux | macOS |
| --- | --- | --- | --- |
| Repository validation | Local execution plus CI | CI | CI |
| Settings wizard / offline planner | Implemented; local and CI tests | Implemented; CI tests | Implemented; CI tests |
| Synthetic file executor | Actual Windows ACL/lock tests | Actual POSIX mode/lock tests in CI | Actual POSIX mode/lock tests in CI |
| Read-only doctor | Live local Docker Desktop check plus mocked tests | Probe implementation; mocked tests only | Probe implementation; mocked tests only |
| Docker application installation | Five isolated Phase 4 candidates plus Paperless-ngx have bounded live evidence; see module records | Code and mocked tests only; runtime unverified | Code and mocked tests only; runtime unverified |
| Native metrics / startup / scheduling | PowerShell, services, Task Scheduler adapter planned | Native tools and systemd adapter planned | Native tools and launchd adapter planned |
| GPU acceleration | Conditional, driver/runtime/app dependent | Conditional, driver/runtime/app dependent | Not assumed; CPU fallback |
| Coolify | Existing custom integration; not a portable supported baseline | Upstream-supported installation target | Explicit Linux VM/remote Linux host path |
| ARM64 application images | Unverified | Unverified | Unverified, especially Apple Silicon |

Coolify officially supports Linux servers; a Linux VM is the documented route on other host operating systems. The project's existing Windows integration must be labeled experimental until independently reproduced and tested. [Coolify installation documentation](https://coolify.io/docs/get-started/installation).

## Required test matrix

For each released module record OS/version, CPU architecture, Docker/runtime version, image digest, filesystem/storage type, fresh install result, restart result, restore result, and application-level content checks.

Core unit tests target Windows/Linux/macOS with Python 3.12 and 3.14. Runtime tests require actual supported Docker environments; CI host names alone are insufficient. The Phase 2 Windows reference check used Python 3.14.6, Compose 5.5.1 and a Linux-container Docker Desktop engine. Linux/macOS live Docker checks, ARM64 runtime support, filesystem suitability and actual clock offset remain unverified.

Preflight must check image architecture before pull or build. The reference code-server image contains a hard-coded Linux x64 Node download; this must be replaced or the module must explicitly refuse unsupported architectures. Emulation is not an automatic production fallback.

## Honest support labels

- **Planned:** documented design only.
- **Experimental:** implemented but incomplete runtime/recovery evidence.
- **Validated:** passed the declared platform, data, lifecycle, and recovery tests for the release.
- **Unsupported:** known incompatible or outside the maintained matrix.

Every release carries its matrix. Never imply "all platforms supported" because a wrapper script exists.

### Phase 4 candidate matrix

| Adapter | Windows Docker Desktop evidence | Explicitly not certified |
| --- | --- | --- |
| Glance | Seven rendered fragments, configuration validation, loopback trial and privacy-filtered collector | Production migration, scheduler, visual screenshot and cross-platform runtime |
| Uptime Kuma | Desired-state idempotence, HTTP/webhook delivery, status page, stopped backup and independent restore | Real SMTP inbox delivery, production import and cross-platform runtime |
| Beszel | Hub/agent metrics, down/up transition, stopped backup and exact record restore; Windows adapter emits fresh GPU/service records | Authenticated chart inspection, controlled Windows service-state/reboot test and cross-platform runtime |
| Stirling-PDF | Real synthetic rotation, bounded runtime, stopped five-volume backup and independent restore | Authentication/public access, advanced conversion workloads and cross-platform runtime |
| Portainer | Isolated nested-engine create/inspect/delete, host invisibility and authenticated independent restore | Host-engine control, public access, real workloads and cross-platform runtime |
| Paperless-ngx | Nonempty upload/search/edit, consistent exporter/dump/files set, reviewed Windows/Linux amd64 Restic encryption/check/decryption, immutable off-host synthetic artifact, clean-runner semantic restore and restart | Production migration, durable production repository, real offline-key custody, scheduling/prune trial, API tokens, public/mail/OCR/load, ARM64 and macOS runtime |

Phase 3's local filesystem adapter is not a general-purpose native-service or Docker adapter. Use local storage with hard links, atomic replacement and supported permission semantics; network shares, unusual filesystems, concurrent privileged tampering and power-loss durability are not certified. Windows tests do not require SACL/audit-policy changes or blanket administrator rights. If scoped DACL/owner checks fail, execution stops rather than elevating or repairing existing permissions.
