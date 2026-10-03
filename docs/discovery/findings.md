# Phase 1 findings and disposition

These findings are from read-only discovery. They are migration requirements and review items, not fixes applied to the reference host.

## High-priority recovery and reproducibility gaps

| ID | Evidence-backed finding | Required treatment |
| --- | --- | --- |
| F01 | Live/root Coolify app is 4.3.23; resolving its alternate source Compose set currently selects 4.3.19 | Capture exact environment/override invocation and reconcile controller ownership before updates or adoption |
| F02 | Firefly backup uses Windows DPAPI for APP_KEY/database/cron secrets | Add independently decryptable encrypted recovery export before relying on clean-machine restore |
| F03 | Firefly backup archives database/configuration but does not copy upload/export directories | Define authoritative attachments/exports and include required assets; verify synthetic attachment recovery |
| F04 | Firefly dump is piped through gzip without a demonstrated pipe-failure guard | Check dump success independently; gzip integrity does not prove a valid database dump |
| F05 | Media-stack backup comments claim freezing, but implementation only ZIPs live config, then deletes old archives | Add consistent app-aware snapshots, verification and guarded retention; do not import script unchanged |
| F06 | Coolify backup copies raw `.env` and SSH material without encryption in that script | Treat existing backup tree as sensitive and require encrypted off-host recovery; never publish it |
| F07 | Beszel and code-server include hard-coded amd64/x64 build steps; Nextcloud base and many media tags float | Record compatible image locks, source patches and per-architecture build tests |
| F08 | Beszel has important untracked files and vendored PocketBase alongside tracked changes | Capture a reviewed complete patch/build source set; `git diff` alone is insufficient |

Windows DPAPI normally binds decryption to the originating user's credentials and computer. This is why a copied encrypted string alone is not a portable recovery kit. [Microsoft CryptProtectData documentation](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).

## Backup evidence and limits

AFFiNE and Paperless daily/monthly backup metadata contains a recorded `passed` restore-test status. Their weekly tasks report `267011` (`0x41303`), which means not yet run—not an observed task failure. Long-running monitoring tasks report `267009` (`0x41301`), which means running. [Microsoft task result constants](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-error-and-success-constants).

The daily backup metadata corresponds to the current local date. Monthly metadata represents an earlier recovery point even though the task's most recent invocation reported success. A task result is not a new backup timestamp.

AFFiNE captures table counts before stopping application writes. Paperless exports documents and records inventory before stopping the webserver and taking its database/file snapshot. Under concurrent activity, those artifacts can refer to different instants. The reusable implementation must define consistency boundaries and validate inventory against the actual recovery snapshot.

AFFiNE's inspected script does not first preserve whether the app was deliberately stopped; its cleanup starts the app after stopping it. The new coordinator must preserve prior running/paused/stopped state. No existing backup script was executed during this audit.

No dedicated scheduled backup was identified for several other applications, including Nextcloud, Immich, Vaultwarden, Matrix and code-server. This is **not proof that no backup exists**: app-internal, manual and externally managed backups were not exhaustively queried. Treat coverage as unverified until evidence is obtained.

## Platform, storage and management gaps

- Native Jellyfin uses a tray/user startup entry. It must not be documented as an automatically starting Windows service.
- Glances intentionally disables process listing; a missing process table is not necessarily a collector failure.
- Several services have no explicit container resource caps. The Docker VM ceiling still applies; copying this as a universal resource preset would be unsafe.
- Nextcloud binds multiple external drives, and Immich overlays multiple host paths under `/data`. Recovery must preserve the full mapping, not just the first mount.
- FlareSolverr and TURN have anonymous volumes that require explicit ownership/data-policy review.
- Many published ports bind all host interfaces. Public reachability still depends on firewall/router/tunnel configuration; a bind alone does not prove Internet exposure.
- Native tunnel/VPN service state is verified, but remote account policy/routes are not exported. Mark them owner-configured external dependencies.
- Actual active image references for Stirling-PDF, Portainer and Vaultwarden are version tags; older foundation notes described digest references. Live evidence supersedes those older descriptions.

## Disposition

Phase 1 documents these findings. Phase 2 can proceed with the planning engine because it does not deploy or adopt existing services. Application implementation/adoption cannot claim readiness until its relevant findings and restore gates are resolved. Production fixes require a separately scoped request.
