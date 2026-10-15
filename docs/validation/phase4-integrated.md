# Phase 4 integrated validation

Date: 2026-10-15

Candidate: **0.5.0-rc.1**

Host: Windows with local Docker Desktop Linux amd64 engine

## Decision

The five bounded Phase 4 adapters are integrated as a release candidate. The review is a **go for repository-level `0.5.0-rc.1` testing** and a **no-go for stable `0.5.0` publication**. No production application was adopted, restarted, upgraded or reconfigured during this integrated review.

## Integrated static contract

`python tools/validate_phase4.py` checks:

- the package and catalog agree on the release candidate version;
- Glance, Uptime Kuma, Beszel, Stirling-PDF and Portainer expose their declared separate CLI commands;
- implementation, focused regression, module guide and validation-record files exist;
- every declared application image, including the Glance collector and Portainer's nested engine, uses an exact SHA-256 digest;
- this integrated record and the release review are present.

The repository validator, publication guard, Python compilation, Node syntax check for the Kuma configuration client, complete unit suite and whitespace review remain required together. This contract is intentionally offline and cannot substitute for application-level live evidence.

The final local run passed **294 tests with two expected platform skips** in 639.437 seconds. Repository validation reported 21 catalog modules and 64 documents; the Phase 4 contract, Python compilation, Node syntax and whitespace checks also passed. The release-candidate tag must be created only after the exact pushed commit passes the complete GitHub Actions matrix.

## Live host reconciliation

Read-only Docker inspection on 2026-10-15 reported Engine 29.8.2, Linux amd64, 58 containers, 56 running, none paused and two stopped. The existing Glance, Uptime Kuma, Beszel, Stirling-PDF and Portainer services were running; this was an inventory observation, not production certification.

One recovered, module-owned Beszel validation project remains intentionally running on a loopback-only port. Both services are running and paired, and the adapter reports that application verification is still required. Its login page rendered in the validation browser, but no authenticated session was available; credentials were not extracted or transmitted to bypass that boundary. Four Beszel trial volumes and two Kuma trial volumes remain labeled and retained as recoverable validation evidence. They are not treated as production data and are not silently deleted by this review.

## Module evidence summary

| Module | Completed evidence | Remaining boundary |
| --- | --- | --- |
| Glance | Seven pages, pinned validation, rendered fragments, privacy-filtered collector | Production migration/scheduler, visual screenshot, rollback and cross-platform runtime |
| Uptime Kuma | Idempotent desired state, HTTP/webhook delivery, public status page, stopped backup and independent restore | Real SMTP inbox, production migration and cross-platform runtime |
| Beszel | Metrics, agent down/up, stopped backup and exact record restore; Windows GPU/service records reached the hub | Authenticated chart inspection, controlled service-state/reboot and cross-platform runtime |
| Stirling-PDF | Real rotation, resource bounds, stopped five-volume backup and independent restore | Auth/public exposure, advanced conversions and cross-platform runtime |
| Portainer | Explicit isolated-engine grant, host invisibility, API exercise and authenticated restore | Host control, public exposure, real workloads and cross-platform runtime |

## Stable-release blockers

1. Inspect an authenticated Beszel system-detail chart and confirm restored history renders.
2. Complete the documented controlled Windows service-state and reboot acceptance tests for the native adapter, or explicitly exclude that adapter from stable support.
3. Decide whether Linux/macOS remain explicitly unverified for application runtime or receive live evidence before stable publication.
4. Repeat the staged/history publication review for the eventual stable candidate. The pattern scanner is a guard, not a complete secret or private-identifier audit.

## Safe handoff

The remaining Beszel trial must stay loopback-only until its UI gate is complete. Cleanup must use its exact reviewed plan and ownership labels; retained volumes or private snapshots require a separate explicit deletion decision. Production resources must never be selected as cleanup substitutes.
