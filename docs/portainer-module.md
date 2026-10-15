# Optional Portainer module

This Phase 4 candidate provides a deliberately bounded Portainer CE control plane. It is useful for validating the Portainer lifecycle, API and recovery workflow without granting the web application control of the host Docker engine.

It is **not** a replacement for an existing Portainer installation and it does not adopt or manage existing workloads.

## Permission boundary

Planning requires this exact, reviewable grant:

```text
isolated-engine-only
```

The resulting deployment has these properties:

- Portainer receives no host Docker socket, host path or device.
- Portainer can control one disposable nested Docker daemon over a private internal network.
- The nested daemon has no published host port and uses ephemeral tmpfs storage.
- The nested daemon is privileged because Docker-in-Docker requires it. This is a real security boundary and is why the module is opt-in, loopback-only and not a production workload engine.
- Host-engine control is intentionally unavailable. A future host-control mode would require a separate permission contract, threat review and dedicated validation.

Authorized Portainer users can effectively control every resource visible to their configured Docker endpoint. Do not treat Portainer application roles as a perfect containment boundary for untrusted administrators.

## Pinned components

The reviewed `linux/amd64` images are pinned by digest in [the image manifest](../modules/portainer/images.json):

- Portainer CE 2.39.8
- Docker-in-Docker 29.9.0

The candidate exposes only self-signed HTTPS on a chosen loopback port. Legacy HTTP 9000 and Edge tunnel 8000 are not published. The database encryption key and initial administrator password are generated into private files and mounted read-only as Compose secrets.

Resource ceilings are:

| Service | Memory | CPU | PIDs |
| --- | ---: | ---: | ---: |
| Portainer | 256 MiB | 0.5 | 128 |
| Nested engine | 512 MiB | 1.0 | 256 |

## Plan and lifecycle

Use an absent root and absent plan path. The grant text is intentionally verbose so Docker-control permission cannot be inferred from merely selecting the module.

```powershell
python -m homelab portainer plan `
  --root C:\Docker\HomeLab-Managed\portainer-isolated `
  --port 19443 `
  --grant-docker-control isolated-engine-only `
  --output C:\Docker\HomeLab-Plans\portainer.json
```

Review the redacted plan and copy its complete `plan_id` into mutating commands:

```powershell
python -m homelab portainer up --plan C:\Docker\HomeLab-Plans\portainer.json --confirm PLAN_ID
python -m homelab portainer status --plan C:\Docker\HomeLab-Plans\portainer.json
python -m homelab portainer exercise --plan C:\Docker\HomeLab-Plans\portainer.json --confirm PLAN_ID
python -m homelab portainer stop --plan C:\Docker\HomeLab-Plans\portainer.json --confirm PLAN_ID
python -m homelab portainer remove --plan C:\Docker\HomeLab-Plans\portainer.json --confirm PLAN_ID
```

`exercise` authenticates through Portainer, verifies that exactly one empty `tcp://engine:2375` endpoint is registered, creates and inspects one labeled network, deletes it, and confirms it is gone. It never targets the outer Docker endpoint.

`remove` deletes owned containers and networks but deliberately retains the Portainer data volume. Deleting that volume is a separate manual data-destruction decision after verifying its exact labels and backup.

## Backup and recovery

Stop both services before backup:

```powershell
python -m homelab portainer backup `
  --plan C:\Docker\HomeLab-Plans\portainer.json `
  --confirm PLAN_ID `
  --output D:\HomeLab-Backups\portainer\2026-10-15
```

The backup contains:

- the complete stopped Portainer `/data` tree, including its nonempty `portainer.edb`;
- the initial administrator credential required by this isolated test deployment;
- the database encryption key;
- a private manifest containing image identities, tree hashes and content evidence.

The backup is **not encrypted** and contains administrator material. Keep it outside Git on owner-only storage, then protect the backup with the repository-wide encrypted/off-host recovery process. It contains Portainer configuration only; it does not back up Docker workloads, volumes or nested-engine state.

Restore only to a fresh root and a different free loopback port:

```powershell
python -m homelab portainer plan `
  --root C:\Docker\HomeLab-Managed\portainer-restored `
  --port 19444 `
  --grant-docker-control isolated-engine-only `
  --restore-backup D:\HomeLab-Backups\portainer\2026-10-15 `
  --output C:\Docker\HomeLab-Plans\portainer-restored.json
```

Run `up`, `status`, and `exercise` against the new plan. Recovery is not accepted until authentication and the bounded create/inspect/delete exercise pass in the fresh project.

## Security and operational notes

- Keep the candidate on loopback. Public exposure, reverse-proxy headers, trusted origins and external certificates are not certified here.
- The self-signed certificate is expected; the module's validator disables certificate verification only for its loopback API probe.
- The private nested-engine TCP API is intentionally non-TLS because only the two owned containers can reach the internal Docker network. It still represents root-equivalent control of that disposable engine.
- Do not use the nested engine for persistent workloads. Its Docker data is ephemeral by design and is excluded from backup.
- `--compact-db` is not a normal startup flag in this module. Database compaction must be a separate stopped-backup maintenance procedure.
- Image updates require a new digest review, a pre-update stopped backup and an independent restore rehearsal. Never update only the image after an incompatible database migration.

See the [Windows Docker Desktop validation record](validation/portainer.md) for current evidence and limitations.
