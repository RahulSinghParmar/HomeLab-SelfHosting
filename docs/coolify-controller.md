# Coolify controller integration

This Phase 7 integration gives the central update tool one safe handoff for the existing Coolify control plane. It discovers upstream stable versions, validates the reviewed Windows Docker Desktop adapter, and produces a fail-closed plan. It does not replace Coolify's own updater, edit generated Compose files, or treat Coolify-managed applications as ordinary local Compose projects.

Coolify supports Linux servers. Running it through Docker Desktop and WSL on Windows remains an experimental existing-instance adapter, not an upstream-supported production topology. A portable deployment should use a Linux host or Linux virtual machine; see the [self-hosted installation requirements](https://coolify.io/docs/start-with-self-hosted).

## Ownership and update route

| Resource | Lifecycle and update owner |
| --- | --- |
| Coolify dashboard, PostgreSQL, Redis and realtime migration | Coolify root project and Coolify dashboard updater |
| Generated Traefik proxy | Coolify controller |
| Sentinel | Coolify controller, with local limits revalidated after recreation |
| Applications and databases deployed by Coolify | Their Coolify resource plus application-specific recovery workflow |
| Other reviewed local Compose projects | Generic Docker update manager only when explicitly enabled |

The generic audit includes a `controller` field. A project marked `controller-managed` is visible but cannot produce a generic apply plan. The operator is redirected to this Coolify controller workflow.

## Central command

On the reviewed Windows host:

```powershell
C:\Docker\maintenance\Manage-HomelabUpdates.ps1 -Action Controller
```

The command writes private, secret-free audit and plan files under the maintenance reports and plans directories. It performs no update. An optional token file can enable the read-only active-deployment gate:

```powershell
C:\Docker\maintenance\Manage-HomelabUpdates.ps1 -Action Controller `
  -ApiTokenFile C:\Private\coolify-api-token.txt
```

The token file is read transiently and its value is never written to an audit. Create a minimum-scope token in Coolify, keep it outside Git and backups intended for publication, and remove it when it is no longer required. Protected API requests require a Bearer token; the controller uses only `GET /deployments` to count active deployments. See the [Coolify API overview](https://coolify.io/docs/api/overview) and [deployments endpoint](https://coolify.io/docs/api/endpoints/deployments/list-deployments).

## Direct CLI workflow

```powershell
python homelab_cli.py coolify controller-audit `
  --policy modules\coolify\controller.example.json `
  --output C:\Private\coolify-controller-audit.json

python homelab_cli.py coolify validate-controller-audit `
  --audit C:\Private\coolify-controller-audit.json

python homelab_cli.py coolify controller-plan `
  --policy modules\coolify\controller.example.json `
  --audit C:\Private\coolify-controller-audit.json `
  --output C:\Private\coolify-controller-plan.json
```

The audit verifies Docker context and engine platform, WSL host-mount access, root health, backup freshness, scheduled-task results and actions, Sentinel limits, the local Windows updater shim, the official stable version feed, and the Soketi-to-Reverb migration boundary. It stores hashes and aggregate states, not secret or application content.

## Update gates

An available release is not an approved update. The plan remains `update_ready: false` unless a future, separately reviewed execution path proves all of these conditions:

1. No active deployment or build is reported by the controller API.
2. A fresh application-consistent Coolify instance backup exists.
3. The backup has an encrypted off-host copy and a successful independent restore.
4. Any crossed migration boundary has been rehearsed on a disposable restore.
5. The current upstream upgrade script still matches the bounded Windows shim anchors.
6. The dashboard, realtime UI, terminal, proxy and a synthetic deployment pass after the update.
7. Sentinel limits are reapplied and verified if the controller recreates it.

The reviewed instance crosses Coolify's 4.6 Soketi-to-Reverb boundary. Coolify documents that the separate realtime container is removed and the realtime ports move to the main container; custom overrides and Cloudflare routing therefore require an isolated rehearsal before update. See the [Reverb migration guide](https://coolify.io/docs/core/instance-management/reverb-migration).

## Recovery boundary

Coolify instance backup protects its control-plane database and required instance material. It does not back up application databases, persistent volumes, or other data belonging to deployed workloads. Preserve `APP_KEY`, and protect each workload with its own tested application-aware recovery module. See the official [instance backup](https://coolify.io/docs/core/backup-and-recovery/instance-backup) and [restore](https://coolify.io/docs/core/backup-and-recovery/instance-restore) guidance.

The controller intentionally has no apply command. When every gate is satisfied, the owner starts the update from Coolify's settings page and follows the [official update workflow](https://coolify.io/docs/core/instance-management/update).
