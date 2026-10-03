# Changelog

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
