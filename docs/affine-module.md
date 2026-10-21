# AFFiNE application-aware recovery module

AFFiNE is the second bounded Phase 5 application candidate. This module creates a new isolated deployment for synthetic validation; it does not adopt, inspect, stop, upgrade or copy the existing personal AFFiNE deployment.

## Release boundary

Version `0.6.0-alpha.5` provides:

- AFFiNE `0.27.4`, PostgreSQL with pgvector and Redis pinned by exact image digest;
- a one-shot migration service whose successful exit is expected;
- loopback-only application access and an internal-only database/cache network;
- private generated PostgreSQL, Redis and synthetic administrator credentials;
- disabled public signup, guest access, mail, AI and indexer behavior for the recovery trial;
- explicit CPU, memory, process and log limits without reserving those resources at idle;
- a synthetic Yjs fixture plus a real Chromium-created and rendered AFFiNE note;
- reload and independently authenticated browser-session checks;
- source and recovered restart persistence, application-quiesced backup and independent semantic restore;
- a separately gated encrypted Restic vault and clean-runner recovery workflow.

This is an experimental recovery adapter. It does not enable AFFiNE in the general planner and does not replace the production backup process.

## Resource ceiling

The long-running services are capped at 160 MiB for Redis, 512 MiB for PostgreSQL and 1536 MiB for AFFiNE. The 768 MiB migration job runs only during initialization or restore. These values are ceilings, not permanent RAM reservations. Actual capacity must be measured against representative workspaces before production use.

## Safety model

Every plan binds an absent private installation root, an unprivileged loopback port, the local Docker engine identity and exact image digests. Generated resources carry a unique owner and plan identity. Operations refuse foreign, missing, duplicate, privileged, socket-mounted, incorrectly networked or resource-drifted containers.

The module deliberately provides no Docker socket, host devices, GPU, public hostname, SMTP, OAuth or external AI credentials. The application has a read-only container root where compatible with the upstream runtime, bounded temporary storage, `no-new-privileges`, capped logs and named database/cache volumes. Configuration and AFFiNE storage are private bind mounts under the selected root.

## Operator workflow

Use a new root and plan file outside that root:

```powershell
python -m homelab affine plan --root C:\Docker\homelab-affine-trial --port 18020 --output C:\Docker\homelab-affine-plan.json
python -m homelab affine up --plan C:\Docker\homelab-affine-plan.json --confirm <plan-id>
python -m homelab affine status --plan C:\Docker\homelab-affine-plan.json
python -m homelab affine exercise --plan C:\Docker\homelab-affine-plan.json --confirm <plan-id>
python -m homelab affine backup --plan C:\Docker\homelab-affine-plan.json --output C:\Docker\homelab-affine-backup --confirm <plan-id>
python -m homelab affine stop --plan C:\Docker\homelab-affine-plan.json --confirm <plan-id>
python -m homelab affine remove --plan C:\Docker\homelab-affine-plan.json --confirm <plan-id>
```

The `up`, `exercise`, `backup`, `stop` and `remove` commands require the exact reviewed plan ID printed by `plan`. `remove` removes owned containers and networks but retains state and named volumes. Volume and directory deletion remains an explicit separately reviewed cleanup step.

## Synthetic content exercise

The exercise initializes AFFiNE through its supported self-host administrator endpoint. A digest-pinned Playwright/Chromium runtime then signs in through the rendered UI, creates a synced workspace, creates and edits a note, verifies the rendered title and paragraph, reloads it, and repeats the read through an independent browser context. A separate bounded server-sync fixture records Yjs state through independently authenticated sessions.

The browser runtime is ephemeral, unprivileged, read-only, resource bounded, attached only to the AFFiNE frontend network and has no Docker socket. Screenshot evidence is copied from a self-cleaning anonymous volume through Docker's archive stream and immediately protected with private filesystem permissions. Evidence contains synthetic text, identifiers, checksums and booleans—never credentials or session material.

This proves the declared title/paragraph path in the web editor. It does not prove native desktop/mobile synchronization, attachments, comments, databases, multi-user conflict handling or every editor block type.

## Consistent backup

Backup requires a healthy owned project and completed synthetic evidence. It:

1. verifies the saved semantic fixture;
2. stops the AFFiNE application to quiesce writes;
3. writes and validates a PostgreSQL custom-format dump;
4. copies private configuration and AFFiNE storage;
5. records the private Compose definition and required credentials;
6. emits sanitized configuration metadata, file-tree checksums and a manifest;
7. restarts AFFiNE and verifies the document again.

The resulting staging directory is plaintext-sensitive because it contains database content, private configuration and recovery credentials. Keep it outside Git and public/cloud-synchronized folders. Use the separately reviewed [AFFiNE encrypted vault](affine-vault.md) before copying a recovery set off-host.

## Independent restore

Create a second plan with a different absent root and port:

```powershell
python -m homelab affine plan --root C:\Docker\homelab-affine-restore --port 18021 --output C:\Docker\homelab-affine-restore-plan.json --restore-backup C:\Docker\homelab-affine-backup
python -m homelab affine up --plan C:\Docker\homelab-affine-restore-plan.json --confirm <restore-plan-id>
```

Restore accepts only a complete checksum-valid backup into never-started target resources. It restores PostgreSQL, config and storage, runs the pinned migration, starts AFFiNE, compares server-sync state, renders the saved note through independent browser sessions, restarts the application and repeats both checks. A recovered project may subsequently stop/start without overwriting its prior evidence; each browser run uses a collision-free evidence name.

## Update boundary

Do not change only the AFFiNE image around a migrated database. Create a new reviewed plan, take a consistent recoverable backup, test the target release against an isolated restore, validate migration and content, then decide whether to update production. Image rollback without compatible database/config/storage rollback is not a recovery plan.

## Current no-go items

- production deployment adoption or migration;
- desktop or mobile client synchronization;
- attachments, additional editor block types, public access, SMTP, OAuth, AI and indexer configuration;
- representative multi-user, workspace-size, load or upgrade testing;
- durable owner-operated off-host storage, real offline-key loss recovery and scheduling;
- macOS or ARM64 live runtime certification.

See the [AFFiNE application validation](validation/affine.md), [browser/off-host recovery gate](validation/affine-off-host-recovery.md), [encrypted vault guide](affine-vault.md), the [observed deployment runbook](runbooks/affine.md), and the upstream [self-host Compose definition](https://github.com/toeverything/AFFiNE/blob/canary/.docker/selfhost/compose.yml).
