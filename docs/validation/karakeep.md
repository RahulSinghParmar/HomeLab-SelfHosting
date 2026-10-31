# Karakeep 0.6.0-alpha.12 validation

Date: **2026-10-31**

Scope: isolated generated account, searchable text bookmark and exact PNG asset only; no personal users, bookmarks, assets, credentials, configuration values or production database rows

Decision: **Go for the bounded experimental local recovery candidate. No-go for production adoption, encrypted/off-host backup replacement or completed Phase 5 until release CI passes.**

## Production boundary

The existing `karakeep` Compose project was inspected read-only before implementation. It contains app, Chrome and Meilisearch services. The application data root contains `db.db`, `queue.db` and `assets`; Meilisearch has a separate index bind. The module uses different roots, project identities and loopback ports. No production container, file, secret, account, public route or image was changed.

## Windows Docker Desktop evidence

The rehearsal used Docker Engine 29.9.2, Compose 5.6.1 and Python 3.14.6 on a Linux/amd64 Docker Desktop engine. The source project used exact digests for Karakeep 0.34.1, Karakeep Chrome, Meilisearch 1.41.0 and Playwright 1.64.0/Chromium. The three long-running services used read-only roots, all capabilities dropped, `no-new-privileges`, explicit runtime users, an internal network and bounded CPU, memory, PID and JSON-log resources. Only the app's loopback port was published.

The rendered UI registered the generated `phase5-karakeep@example.invalid` account and created a private full-access recovery key. It rendered `HomeLab Karakeep Phase 5 recovery marker v1` with the exact body `Synthetic searchable bookmark survives database and search-index recovery.` The API and rendered session found the record by full-text search. The separate PNG asset downloaded as 68 bytes with SHA-256 `613fe786197ef233bcb1b6d3ab7647c7b3c985889d0d56bca6d28b60e3cfe126`. A fresh authenticated browser repeated the rendered/search/asset checks after source restart. The restart screenshot was visually inspected and hashed as `1aeb836b6b121def6e7ace9ec644a0cedf1307463637c96ffccdb2068d9746ea`.

Karakeep's built-in export completed as a 392-byte ZIP with one safe JSON member containing the synthetic text bookmark. It omitted the binary asset bookmark, so the module records that export only as supplementary evidence and never represents it as complete recovery.

## Backup and restore evidence

The source plan ID was `8449b86a0b2aa0f244073ce5491d481914d5034a761a3f0742da91c34ad62668`. Before capture, a fresh browser repeated semantic checks. The complete source project was stopped while `db.db` and the asset tree were copied. SQLite `PRAGMA quick_check` returned `ok`; the manifest covered five authoritative data files, private and sanitized configuration, generated recovery inputs, browser evidence and complete hashes. `queue.db`, SQLite WAL/SHM files and the entire Meilisearch directory were excluded. The source returned healthy and repeated browser/search/asset checks after capture.

The backup manifest ID was `7879113bed21d6eb599a1238edcc074f1c27d72aba08810d74a2a3cf3114353f`. A fresh project with plan ID `af96de2b44cfb744d9b480b0a385747061eba3dfd58c3b5d65f71f201f2d4431` restored only authoritative state into a new data root and started with an empty search bind. The authenticated administrator reindex operation rebuilt Meilisearch, after which the browser rendered the same title/body, full-text search returned the restored bookmark and the PNG matched exactly. All three services restarted and repeated the same proof. Restore fingerprint `0de3e2f054c31b38d16fea085e527412a7b8b2335e57bbe54ea7f3c4f2d99f89` binds the semantic result to the backup; the recovered restart screenshot SHA-256 was `357ee85eeaf578d25c8d85ca942b5a0b007a1fd7f23ffabc938f3217f2df0793` and was visually inspected.

Observed memory after recovery was approximately 288–326 MiB for the app, 18–22 MiB for Meilisearch and 217–276 MiB for Chrome, below their respective 1024/512/512 MiB ceilings. These are a short idle/recovery snapshot, not capacity guidance.

Two adapter defects were caught rather than waived: Docker Desktop's tmpfs default required explicit `exec` on the private `/run` mount for `s6-overlay`, and Chromium HSTS required a neutral internal hostname instead of the Compose service name `app`. A later interrupted run also established the bounded-resume path and the need for an explicit fresh-session sign-in. Regression checks cover the resulting contracts.

After evidence capture, both generated projects and their networks were removed. The personal `karakeep` app, Chrome and Meilisearch containers remained on their original image identities, running for 44 hours with zero restarts; app and search were healthy. No personal data or configuration value was read or changed.

## Automated checks

Eleven focused tests cover deterministic planning, unsafe paths/ports, hardening and limits, Linux ownership, secret validation, browser evidence semantics, bounded resume, confirmation ordering, SQLite integrity, recovery-plan binding, derived-state exclusion and tamper rejection. The offline Phase 5 validator checks the CLI, exact image digests, browser runtime, module/docs/release files and recovery contracts. Repository validation, publication history, the complete regression suite, the six-job cross-platform matrix and whitespace checks remain release gates.

## Not proven

- personal or production-scale Karakeep recovery;
- multi-user collaboration, link crawling, archived pages, PDF/OCR or large assets;
- external AI, semantic/vector search, webhooks, email or public access;
- encrypted off-host storage, independent key custody, scheduling or 7/4/3 retention;
- upgrade migration, rollback, live Linux/macOS or ARM64 execution.

The next Karakeep gate requires a separate command after this evidence is complete: encrypted off-host recovery with separate key custody and an independent clean-runner browser/search/asset proof.
