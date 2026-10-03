# Copy-paste implementation prompts

Use these one at a time. Each prompt includes its stopping point; do not paste every phase at once. Phase 0 is the foundation release. For subsequent work, the repository and fresh evidence take priority over old conversation summaries.

## Phase 1 — Discovery and reproducible configuration mapping

```text
Start Phase 1 of HomeLab-SelfHosting. Read README.md, docs/architecture.md,
docs/roadmap.md and SECURITY.md first. Perform a read-only inventory of my
existing Docker and native-host services. Do not restart, update, adopt or
modify production services. Trace effective Compose files, overrides, custom
image builds, storage, secrets by name only, startup tasks and backup scripts.
Keep detailed private inventory outside Git. Create a sanitized configuration
mapping and per-module runbooks with evidence and known gaps. Preserve licenses.
Validate and secret-scan the public files and staged diff. Commit and push the
completed reviewed milestone to HomeLab-SelfHosting and publish version 0.2.0
only when the phase gates pass. Report evidence and stop before Phase 2.
```

## Phase 2 — Doctor, wizard and plan

```text
Start Phase 2 of HomeLab-SelfHosting using the roadmap and Phase 1 evidence.
Implement the cross-platform coordinator, prerequisite doctor, service-selection
wizard, file-based plans, dependency resolution and deterministic dry runs.
Cover configurable storage, resource budgets, ports, CPU architecture and local
versus remote Docker contexts. Do not deploy applications. Use no live secrets.
Add Windows/Linux/macOS unit tests and honest compatibility status. Validate,
review and scan the public changes, commit and push, and release 0.3.0 only
after its gates pass. Report limitations and stop before Phase 3.
```

## Phase 3 — Storage, secrets and safe execution

```text
Start Phase 3 of HomeLab-SelfHosting. Implement protected private installation
state, configurable storage, secret generation/references, operation locks,
ownership tracking, reviewed-plan execution and resumable journals. Test only
an isolated synthetic module. Prove idempotency, interruption recovery, conflict
refusal and non-destructive cleanup. Never adopt existing resources implicitly
or rotate keys on retry. Add regression tests and documentation. Validate and
scan, commit and push, release 0.4.0 when gates pass, then stop before Phase 4.
```

## Phase 4 — Visibility and utilities

```text
Start Phase 4 of HomeLab-SelfHosting. Build isolated, selectable modules for
Glance/Uptime Kuma, Beszel, Stirling-PDF and opt-in Portainer in that order.
Use approved sanitized customizations and reproducible images. Do not edit
my existing containers or monitoring database. Test rendered UI, check state
transitions, persistence, settings recovery and measured resource use. Keep
Docker administration opt-in. Work in bounded app milestones. Publish tested,
scanned changes as 0.5.0 only when its gates pass; report and stop before Phase 5.
```

## Phase 5 — Personal data and recoverability

```text
Start Phase 5 of HomeLab-SelfHosting. Implement and validate Paperless, AFFiNE,
Nextcloud, Firefly III, Vaultwarden and Karakeep one at a time, beginning with
Paperless. Use synthetic nonempty data and isolated storage. Add consistent
application backups, independent encrypted recovery secrets, off-host backup
configuration and safe retention. Prove real content restoration, not just
HTTP health. Do not read or export personal documents, finances or passwords.
Use app-sized reviewed milestones; stop for missing authority or recovery keys.
Validate, scan and push coherent changes; release 0.6.0 only after all declared
gates pass. Report unverified items and stop before Phase 6.
```

## Phase 6 — Media and optional GPU

```text
Start Phase 6 of HomeLab-SelfHosting. Implement Immich, optional media-management
services and the Jellyfin adapter with compatible pinned releases and correct
storage mappings. Preserve originals. Limit ML separately and keep thumbnail,
OCR, indexing and transcoding jobs manual unless explicitly approved. Enable
GPU only after host/runtime/application capability checks and a synthetic test;
otherwise use CPU mode. Test backup/restore and resource limits in isolation.
Do not touch production media. Validate and scan, commit/push tested milestones,
release 0.7.0 when gates pass, and stop before Phase 7.
```

## Phase 7 — Development, communication and host integration

```text
Start Phase 7 of HomeLab-SelfHosting. Reproduce code-server toolchains and
extension/settings persistence with architecture-aware builds. Add Matrix with
identity/signing-key recovery and optional Element/TURN/bridges. Implement the
Coolify adapter without taking over its generated resources; label Windows
integration experimental until proven. Finish native monitoring/startup/task
adapters with platform-specific tests. Keep credentials and private workspaces
outside Git. Validate actual developer/chat/reboot behavior where test hosts
are available, record gaps, scan and push tested changes. Release 0.8.0 only
when declared gates pass, then stop before Phase 8.
```

## Phase 8 — Optional public and private remote access

```text
Start Phase 8 of HomeLab-SelfHosting. Implement documented optional Cloudflare
Tunnel, reverse-proxy and private VPN integration for user-owned accounts and
domains. Keep local operation independent and internal services unpublished.
Require explicit configuration before DNS/firewall/external-account changes.
Document SMTP/OAuth and client-compatible authentication. Test external login,
uploads, native clients, redirects and WebSockets where authorized. Do not
change my current public routes implicitly. Validate and scan, commit/push,
release 0.9.0 after gates pass and stop before Phase 9.
```

## Phase 9 — Portability and disaster-recovery rehearsal

```text
Start Phase 9 of HomeLab-SelfHosting. Test the declared Windows/Linux/macOS and
CPU-architecture matrix on appropriate real environments. Rebuild an isolated
installation from a tagged release, encrypted off-host backup and independent
recovery key. Verify nonempty application content and simulate interrupted
operations, missing storage and incompatible versions safely. Record recovery
time, recovery point and limitations. Never claim unavailable environments
passed. Preserve production and exact resource ownership. Scan and push evidence
and fixes; release 0.10.0 when gates pass, then stop before Phase 10.
```

## Phase 10 — Stable production release

```text
Start Phase 10 of HomeLab-SelfHosting. Audit all roadmap acceptance gates,
security controls, licenses, image references, reproducible builds, compatibility
matrix and recovery evidence. Finish beginner installation/operations guides,
troubleshooting and sanitized screenshots. Rehearse the documented new-user
workflow. Fix in-scope blockers with regression tests; do not claim zero bugs or
untested platform support. Scan the complete release contents and Git history,
publish checksums and version 1.0.0 only when the supported scope passes. Push
the release and provide a clear operational handoff with known limitations.
```
