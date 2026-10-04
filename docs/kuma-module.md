# Experimental Uptime Kuma module

Version **0.5.0-alpha.2** is a bounded Phase 4 experiment, not a production-monitor migration or a general Kuma installer. It creates a new project with two synthetic HTTP checks and a status page showing only the fixture. Existing Kuma, Glance and other services are never adopted or changed.

## Requirements and boundaries

- Python 3.12+, Docker Compose v2 and a running **local Linux amd64** Docker engine. Windows Docker Desktop was exercised live; Linux/macOS runtime deployment and ARM64 remain unverified.
- A cached image matching `modules/uptime-kuma/image.json`. Review the upstream release before explicitly pulling it; the adapter never pulls, builds or upgrades images.
- An existing local parent directory outside all Git checkouts, with permission to create owner-private files, and unused loopback ports. Do not use network storage, symlinks/junctions or existing application directories.
- Fixed budgets: Kuma 512 MiB / 1 CPU and a synthetic fixture 64 MiB / 0.25 CPU; bounded process counts and logs. These are ceilings, not reservations or general sizing recommendations.
- Dedicated bridge network with **outbound access allowed**; only Kuma is published on `127.0.0.1`. No Docker socket, host mounts, devices or added capabilities. Read-only root filesystems, no-new-privileges and a limited Kuma `/tmp`. The upstream image's root user is retained inside the container.
- `/app/data` is an owned Docker named volume, not the installation directory. Its physical drive follows Docker Desktop storage settings. Stopping/removing the trial never deletes this volume.

Only HTTP checks used here are tested. Docker, ICMP, browser-based and other privileged/specialized monitors are not certified. No SMTP, push tokens, public tunnel, real notifications or existing account import is configured. A status page describes selected synthetic checks; it is not an authorization boundary or proof that all host services are healthy.

## Plan and start

These commands run from the repository root. The examples use a pre-created private parent `D:/HomeLab-Trials`; choose your own existing local parent (on POSIX, an absolute path such as `/srv/homelab-trials`). Every new plan, installation and snapshot destination must be absent. All real plans/state/snapshots stay outside Git.

If the reviewed image is not already cached, this is a separate, explicit download:

```sh
docker pull louislam/uptime-kuma@sha256:c74379ac4509ce2d2c2633f509e67003ee2e45b6e995c5e43fc101f45a0e1fbe
```

```sh
python -m homelab kuma plan --root D:/HomeLab-Trials/kuma --port 13001 --output D:/HomeLab-Trials/kuma-plan.json
python -m homelab kuma up --plan D:/HomeLab-Trials/kuma-plan.json --confirm FULL_PLAN_ID
python -m homelab kuma status --plan D:/HomeLab-Trials/kuma-plan.json
```

Replace `FULL_PLAN_ID` with the entire hash printed by the reviewed plan. Changing root, port, image, engine or recovery input requires a new plan. Plans are local-engine-bound, not portable recovery packages.

`up` creates and starts owned containers; it does **not** claim the application is ready. Wait for startup and check the Kuma container's health in Docker Desktop. Then explicitly seed the fixture:

```sh
python -m homelab kuma seed --plan D:/HomeLab-Trials/kuma-plan.json --confirm FULL_PLAN_ID
python -m homelab kuma inspect-monitors --plan D:/HomeLab-Trials/kuma-plan.json
```

The setup creates `blueprint-admin` with a random password stored in the private installation's `credentials.json`. Open that file locally if you need the administration UI; do not paste it into chat, issues, screenshots or public documentation. The API client receives credentials over stdin and prints only synthetic evidence, not tokens. Do not manually create a different account first. Changed credentials/settings or foreign monitors are not silently overwritten.

Open the admin dashboard at `http://127.0.0.1:13001/dashboard` and selected status page at `http://127.0.0.1:13001/status/blueprint`. Only **Blueprint fixture** appears publicly; **Blueprint self-check** stays off that page. Both use a 20-second interval. A fresh monitor needs time to collect history. Repeating `seed` preserves matching monitor IDs; unexpected/changed definitions cause a refusal, not an import or reset.

## Verify real state changes

```sh
python -m homelab kuma fixture-down --plan D:/HomeLab-Trials/kuma-plan.json --confirm FULL_PLAN_ID
python -m homelab kuma inspect-monitors --plan D:/HomeLab-Trials/kuma-plan.json
python -m homelab kuma fixture-up --plan D:/HomeLab-Trials/kuma-plan.json --confirm FULL_PLAN_ID
```

After each transition, allow at least one polling interval plus the HTTP timeout and status-page refresh. Inspect again and refresh the page: it should change from operational to degraded and back, while the self-check stays up. This tests monitoring transitions, **not email/push alert delivery**. `fixture-down` affects only the owned synthetic HTTP container, never a real service.

Stop/start with the same reviewed plan preserves the account, monitor IDs and history:

```sh
python -m homelab kuma stop --plan D:/HomeLab-Trials/kuma-plan.json --confirm FULL_PLAN_ID
python -m homelab kuma up --plan D:/HomeLab-Trials/kuma-plan.json --confirm FULL_PLAN_ID
```

An already-running unchanged deployment is not restarted by `up`. Do not edit the generated Compose/state files or operate these projects with blanket Compose commands; drift and missing/foreign resources cause refusal.

## Stopped-state backup and independent recovery

Stop both owned services before copying their data. The backup operation refuses running services and existing destinations:

```sh
python -m homelab kuma stop --plan D:/HomeLab-Trials/kuma-plan.json --confirm FULL_PLAN_ID
python -m homelab kuma backup --plan D:/HomeLab-Trials/kuma-plan.json --confirm FULL_PLAN_ID --output D:/HomeLab-Trials/kuma-snapshot
```

The snapshot contains the **complete `/app/data` tree**, `credentials.json` and a manifest with image identity, SHA-256 file hashes and semantic SQLite evidence. Validation requires a healthy database, the exact two synthetic monitors, one expected account/status page, no notification integrations and nonempty heartbeat history. This is deliberately not a production backup utility.

**The snapshot is unencrypted and contains credentials.** Private ACLs/modes restrict normal local access; they do not protect against Docker administrators, the same user or privileged tampering. Keep it outside Git, do not upload it to CI and use a separately reviewed encrypted off-host recovery process before relying on it for disaster recovery. Checksums detect accidental drift, not malicious replacement of both files and manifest. A successful copy reports `recovery_verified: false` until you perform the following independent rehearsal:

```sh
python -m homelab kuma plan --root D:/HomeLab-Trials/kuma-restored --port 13002 --restore-backup D:/HomeLab-Trials/kuma-snapshot --output D:/HomeLab-Trials/kuma-restore-plan.json
python -m homelab kuma up --plan D:/HomeLab-Trials/kuma-restore-plan.json --confirm RESTORE_PLAN_ID
python -m homelab kuma inspect-monitors --plan D:/HomeLab-Trials/kuma-restore-plan.json
```

Use the **new** plan hash, wait for readiness, authenticate using the preserved account and inspect `http://127.0.0.1:13002/status/blueprint`. Check monitor IDs, down/up history and selected page content, not just HTTP 200. Do not run `seed` to manufacture missing recovery evidence. Record the rehearsal separately; the original backup manifest is immutable and does not acquire a success flag automatically.

Recovery creates a fresh project, containers and volume, copies data while containers have never started, then starts the fixture and application. It never overwrites existing state. Keep the source snapshot unchanged and available: **every recovery-plan operation currently revalidates it**, including stop/removal. This conservative dependency is a prerelease limitation, not a general restore-management design.

## Cleanup and failure handling

```sh
python -m homelab kuma stop --plan D:/HomeLab-Trials/kuma-plan.json --confirm FULL_PLAN_ID
python -m homelab kuma remove --plan D:/HomeLab-Trials/kuma-plan.json --confirm FULL_PLAN_ID
```

Repeat against the restore plan with its own hash. Removal requires stopped services, validates ownership/attachments, and removes only exact owned containers and network. **The data volume, private files and snapshot remain recoverable.** There is no volume-deletion command. A removed installation cannot be reactivated; use a new reviewed recovery root.

- Occupied port/path, wrong engine, changed permissions, foreign labels/attachments, altered Compose/credentials or partial service creation: stop and review private evidence; do not force adoption or delete data to bypass the guard.
- An interrupted restore copy leaves `restore-copying` and fails closed. Preserve it and use a fresh target after reviewing/quarantining the partial trial. No automatic resume or cleanup is provided for this ambiguous case.
- Partial file initialization or `.pending-*` files require manual review. An interrupted status-page setup may likewise require review instead of automatic repair.
- The hardened image can log `Failed to start nscd`; the optional DNS cache daemon cannot write normally with this root filesystem. Tested HTTP/Docker DNS, monitoring and health checks still passed. Do not weaken privileges merely to hide the warning; other DNS-dependent workloads need their own validation.
- App readiness, valid authentication and live checks matter more than container status. `status` intentionally says `requires-application-verification`.

The client targets the [pinned 2.5.5 source interface](https://github.com/louislam/uptime-kuma/tree/2.5.5) and [upstream internal API](https://github.com/louislam/uptime-kuma/wiki/Internal-API), not a promised stable public management API. Image upgrades, database migrations and rollback need a new compatibility/recovery rehearsal; no update command is supplied. Digest pinning is reproducibility, not security certification. See [release evidence](releases/v0.5.0-alpha.2.md) and [platform support](platform-support.md).
