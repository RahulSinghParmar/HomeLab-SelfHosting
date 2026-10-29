# Vaultwarden 0.6.0-alpha.10 validation

Date: **2026-10-30**

Scope: isolated generated vault account, secure note and attachment only; no personal users, vault items, attachments, credentials, configuration values or production database rows

Decision: **Go for the bounded experimental local recovery candidate. No-go for production adoption, encrypted/off-host backup replacement or completed Phase 5.**

## Production boundary

The existing `vaultwarden` container was inspected read-only before the rehearsal. It remained healthy on its existing private data bind and pinned Vaultwarden 1.37.1 image. The adapter used separate roots, Compose identities and loopback ports. No production container, configuration, database, attachment, user, secret or public route was changed.

## Windows Docker Desktop evidence

The validated environment was Docker Engine 29.9.2, Compose 5.6.1 and Python 3.14.6 on a Linux/amd64 Docker Desktop engine with eight CPUs and a 9.71 GiB memory ceiling. The source trial used exact image digests for Vaultwarden 1.37.1 and Playwright 1.64.0/Chromium. The long-running service had a read-only root filesystem, all capabilities dropped, `no-new-privileges`, one CPU, 384 MiB memory, 512 MiB memory-plus-swap, 256 PIDs and bounded JSON logs. Only its disposable loopback port was published; the data directory used a private Windows bind.

The rendered Web Vault registered `phase5-vaultwarden@example.invalid` with a generated password, dismissed the first-run tour, and created one secure note titled `HomeLab Vaultwarden Phase 5 recovery marker v1`. It decrypted the exact body in the browser, uploaded and downloaded `phase5-vaultwarden-attachment.txt`, and matched 49 bytes with SHA-256 `b816e5a2792e62c1cbe9aaf848554d54794b4a4d0649fff119360604e919ee6c`. The same title, body and attachment were verified after a full reload/unlock, in an independent browser context, and after container restart.

## Backup and restore evidence

The source plan ID was `5ca01af37911baf408b65a3211572dc452ac5e50da4a869cd33cb522a8af0ec8`. Before capture, the browser repeated the semantic checks. Vaultwarden's built-in `/vaultwarden backup` operation produced one valid SQLite snapshot; the app was then stopped while the snapshot, RSA keys, attachment/Send trees, generated recovery inputs, sanitized metadata and browser evidence were copied and checksummed. The app returned healthy and repeated the browser checks after capture.

The backup manifest ID was `49bb6a7f09ae29498aabfa05f6e33d3686d00e5e78f18cbc77a7501b8ec6e3d2`. A fresh project with plan ID `a1004af15b179b9c559c54cd2d3326a847b59a5dca18c7ed0b983d8ef796fc3e` restored the curated file set before first application start. The browser decrypted the exact note and downloaded the exact attachment, then the service restarted and repeated both checks. Restore evidence fingerprint `d614435f353d7f5dbef7f1c86ab80e3db411571914ab1152ddc5c702927042d6` bound the semantic result to the backup manifest.

After evidence capture, both generated projects, their networks, private roots, plans, plaintext-sensitive local staging set and three iterative browser-helper image tags were removed. No Vaultwarden module-labeled container or network remained. The personal `vaultwarden` container remained running and healthy with zero restarts on its original `C:/Docker/vaultwarden/vw-data` bind and unchanged image digest.

## Automated checks

Nine focused tests cover deterministic plans, runtime/input tampering, Compose hardening, credential validation, browser evidence parsing, confirmation ordering, backup/recovery binding, database/tree tampering and SQLite/manifest drift. The offline Phase 5 validator checks the CLI, exact image digests, browser runtime, module/docs/release files and recovery contracts. Repository validation, publication history, full regression, the six-platform Python matrix and whitespace checks remain release gates.

## Not proven

- personal vault recovery or production-scale data;
- organizations, collections, Sends semantics, TOTP/passkeys, emergency access or password history;
- browser extensions, native desktop/mobile clients, SMTP or public access controls;
- multi-user concurrency, load, upgrade migration or rollback;
- encrypted off-host storage, independent key custody, scheduling or 7/4/3 retention;
- live Linux, macOS or ARM64 runtime behavior.

The next Vaultwarden gate is separately approved encrypted off-host clean-runner recovery. It must transfer only encrypted backup material, keep recovery credentials out of the artifact, and repeat decrypted note/attachment checks on an independent runner.
