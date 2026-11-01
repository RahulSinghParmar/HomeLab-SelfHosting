# Karakeep application-aware recovery module

Version **0.6.0-alpha.12** adds a bounded Karakeep recovery adapter for generated test data. It does not inspect, import, restart, upgrade or modify an existing Karakeep installation.

## What the module proves

- Karakeep 0.34.1, Karakeep Chrome, Meilisearch 1.41.0 and Playwright/Chromium 1.64.0 images are pinned by digest;
- app, browser and search services use an internal bridge, while only the app's loopback HTTP port is published;
- long-running services use read-only roots, dropped capabilities, `no-new-privileges`, explicit users and bounded CPU, memory, PID and JSON-log resources;
- a rendered browser registers a generated first administrator and creates a full-access recovery API key without exposing it in command output;
- the fixture contains one searchable text bookmark and one exact PNG asset bookmark;
- the built-in logical export is downloaded and inspected for the text bookmark as supplementary evidence;
- a quiesced SQLite database plus the complete asset tree restores into a fresh unrelated project;
- the restore starts with empty queue and Meilisearch state, invokes the authenticated administrator reindex operation, finds the bookmark by full-text search, downloads exact asset bytes, renders the title and repeats the checks after restart.

The SQLite database and assets are authoritative. `queue.db`, SQLite WAL/SHM files and Meilisearch data are derived and deliberately excluded. The built-in logical export includes the synthetic text bookmark but omits the binary asset bookmark, so it is not a replacement for assets or the authoritative database.

## Safety boundaries

The trial root, project name, owner label, port, generated credentials and exact image set are plan-bound. Every mutation requires the complete plan ID. Existing Docker resources are never adopted. Removal affects only owned containers and their internal network; generated data remains for an explicit operator decision.

Registration is enabled only for the disposable loopback trial. Mail, external AI, embedding, LLM OCR and telemetry are disabled. No public route, Docker socket, host device or GPU is attached. These settings are recovery-test controls, not a production account policy.

## Commands

Create the source plan outside the installation root:

```sh
python -m homelab karakeep plan --root C:/Docker/homelab-karakeep-trial --port 18060 --output C:/Docker/homelab-karakeep-plan.json
```

Review the redacted output and use its complete `plan_id`:

```sh
python -m homelab karakeep up --plan C:/Docker/homelab-karakeep-plan.json --confirm PLAN_ID
python -m homelab karakeep exercise --plan C:/Docker/homelab-karakeep-plan.json --confirm PLAN_ID
python -m homelab karakeep backup --plan C:/Docker/homelab-karakeep-plan.json --output C:/Docker/homelab-karakeep-backup --confirm PLAN_ID
```

Create an unrelated restore plan with a different root and port:

```sh
python -m homelab karakeep plan --root C:/Docker/homelab-karakeep-restore --port 18061 --restore-backup C:/Docker/homelab-karakeep-backup --output C:/Docker/homelab-karakeep-restore-plan.json
python -m homelab karakeep up --plan C:/Docker/homelab-karakeep-restore-plan.json --confirm RESTORE_PLAN_ID
```

Status is read-only. Stop before removal:

```sh
python -m homelab karakeep status --plan C:/Docker/homelab-karakeep-plan.json
python -m homelab karakeep stop --plan C:/Docker/homelab-karakeep-plan.json --confirm PLAN_ID
python -m homelab karakeep remove --plan C:/Docker/homelab-karakeep-plan.json --confirm PLAN_ID
```

## Recovery set

The private staging set contains generated credentials, `db.db`, the asset tree, private and sanitized Compose metadata, rendered semantic evidence, the supplementary logical export, complete checksums and a manifest. Verification runs SQLite `PRAGMA quick_check`, rejects queue/index/WAL/SHM material, validates every file checksum and binds the restore plan to the complete manifest.

The set is plaintext-sensitive and local. Keep it outside Git and synchronized folders. It is not hardware-failure recovery until an encrypted off-host copy and separately recoverable key pass an independent clean-runner restore.

## Not covered

Personal bookmarks, multi-user sharing, lists/tags beyond the exported fixture, link crawling, browser archives, PDFs, OCR, external AI, webhooks, native/mobile clients, SMTP, public reverse proxies, load, upgrade migration and rollback are untested. The first runtime rehearsal targets Windows Docker Desktop Linux/amd64; Linux, macOS and ARM64 behavior is not certified.

See [validation evidence](validation/karakeep.md), the [encrypted recovery vault](karakeep-vault.md), the [off-host recovery gate](validation/karakeep-off-host-recovery.md), the [production inventory runbook](runbooks/karakeep.md), and Karakeep's [configuration reference](https://github.com/karakeep-app/karakeep/blob/main/docs/docs/03-configuration/01-environment-variables.md).
