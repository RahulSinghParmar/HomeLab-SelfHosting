# Changelog

## 0.5.0-alpha.2 — 2026-10-04

- Added a separately gated, digest-pinned Uptime Kuma trial with two synthetic HTTP monitors, generated private credentials and one selected status-page monitor.
- Added bounded lifecycle, drift/ownership checks, idempotent registration and fixture-only up/down controls; no Docker socket, production adoption or notification configuration.
- Added stopped-state whole-data snapshots, SQLite/content verification and recovery into a fresh independent named volume, preserving account identity, monitor IDs and heartbeat history.
- Verified rendered up/down/up transitions, restart/retry persistence and restored page content on Windows Docker Desktop Linux amd64.
- Added 31 Kuma regression tests; documented plaintext snapshot sensitivity, optional DNS-daemon warning and unsupported monitor/platform/update cases.
- Existing services remain untouched; general deployment and full Phase 4 remain incomplete.

## 0.5.0-alpha.1 — 2026-10-04

- Added a separate experimental Glance starter: reviewed plans, private owned state, bounded Docker lifecycle, configuration export and independent starter recovery.
- Pinned the tested amd64 image by digest; loopback binding, dedicated bridge, no Docker socket, read-only configuration/root filesystem and fixed resource/log limits.
- Added drift, foreign-resource, context, port and interruption guards plus regression tests.
- Found and corrected an internal-only Docker network that accepted but did not publish the requested port; verify effective bindings as well as requested ones.
- Recorded Windows live rendering, retry, restart, configuration recovery and measured lightweight resource usage.
- Full Phase 4, general application execution, custom-dashboard recovery and other platform runtime certification remain pending. Existing deployments were not modified.

## 0.4.0 — 2026-10-03

- Added separately gated synthetic file-module planning, apply, verified status and non-destructive retirement.
- Added private local storage with Windows owner/DACL verification and POSIX owner/mode enforcement; no automatic elevation or existing-folder permission repair.
- Added reusable 256-bit generated credentials, reference-only reports, ownership markers and fingerprint checks.
- Added kernel operation locks, atomic state snapshots, ordered journals, retry reconciliation and fail-closed handling of ambiguous partial writes.
- Added real filesystem, lock contention/process death, interruption, tampering, retention and CLI privacy tests.
- Application deployment remains disabled; no existing containers, service settings or user data were changed.

## 0.3.0 — 2026-10-03

- Added a Python 3.12+ selection wizard, strict private settings validation, offline deterministic plans and read-only host doctor.
- Added thin PowerShell/POSIX launchers and runnable Windows/Linux/macOS settings examples.
- Added provisional module budgets, dependency ordering, TCP/UDP range conflicts, per-service storage proposals and redacted input-bound plan hashes.
- Refuse remote Docker endpoints, ambiguous environment overrides, occupied fresh-install paths, overlapping paths, Git-contained output and output overwrites.
- Added Windows live read-only evidence and cross-platform mocked regression/launcher checks; application runtime support remains unverified.
- No containers, live configuration, services, firewall rules or global Docker limits were changed.

## 0.2.0 — 2026-10-03

- Added a metadata-only Windows collector with outside-checkout output guards and mocked privacy tests.
- Reconciled all 54 observed containers: 52 assigned to blueprint modules and two private controller-generated applications explicitly excluded.
- Added 21 application runbooks, configuration/secret/storage mapping, evidence register and custom-build provenance ledger.
- Documented Coolify source drift, backup consistency/coverage gaps, Windows-bound recovery secrets and native startup limitations.
- Extended validation to enforce module coverage, logical source locators and runbook presence.
- No production service changes, backup jobs, restores or heavy application tasks were performed.

## 0.1.0 — 2026-10-03

- Added sanitized service-family inventory and 21-module catalog.
- Defined modular deployment architecture, platform adapters, storage policy, and recovery boundaries.
- Added an incremental roadmap with acceptance gates and copy-paste phase prompts.
- Added example design plans, a repository validator, regression tests, and static CI.
- No deployment or recovery automation is implemented in this foundation release.
