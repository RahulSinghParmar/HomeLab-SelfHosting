# Experimental Paperless-ngx recovery module

Version **0.6.0-alpha.3** retains the isolated Paperless-ngx application workflow and encrypted vault, then adds a separately gated clean-runner recovery rehearsal. It creates new synthetic projects and never adopts, changes, backs up or migrates an existing Paperless deployment automatically.

## Boundary and component set

- Paperless-ngx 3.2.1, PostgreSQL 18 and Valkey 9 are pinned by immutable image digests in `modules/paperless-ngx/images.json` and must already be cached.
- Only the Paperless web application is published, on a chosen `127.0.0.1` port. PostgreSQL and Valkey have no host ports and use an internal backend network.
- There is no Docker socket, device, GPU, host namespace, SMTP configuration, public domain or automatic signup.
- Ceilings match the measured reference deployment: Paperless 1792 MiB / 2 CPUs / 512 processes, PostgreSQL 512 MiB / 1 CPU / 128 processes, and Valkey 128 MiB / 0.25 CPU / 64 processes.
- Six owned named volumes keep the database, broker state, Paperless data, media, export and consume paths separate. `remove` retains every volume.
- Private credentials, Compose state, plan binding and locks stay outside Git with owner-restricted permissions.

This is a synthetic recovery candidate, not authorization to publish Paperless or store personal records in the trial.

## Fresh lifecycle and document exercise

Run from the repository root. The parent directory must exist; root, plan and backup destinations must be absent.

```sh
python -m homelab paperless plan --root D:/HomeLab-Trials/paperless --port 18010 --output D:/HomeLab-Trials/paperless-plan.json
python -m homelab paperless up --plan D:/HomeLab-Trials/paperless-plan.json --confirm FULL_PLAN_ID
python -m homelab paperless status --plan D:/HomeLab-Trials/paperless-plan.json
python -m homelab paperless exercise --plan D:/HomeLab-Trials/paperless-plan.json --confirm FULL_PLAN_ID
```

`exercise` is deliberately restricted to an empty fresh project. It generates one small PDF containing the text `HomeLab Paperless recovery validation`, feeds it through the consume directory, then edits its title and tag. Passing evidence requires:

- exactly one consumed document;
- searchable marker text;
- title `Phase 5 Recovery Fixture` and tag `phase5-recovery`;
- Paperless database checksum equal to the SHA-256 of the stored original file.

No account, financial record, password, private document or production path is used.

Stop/start is confirmation-gated and verifies owned resource drift. `remove` requires all services to be stopped and removes only owned containers and networks; it keeps data volumes and private records.

## One consistency boundary

The backup sequence is:

```text
verify nonempty content
-> stop Paperless web/consumer/task processes
-> run the supported document exporter against quiesced database and files
-> record semantic document/checksum evidence
-> create and validate a PostgreSQL custom archive
-> copy data, media and export trees
-> hash private Compose, sanitized configuration, credentials and all payloads
-> restart Paperless and require healthy state
```

PostgreSQL and Valkey remain available while the application is quiesced. The exporter, semantic inventory, dump and filesystem snapshot therefore represent one application-write boundary. A failed step retains the partial destination for review and still attempts to restart the web application.

```sh
python -m homelab paperless backup --plan D:/HomeLab-Trials/paperless-plan.json --confirm FULL_PLAN_ID --output D:/HomeLab-Trials/paperless-backup
```

The primary portable restore path is Paperless's documented **document exporter/importer**. The PostgreSQL dump and data/media/export snapshot are retained as a separate complete recovery set; the adapter never mixes raw database restoration with importer restoration. The manifest records the exact three images, completed consistency steps, semantic inventory, per-file hashes, database and configuration hashes, secret-material hash and pending recovery status.

API tokens are not included by the upstream exporter and must be regenerated after importer-based recovery. Export/import should use the same Paperless release because database layout can change across releases.

## Independent restore

Restore always uses a new root, project, port and six new volumes:

```sh
python -m homelab paperless plan --root D:/HomeLab-Trials/paperless-restored --port 18011 --restore-backup D:/HomeLab-Trials/paperless-backup --output D:/HomeLab-Trials/paperless-restore-plan.json
python -m homelab paperless up --plan D:/HomeLab-Trials/paperless-restore-plan.json --confirm RESTORE_PLAN_ID
```

The adapter validates the entire source manifest, starts the clean application once to initialize schema and volume ownership, stops it, imports while quiesced, starts it again, and compares the restored semantic inventory byte-for-byte with backup evidence. Successful state records `recovery.verified: true`. Interrupted restoration remains fail-closed and requires a fresh target.

## Encryption and retention boundary

The created directory is **sensitive plaintext staging**. It contains credentials, database content, private Compose configuration and documents. Owner-only local permissions are not encryption. Never commit, sync publicly, attach it to an issue or treat a same-disk copy as disaster recovery.

Version `0.6.0-alpha.2` adds the separate [Paperless encrypted recovery vault](paperless-vault.md). It validates a reviewed restic 0.19.1 Windows amd64 binary, keeps key material out of plans/output, accepts only this module's verified nonempty staging set, checks every repository data pack, restores to a new private target and protects the last restore-verified snapshot. The retention target is 7 daily, 4 weekly and 3 monthly points; preview never prunes and apply is separately confirmation-gated.

Version `0.6.0-alpha.3` adds Linux amd64 Restic validation, portable recovery manifests and a manual two-runner hosted rehearsal. The encrypted synthetic repository crosses the host boundary without its key; a fresh runner performs full-data verification, decryption, independent Paperless import and restart validation. No automated schedule, durable production repository or production-backup replacement is delivered.

## Certified and remaining scope

Certified on the recorded Windows Docker Desktop/Linux amd64 trials: fresh health, synthetic upload/open/search/edit, exact stored-file checksum, application quiesce, exporter, readable PostgreSQL archive, hashed filesystem/configuration set, reviewed restic binary verification, encrypted store, full data check, decrypted manifest equality, independent importer restore, semantic equality and stop/start persistence.

Not certified: the existing personal deployment, real records, public access, user/API-token recovery, SMTP/mail consumption, scanners, large libraries, concurrent ingestion, OCR quality/languages, ARM64, macOS runtime, durable production off-host media, real offline-key custody, scheduled retention, retention pruning in the live trial, upgrade/rollback or household hardware-failure recovery. Continue using the existing production backup schedule until it is separately reviewed; do not replace it with this candidate.

Upstream references: [Paperless administration and exporter/importer](https://github.com/paperless-ngx/paperless-ngx/blob/dev/docs/administration.md) and [Paperless-ngx v3.2.1](https://github.com/paperless-ngx/paperless-ngx/releases/tag/v3.2.1).
