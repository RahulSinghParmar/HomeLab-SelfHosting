# Docker update manager

The Docker update manager separates **checking**, **approval** and **deployment**. It never updates every running container automatically.

## Safety model

- `audit` inventories Compose projects and optionally compares running image digests with registries. It does not pull or restart anything.
- `inspect-remote` reports the remote digest and OCI version metadata for one proposed image.
- `plan` binds one audited project and service to one exact version tag or digest. Rolling tags such as `latest`, `stable` and `nightly` are refused.
- `apply` requires the full plan ID, verifies that the Compose file and running image have not changed, pulls only the approved target, stops only the selected service, copies only its reviewed backup paths, changes one simple `image:` field, validates Compose, recreates that service and waits for health.
- Controller-managed projects, unknown projects, local builds, databases without an application-consistent backup rule and multi-file Compose projects remain audit-only.

An unhealthy updated service is left in place for operator diagnosis and its recovery set is retained. The tool does not automatically downgrade or delete the container after a possible data migration. Restore the application backup and original Compose file together after reviewing the recovery journal.

## Workflow

Copy and edit [`modules/docker-updates/policy.example.json`](../modules/docker-updates/policy.example.json) outside Git. Only enable services with a reviewed application-consistent backup path and health check.

```powershell
python homelab_cli.py docker-updates audit `
  --policy C:\Docker\maintenance\update-policy.json `
  --online `
  --output C:\Docker\maintenance\reports\update-audit.json

python homelab_cli.py docker-updates inspect-remote `
  --image ghcr.io/example/app:v1.2.3

python homelab_cli.py docker-updates plan `
  --policy C:\Docker\maintenance\update-policy.json `
  --audit C:\Docker\maintenance\reports\update-audit.json `
  --project example-stack `
  --service example-app `
  --target-image ghcr.io/example/app:v1.2.3 `
  --output C:\Docker\maintenance\plans\example-app-v1.2.3.json

python homelab_cli.py docker-updates apply `
  --plan C:\Docker\maintenance\plans\example-app-v1.2.3.json `
  --confirm <full-plan-id>
```

Read release notes and application migration guidance before planning an update. Database major-version changes and controller-managed applications must use their own supported updater and recovery process.
