# code-server validation record

Validated on 2026-11-15 using Windows Docker Desktop with Linux amd64 containers.

## Read-only production audit

- Existing container remained `running` and `healthy`.
- Existing tag: `local/code-server-dev:4.144.0`.
- Actual binary: code-server `4.131.0` with Code `1.131.0`.
- Runtime limits: 6 CPUs, 6 GiB memory and 2,048 PIDs.
- Idle sample: approximately 174 MiB before the isolated trial.
- Autosave, restore-window and persistent-terminal settings were already enabled.
- No workspace content, authentication value, SSH/GPG key or Git credential was read.

The tag/binary mismatch is retained as an explicit production migration blocker. No production container, path, setting or credential was changed.

## Candidate build proof

- Immutable code-server `4.145.0` multi-platform index resolved to separate amd64 and arm64 manifests.
- Node `24.19.0` amd64 archive passed SHA-256 verification.
- The Dockerfile rejects unsupported architectures and a base binary/version mismatch.
- All 18 requested extension versions installed successfully at build time.
- The candidate records the reviewed platform digest, Node checksum and application version as image labels.

The arm64 archive checksum and base manifest were verified from upstream metadata, but the image was not executed on an arm64 host. arm64 therefore remains build-contract coverage, not runtime certification.

## Disposable recovery trial

Evidence is stored outside Git in `C:\Docker\Code-Server-Evidence-20261115.json`; the matching private plan is beside it.

The owned synthetic trial proved:

- HTTP health and exact code-server/Node versions.
- All 18 pinned extensions in persistent state.
- Server-side GCC compilation with exact source and artifact hashes.
- Forced container recreation with workspace, settings and extension persistence.
- Copy-once autosave/window/terminal defaults.
- A stopped-state tar backup of config, local state, secure state and workspace.
- Deletion of the synthetic source state followed by independent-root restore.
- Restored HTTP health, source/settings hashes and extension set.
- Cleanup of the trial containers and root.

Observed trial samples were approximately 130.1 MiB idle and 130.2 MiB during the short compilation sample. The sampled CPU peak was only 0.04% because compilation completed between Docker sampling intervals; it is evidence of bounded operation, not a meaningful capacity benchmark.

The first recovery attempt discovered a Windows ACL translation failure while copying a Linux-created Java extension tree from the host. It stopped without claiming success. The final workflow archives and restores inside a Linux helper container, preserving permissions; that corrected trial passed.

## Remaining Phase 7 gates

- Encrypted off-host recovery with owner-managed development credentials.
- Real browser autosave and reconnect across a client disconnect.
- Production migration/rollback approval and public-domain WebSocket test.
- Actual arm64 build and runtime exercise.
- Matrix/Element identity-safe recovery and optional TURN tests.
- Coolify controller adapter without taking ownership of generated resources.
- Windows startup/task adapters and an actual reboot-recovery test.
