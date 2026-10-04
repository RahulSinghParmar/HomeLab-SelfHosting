# Platform and architecture support

## Current status

The isolated Glance starter and synthetic Kuma module have live Windows Docker Desktop Linux-amd64 evidence in 0.5.0-alpha.1 and 0.5.0-alpha.2 respectively. The complete application catalog is not deployment-certified. The existing homelab is design evidence, not proof that the installer can recreate it. CI checks repository structure, mocked/Python regression tests, offline plans and platform launchers; it does not deploy applications.

| Capability | Windows | Linux | macOS |
| --- | --- | --- | --- |
| Repository validation | Local execution plus CI | CI | CI |
| Settings wizard / offline planner | Implemented; local and CI tests | Implemented; CI tests | Implemented; CI tests |
| Synthetic file executor | Actual Windows ACL/lock tests | Actual POSIX mode/lock tests in CI | Actual POSIX mode/lock tests in CI |
| Read-only doctor | Live local Docker Desktop check plus mocked tests | Probe implementation; mocked tests only | Probe implementation; mocked tests only |
| Docker application installation | Experimental Glance and synthetic Kuma: live startup/restart/rendering/recovery | Glance/Kuma code and mocked tests; runtime unverified | Glance/Kuma code and mocked tests; runtime unverified |
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

Phase 3's local filesystem adapter is not a general-purpose native-service or Docker adapter. Use local storage with hard links, atomic replacement and supported permission semantics; network shares, unusual filesystems, concurrent privileged tampering and power-loss durability are not certified. Windows tests do not require SACL/audit-policy changes or blanket administrator rights. If scoped DACL/owner checks fail, execution stops rather than elevating or repairing existing permissions.
