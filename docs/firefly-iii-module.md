# Firefly III application-aware recovery module

Version `0.6.0-alpha.8` adds a bounded Firefly III recovery candidate for new synthetic deployments. It does not adopt, restart, update, export or read records from the existing personal finance deployment.

## Release boundary

The module uses exact image digests for Firefly III 6.6.6, MariaDB 10.11.18 and Alpine 3.22. It creates separate app, database and cron services. Only the app is published, on a loopback address; MariaDB and cron remain on an internal network. Generated APP_KEY, database password and 32-character cron token are stored in private files and are excluded from plans and command output. The Docker socket, host devices, GPU access, SMTP delivery and external integrations are absent.

Resource ceilings are 1024 MiB and two CPUs for the app, 512 MiB and one CPU for MariaDB, and 64 MiB and one quarter CPU for cron. These are limits, not idle reservations. During the Windows recovery rehearsal, the source used about 130 MiB app, 138 MiB database and under 1 MiB cron; the recently restarted recovery project used about 75 MiB app, 95 MiB database and under 1 MiB cron.

Firefly runs as `www-data` with `no-new-privileges`. The one restore step that must return Windows-copied volume files to that user runs in a disposable `--rm` helper as UID 0 with only `CAP_CHOWN`; the long-running services do not receive that override.

## Operator workflow

Use a new root and keep the private plan outside it:

```powershell
python -m homelab firefly plan --root C:\Docker\homelab-firefly-trial --port 18040 --output C:\Docker\homelab-firefly-plan.json
python -m homelab firefly up --plan C:\Docker\homelab-firefly-plan.json --confirm <plan-id>
python -m homelab firefly status --plan C:\Docker\homelab-firefly-plan.json
python -m homelab firefly exercise --plan C:\Docker\homelab-firefly-plan.json --confirm <plan-id>
python -m homelab firefly backup --plan C:\Docker\homelab-firefly-plan.json --output C:\Docker\homelab-firefly-backup --confirm <plan-id>
python -m homelab firefly stop --plan C:\Docker\homelab-firefly-plan.json --confirm <plan-id>
python -m homelab firefly remove --plan C:\Docker\homelab-firefly-plan.json --confirm <plan-id>
```

Mutating commands require the complete reviewed plan ID. `remove` retains named volumes and private files; deletion is a separate reviewed cleanup action. An interrupted restore is intentionally non-resumable because partially imported finance state requires evidence review and a fresh target.

## Finance and scheduler exercise

The exercise creates one synthetic asset account and one fixed USD withdrawal with an expense destination, category and tag. It uploads a fixed 49-byte receipt through the Firefly API as `application/octet-stream`, downloads it again and compares its exact SHA-256. It then creates two supported CSV exports, runs `firefly-iii:report-integrity`, briefly stops the owned cron service, invokes the actual static-token cron endpoint once and restores cron in a `finally` block.

No personal account names, balances, identities or access tokens are used. Registration is unavailable after the synthetic owner exists. API and CLI tokens used by the fixture are generated inside the disposable application and never printed or written into public evidence.

## Consistent backup

Backup requires a healthy owned project and the exact finance fixture. It stops cron and the app to quiesce application writes, independently runs `mariadb-check`, writes a MariaDB logical dump directly to a result file, verifies the dump command exit, requires a nonempty file and checks the dump-completion marker. It does not pipe the database command through compression.

The recovery set contains:

- the logical MariaDB dump;
- complete upload and export trees;
- generated APP_KEY, database password and cron token;
- the private Compose definition and sanitized configuration metadata;
- complete checksums and semantic evidence for the transaction, attachment and exports.

The app and cron are returned to healthy state after capture. The backup is plaintext-sensitive and must remain outside Git, cloud synchronization and public support bundles. `0.6.0-alpha.8` has no encrypted vault or off-host retention workflow.

## Independent restore

Create a second plan with a different absent root and port plus `--restore-backup`. Restore accepts only a complete checksum-valid backup into never-started resources. It starts the fresh database, imports the logical dump, runs a live database check, restores upload/export files, performs the bounded ownership normalization and then starts app and cron.

Recovery is accepted only when the transaction fields, attachment filename/bytes/hash and export counts equal the backup evidence and Firefly's integrity report passes. A subsequent project stop/start repeats the same semantic verification.

The [official Docker example](https://github.com/firefly-iii/docker/blob/main/docker-compose.yml) documents the app/database/cron shape, and Firefly's [environment example](https://github.com/firefly-iii/firefly-iii/blob/main/.env.example) documents APP_KEY, database and static cron inputs.

## Current no-go items

- adoption, migration, update or backup replacement for the personal deployment;
- encrypted or off-host storage, retention, scheduling or offline-key custody;
- importer, bank, webhook, exchange-rate, SMTP, SSO or public-domain behavior;
- multi-user finance separation, representative data size, concurrent load or performance tuning;
- cross-version database migration, image rollback, Linux/macOS or ARM64 runtime certification;
- stable `0.6.0` or completion of Phase 5.

See the [Windows validation record](validation/firefly-iii.md), the [observed deployment runbook](runbooks/firefly-iii.md) and the [recovery design](recovery.md).
