# AFFiNE 0.6.0-alpha.4 validation

Date: **2026-10-20**

Scope: isolated generated workspace content only; no personal notes, users, production credentials or production AFFiNE files

Decision: **Go for the bounded experimental AFFiNE recovery candidate. No-go for production adoption, backup replacement or completed Phase 5.**

## Production boundary

The existing AFFiNE deployment was not adopted, restarted, updated, queried for user content or used as a backup source. Its four observed roles—AFFiNE, PostgreSQL, Redis and a successfully exited one-shot migration—remain owned by the existing Compose project. The synthetic source, backup and restore used separate roots, project names, credentials, ports and volumes.

## Windows Docker Desktop trial

The source project used loopback port `18020` and exact linux/amd64 image digests for AFFiNE 0.27.4, PostgreSQL pgvector pg16 and Redis 8 Alpine. AFFiNE, PostgreSQL and Redis became healthy; the migration completed with exit code 0, which is the expected one-shot lifecycle.

The application exercise created a workspace and Yjs document state containing the marker `HomeLab AFFiNE Phase 5 recovery marker v1`. A second independently authenticated session loaded the same state. The AFFiNE container was restarted, became healthy, and returned the same semantic state again.

Recorded bounded evidence:

- workspace ID: `0a48a2e3-42b3-4295-867d-773c238f8650`;
- document ID: `bb04ed67-ee14-4060-ade2-9a57ef5bc510`;
- two independent authenticated sessions: true;
- restart persistence: true;
- marker SHA-256: `6e2c42dd227b06ff841dd9b6faff19400924d95505ad9caa10ab9104560c5f68`;
- synchronized state SHA-256: `977b30b298f52e3a539e0e006f6a5e6f1fc104b36d56fbd7508b9aa03859a0b3`.

These identifiers belong only to the disposable synthetic trial. The semantic marker is Yjs text synchronized by the AFFiNE server; it is not evidence of a fully rendered editor block tree.

## Backup evidence

The module verified the saved fixture, stopped application writes, created a PostgreSQL custom-format dump, validated its catalog, copied config/storage and private recovery inputs, generated sanitized metadata, hashed every retained file tree, restarted AFFiNE and re-read the same semantic state.

The validated backup fingerprint was `bb99eb9c1a4c6ae1dc05d79cc16096491ac049989c58118f27300f6af5176201`. The backup is application-consistent but plaintext-sensitive. It contains recovery credentials and is not certified as encrypted, off-host or independently keyed.

## Independent restore evidence

A different project on loopback port `18021` initialized fresh Redis/PostgreSQL volumes, restored the database plus config/storage, completed the pinned migration, started healthy and loaded the saved document. Its manifest ID was `90cfafb2e8d77c0aa78e5c4ee47dafdd59aed0dbe9bea6731d6a2b3103c40209`.

The restored state matched the source marker and state checksums. A subsequent AFFiNE restart remained healthy and returned identical semantic content. No source container, volume or installation directory was mounted into the restore project.

## Automated checks

Focused tests cover deterministic secret-free plans, exact image/network/port/resource contracts, private credential generation, bounded fixture parsing, confirmation gates, complete backup verification, checksum tamper rejection and restore-plan binding. The offline Phase 5 validator checks the CLI surface, module/docs/evidence files, exact image digests and fixture safeguards. Repository validation, publication history, whitespace checks and the complete cross-platform unit-test matrix are release gates.

## Not proven

- Browser-rendered AFFiNE blocks, attachments or editor-feature fidelity.
- Desktop/mobile clients, public domain access, mail, OAuth, AI or indexing.
- Production data migration, representative scale, concurrent editing or version upgrades.
- Encrypted off-host recovery, retention, offline recovery-key custody or a clean-machine rehearsal.
- Linux/macOS/ARM64 live runtime behavior.

The next AFFiNE gate is a separately encrypted off-host recovery rehearsal and a browser-rendered document check. Phase 5 then proceeds to Nextcloud only after an explicit separate command.
