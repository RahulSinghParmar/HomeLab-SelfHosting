# Experimental Beszel module

This bounded Phase 4 implementation creates an **upstream Beszel 0.21.0 hub and restricted container agent**, separate from any existing deployment. It is not a production migration, native Windows monitoring installer or full catalog certification. See the [validation record](validation/beszel-trial.md) for completed checks and outstanding gates.

## Boundaries and requirements

- Python 3.12+, Compose v2-compatible CLI and a local **Linux amd64** Docker engine. Windows Docker Desktop is the live test platform. Linux/macOS Docker runtime and ARM64 remain unverified.
- Both digest-pinned images from `modules/beszel/image.json` must already be cached. Execution never pulls, builds or updates images implicitly.
- An unused loopback port, absent installation directory under an existing local parent outside Git, and supported owner-private permissions. Network shares, junctions/symlinks and existing application directories are refused.
- Hub: 256 MiB and 0.5 CPU ceiling. Agent: 128 MiB and 0.5 CPU ceiling. Each has 100-process and bounded-log limits, a read-only root, dropped capabilities, no-new-privileges and a 32 MiB temporary filesystem. Limits are ceilings, not reservations or general production sizing recommendations.
- Only the hub is published, on `127.0.0.1`. The agent listens only within a dedicated bridge; outbound access is allowed. No Docker socket, host filesystem, native service access, host namespaces, GPU devices or public tunnel is granted. The upstream images' root user remains inside each container.
- Both image-declared data directories use explicit owned named volumes: hub `/beszel_data`, agent `/var/lib/beszel-agent`. Their physical drive follows Docker engine storage settings, not the private installation root.

**Metrics describe the Docker/Linux view, not the physical Windows host.** Memory and CPU views may include the Docker VM; disk and network views depend on the container namespace and discovered devices. They are not guaranteed to be per-container usage. GPU and native services are reported as **not exposed**, never silently interpreted as zero usage or healthy services. Docker-container inventory needs additional privileged integration and is intentionally absent here.

The reference homelab's custom Windows GPU fallback, Windows Service Control Manager collector and same/new-origin login-alert changes are **not bundled or certified** by this upstream trial. Porting them needs a separate source/license review, native agent lifecycle and authentication-origin regression tests. Existing customized hub and Windows agent are untouched. No SMTP, real notification, OAuth or account import is configured.

## Reviewed plan and startup

Run from the repository root. Replace `D:/HomeLab-Trials` with your existing local parent, or an absolute POSIX path such as `/srv/homelab-trials`. Keep all generated plans, credentials and snapshots outside Git. Every new output must be absent.

Explicit downloads, after reviewing the pinned upstream release:

```sh
docker pull henrygd/beszel@sha256:7b3ee8cd890263b2c1b2f332b139b91a22f6d770bbfb0eced5737b3be9add65b
docker pull henrygd/beszel-agent@sha256:31cc28b1278691747a18483ab510695b3db8e8ce9aab361e7a8c47ac58f55333
python -m homelab beszel plan --root D:/HomeLab-Trials/beszel --port 18090 --output D:/HomeLab-Trials/beszel-plan.json
python -m homelab beszel up --plan D:/HomeLab-Trials/beszel-plan.json --confirm FULL_PLAN_ID
python -m homelab beszel status --plan D:/HomeLab-Trials/beszel-plan.json
```

Use the entire reviewed plan hash. It binds the installation, images, resource policy and local engine. A port, image or recovery change needs a new plan; this is not an edit-in-place production configuration interface.

`up` initially starts **only the hub**. Allow startup, then:

```sh
python -m homelab beszel seed --plan D:/HomeLab-Trials/beszel-plan.json --confirm FULL_PLAN_ID
python -m homelab beszel inspect-metrics --plan D:/HomeLab-Trials/beszel-plan.json
```

`seed` creates the synthetic `admin@example.invalid` account with the random password already stored in private `credentials.json`, obtains the hub's public SSH key, registers **Blueprint Docker agent** at `agent:45876`, then creates and starts the isolated agent. Passwords and API tokens never appear in generated Compose environment variables or command output. The SSH public key is public configuration; the hub's private key stays in its data volume. SSH mode does not require a universal token. The agent data volume may remain empty in this mode.

The bootstrap/API client uses only the verified owned hub's effective loopback port, disables environment proxies, refuses redirects and bounds response size/time. Its REST interface is tied to the pinned upstream version. Do not create a different initial account or modify the generated Compose/state/credentials files. The first-run hub is uninitialized until `seed`: use a trusted single-user host and complete initialization promptly. Loopback is not protection against other local users or Docker administrators.

Open `http://127.0.0.1:18090/` and sign in using the private credentials file. Do not paste that file into chat, logs, issues or screenshots. Initial SSH pairing and updates take time; allow approximately a minute for polling. The API summary deliberately omits detailed hardware values and reports history count, latest record, collected field names and status. Container `running` alone is not application-health proof.

## Transitions and persistence

```sh
python -m homelab beszel agent-down --plan D:/HomeLab-Trials/beszel-plan.json --confirm FULL_PLAN_ID
python -m homelab beszel inspect-metrics --plan D:/HomeLab-Trials/beszel-plan.json
python -m homelab beszel agent-up --plan D:/HomeLab-Trials/beszel-plan.json --confirm FULL_PLAN_ID
python -m homelab beszel inspect-metrics --plan D:/HomeLab-Trials/beszel-plan.json
```

Allow a polling interval plus timeouts between transitions. The hub should move from up to down to up and resume new metric history. Old history remains during an outage; a latest-record timestamp must not be confused with current connectivity. This tests connection monitoring, **not notification delivery**.

```sh
python -m homelab beszel stop --plan D:/HomeLab-Trials/beszel-plan.json --confirm FULL_PLAN_ID
python -m homelab beszel up --plan D:/HomeLab-Trials/beszel-plan.json --confirm FULL_PLAN_ID
```

Repeating `up` on matching running containers does not restart them. Repeating `seed` preserves matching system/account identities and never regenerates credentials or replaces a missing recorded system. Privilege, image, environment, ports, process, mounts, labels, runtime and foreign attachment drift cause refusal. Paused containers require explicit review.

## Consistent backup and fresh recovery

Stop both owned services before backup:

```sh
python -m homelab beszel stop --plan D:/HomeLab-Trials/beszel-plan.json --confirm FULL_PLAN_ID
python -m homelab beszel backup --plan D:/HomeLab-Trials/beszel-plan.json --confirm FULL_PLAN_ID --output D:/HomeLab-Trials/beszel-snapshot
```

The snapshot contains complete **hub and agent data trees**, private account credentials and a manifest containing pinned images, pairing public key, file hashes and semantic database evidence. Compose is reproducibly generated from the reviewed new plan and manifest; retain the matching source release and private original plan too. The hub private SSH key, settings and authentication records are included in the hub tree. Files are permission-checked and SQLite validation requires the exact synthetic account/system, no configured alerts and nonempty owned metric history.

Only stopped, checkpointed snapshots are supported. Validation uses SQLite's [immutable read-only connection](https://www.sqlite.org/uri.html) to avoid creating WAL/shared-memory sidecars. Nonempty WAL or rollback-journal files are refused rather than silently discarded. Do not delete those files to bypass the guard; investigate why shutdown did not checkpoint, and make a new snapshot. Validation is not a repair operation.

**Snapshots are unencrypted and contain credentials and private keys.** Owner-private files protect against ordinary other users, not the owner, Docker administrators or privileged tampering. Hashes detect accidental drift, not replacement of both manifest and data. Encrypted off-host disaster recovery is a later milestone. Never publish or upload a snapshot to CI.

```sh
python -m homelab beszel plan --root D:/HomeLab-Trials/beszel-restored --port 18091 --restore-backup D:/HomeLab-Trials/beszel-snapshot --output D:/HomeLab-Trials/beszel-restore-plan.json
python -m homelab beszel up --plan D:/HomeLab-Trials/beszel-restore-plan.json --confirm RESTORE_PLAN_ID
python -m homelab beszel inspect-metrics --plan D:/HomeLab-Trials/beszel-restore-plan.json
```

Recovery creates a fresh project and two new volumes, copies both trees into **never-started** containers and then starts them. It does not re-seed missing records. Sign in at `http://127.0.0.1:18091/` using the preserved credentials; verify the original system, history and new readings. Compare saved content, not just record counts or HTTP 200. Upstream retention can aggregate older records over time, so compare promptly and account for retention before diagnosing later differences.

The backup reports `recovery_verified: false`; only a separate content/UI rehearsal establishes recovery evidence. Its original manifest remains unchanged. Keep the source snapshot unchanged and available: **every operation on a recovery plan revalidates it**, including stop/removal. This conservative prerelease dependency is not a general restore-management design. Only adapter-generated synthetic state is supported; this is not a tool for importing a live Beszel database or certifying arbitrary manually changed settings.

## Cleanup, interruptions and updates

```sh
python -m homelab beszel stop --plan D:/HomeLab-Trials/beszel-plan.json --confirm FULL_PLAN_ID
python -m homelab beszel remove --plan D:/HomeLab-Trials/beszel-plan.json --confirm FULL_PLAN_ID
```

Repeat against the restore plan with its own hash. Only the exact stopped owned containers and network are removed. **Both data volumes, private files and snapshots remain recoverable.** No volume-deletion command exists; a removed installation needs a new recovery root to run again.

- Partial initialization, unowned name collisions, foreign attachments, missing recorded resources or `.pending-*` files fail closed. Retain evidence; do not force adoption or reset files to get past a guard.
- Interrupted pairing between Compose and state publication requires manual review. If both files agree on `pairing`, `seed` can finish creation/start, but an orphaned agent volume without its container is refused.
- Interrupted restore stays `restore-copying`. Preserve it, investigate and use a fresh target; there is no unsafe automatic replay into partially copied state.
- `status` intentionally reports `requires-application-verification`; use authenticated metrics and rendered charts to establish health.
- Native Windows services/GPU, Docker inventory, same/new-origin email tests, upgrades/migrations/rollback, encrypted backups, Linux/macOS live runtime, ARM64 and clean-machine recovery remain out of scope.

Upstream references: [pinned source](https://github.com/henrygd/beszel/tree/v0.21.0), [agent installation](https://www.beszel.dev/guide/agent-installation), [environment options](https://www.beszel.dev/guide/environment-variables), [advanced deployment](https://www.beszel.dev/guide/advanced-deployment). Digest pinning provides reproducibility, not vulnerability certification. No third-party source or reference-homelab patch is copied into this module.
