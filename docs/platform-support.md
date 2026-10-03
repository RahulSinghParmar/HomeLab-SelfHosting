# Platform and architecture support

## Current status

No application module is deployment-tested by this project yet. The existing Windows homelab is design evidence, not proof that the future installer can recreate it. Static CI checks only repository structure and Python tests.

| Capability | Windows | Linux | macOS |
| --- | --- | --- | --- |
| Repository validation | Local execution plus CI | CI | CI |
| Docker application installation | Planned: Docker Desktop with Linux containers/WSL2 | Planned: supported Docker Engine + Compose | Planned: Docker Desktop Linux VM |
| Native metrics / startup / scheduling | PowerShell, services, Task Scheduler adapter planned | Native tools and systemd adapter planned | Native tools and launchd adapter planned |
| GPU acceleration | Conditional, driver/runtime/app dependent | Conditional, driver/runtime/app dependent | Not assumed; CPU fallback |
| Coolify | Existing custom integration; not a portable supported baseline | Upstream-supported installation target | Explicit Linux VM/remote Linux host path |
| ARM64 application images | Unverified | Unverified | Unverified, especially Apple Silicon |

Coolify officially supports Linux servers; a Linux VM is the documented route on other host operating systems. The project's existing Windows integration must be labeled experimental until independently reproduced and tested. [Coolify installation documentation](https://coolify.io/docs/get-started/installation).

## Required test matrix

For each released module record OS/version, CPU architecture, Docker/runtime version, image digest, filesystem/storage type, fresh install result, restart result, restore result, and application-level content checks.

Core unit tests will target Windows/Linux/macOS with Python 3.12 and a current Python release. Runtime tests require actual supported Docker environments; CI host names alone are insufficient.

Preflight must check image architecture before pull or build. The reference code-server image contains a hard-coded Linux x64 Node download; this must be replaced or the module must explicitly refuse unsupported architectures. Emulation is not an automatic production fallback.

## Honest support labels

- **Planned:** documented design only.
- **Experimental:** implemented but incomplete runtime/recovery evidence.
- **Validated:** passed the declared platform, data, lifecycle, and recovery tests for the release.
- **Unsupported:** known incompatible or outside the maintained matrix.

Every release carries its matrix. Never imply "all platforms supported" because a wrapper script exists.
