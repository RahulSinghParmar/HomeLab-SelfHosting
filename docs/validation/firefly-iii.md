# Firefly III 0.6.0-alpha.8 validation

Date: **2026-10-23**

Scope: isolated generated finance content only; no personal users, accounts, balances, transactions, attachments, credentials or production database rows

Decision: **Go for the bounded experimental local recovery candidate. No-go for production adoption, encrypted/off-host backup replacement or completed Phase 5.**

## Production boundary

The existing `firefly` project was checked read-only after the rehearsal. `fireflyiii`, `firefly_iii_db` and `firefly_iii_cron` remained healthy with zero restarts. Loopback port 8085 and `https://accounts.parmar.homes/` both redirected to their expected login URL. No production container, configuration, record, volume or secret was changed.

## Windows Docker Desktop evidence

The validated environment was Docker Engine 29.9.2, Compose 5.6.1 and Python 3.14.6 on a Linux/x86_64 Docker Desktop engine with eight CPUs and a 9.71 GiB memory ceiling. Exact digests supplied Firefly III 6.6.6, MariaDB 10.11.18 and Alpine 3.22.

A fresh source on loopback port 18040 created exactly one transaction group with description `HomeLab Firefly III Phase 5 recovery marker v1`, amount USD 42.15, a synthetic asset source, synthetic expense destination, category and tag. The uploaded `phase5-firefly-receipt.txt` was 49 bytes with SHA-256 `ba90c83d8b003580816ee7767a0a4d367f6f8f7b6fe6a42357c7f5ab85d4201a`. Two supported CSV exports, the Firefly integrity report and one real static-token cron request all passed.

The registration route deliberately rendered “Registration is currently not available” after the owner existed. It returns HTTP 200 because Firefly renders an explanatory page, so status code alone is not the security assertion.

## Backup and restore evidence

Stopped application writers, a successful independent `mariadb-check`, an exit-verified nonempty MariaDB logical dump, complete upload/export trees, private recovery inputs and checksums produced manifest ID `993b1011922f91f3d2517f7a8e64652e0cafc3fd7226faae18710fe7af6f56ac`.

A different project on loopback port 18041 initialized fresh resources, imported 81 Firefly tables, passed the live MariaDB check, restored one upload and two export files, and returned the exact transaction and attachment bytes. The first rehearsal identified that the non-root app image could not normalize Windows-copied ownership under the long-running security profile. The corrected workflow uses a disposable root helper with only `CAP_CHOWN`; the fresh rerun then completed with all services healthy.

The recovered project was stopped and started again. All three services returned healthy and the module repeated the manifest, transaction, attachment, export and integrity checks. The source snapshot was approximately 130 MiB app, 138 MiB database and 384 KiB cron; the recently restarted restore snapshot was approximately 75 MiB app, 95 MiB database and 384 KiB cron. These are point-in-time observations, not capacity guarantees.

Firefly logs include its explicit plaintext-attachment compatibility fallback while returning the exact expected bytes. MariaDB logged Docker Desktop's `io_uring` fallback and disabled-binlog expiration warning; database checks, semantic recovery and service health passed. No crash loop or restart occurred.

Both disposable projects, all six labeled volumes, generated roots, plans and the unencrypted sensitive backup were removed after evidence capture. Zero `org.homelab.module=firefly-iii` resources remained.

## Automated checks

Twelve focused tests cover deterministic secret-free plans, exact image/network/port/resource contracts, strict credentials, exact finance and raw-attachment semantics, confirmation ordering, restart behavior, import/live database checks, the bounded ownership helper, complete backup evidence, independent recovery plans and tamper rejection. The offline Phase 5 validator checks module, CLI, digests, docs and recovery markers. Repository validation, publication history, full regression, cross-platform CI and whitespace checks remain release gates.

## Not proven

- personal finance deployment recovery or production-scale data;
- Firefly Data Importer, bank connections, SMTP, webhooks, exchange rates, SSO or public access controls;
- multi-user separation, concurrent workloads, upgrade migration or rollback;
- encrypted off-host storage, independent key custody, scheduling or retention;
- live Linux/macOS/ARM64 runtime behavior.

The next Firefly gate is a separately approved encrypted off-host clean-runner recovery rehearsal. Production adoption requires explicit owner storage, independent key custody, scheduling, retention ownership and a real-data recovery plan.
