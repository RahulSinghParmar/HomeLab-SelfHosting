# Coolify existing-instance adapter

This Phase 7 adapter reviews the existing Coolify installation on Windows Docker Desktop. It does not install Coolify, merge its generated resources into a new Compose project, or take ownership of deployments created through the Coolify UI.

Coolify documents Linux as the supported self-hosted server platform. The reviewed Windows topology is therefore an experimental home-lab integration, not a supported high-availability production host. See the [Coolify self-hosted installation requirements](https://coolify.io/docs/start-with-self-hosted) and [instance update guidance](https://coolify.io/docs/core/instance-management/update).

The separate [Coolify controller integration](coolify-controller.md) now provides stable-channel discovery, Windows compatibility checks and a central owner handoff. It still has no update apply operation.

## Ownership model

| Components | Lifecycle owner |
| --- | --- |
| Dashboard, PostgreSQL, Redis, realtime and testing host | Root `C:\Docker\coolify` Compose project |
| Traefik proxy | Coolify-generated proxy Compose project |
| Sentinel | Coolify scheduler |
| Deployed applications and databases | Their Coolify resource and application-specific recovery module |

The testing host, proxy and Sentinel intentionally have Docker control. The audit requires that boundary to be exact and rejects privileged containers or socket access on any other component.

## Read-only workflow

```powershell
python -m homelab coolify audit `
  --policy modules\coolify\policy.example.json `
  --output C:\Private\coolify-audit.json

python -m homelab coolify validate-audit `
  --audit C:\Private\coolify-audit.json

python -m homelab coolify plan `
  --policy modules\coolify\policy.example.json `
  --audit C:\Private\coolify-audit.json `
  --output C:\Private\coolify-plan.json
```

The audit emits only sanitized image, state, health, port, Compose-owner and Docker-socket metadata. It does not read `.env`, `APP_KEY`, credentials, SSH key contents, database rows or application data. The plan is hash-bound to the audit and performs no changes.

## Backup and update boundary

The local owner script captures the Coolify PostgreSQL database, configuration, SSH material and deployment metadata. Those files include secrets and are not encrypted merely because they are called a backup. A same-disk copy protects against some operator mistakes, not disk or machine loss.

Coolify's instance backup does not protect applications, databases or volumes deployed through Coolify. Each workload needs its own application-consistent backup and verified restore. See Coolify's [instance backup](https://coolify.io/docs/core/backup-and-recovery/instance-backup) and [instance restore](https://coolify.io/docs/core/backup-and-recovery/instance-restore) guidance.

Updates remain owner-operated and manual:

1. Confirm there is no active deployment or build.
2. Create a fresh control-plane backup.
3. Verify its encrypted off-host copy and independent recovery key.
4. Review release notes and image availability.
5. Run the existing owner update path.
6. Reapply local resource ceilings and run the full health test.
7. Restore the matching-version database backup if migration fails; do not assume a container-image downgrade can reverse a database migration.

Until step 3 has an actual restore proof, the adapter reports `update_ready: false`.
