# Backup and disaster recovery design

## What must survive hardware failure

1. A known repository release and installation plan.
2. Compatible application images/build instructions and database engine versions.
3. Application-consistent database and file backups.
4. A separately encrypted bundle of required secrets, application keys, and external-identity configuration.
5. Backup decryption credentials available independently of the failed machine.
6. Instructions and tested evidence for restoring actual content.

A GitHub clone supplies only the public blueprint. It does not recover photographs, passwords, conversations, workspaces, or accounts. A backup on the same disk is not sufficient protection against that disk failing.

## Backup contract

Each module must declare authoritative data, derived/rebuildable data, required secrets, consistency method, version dependencies, expected downtime, and verification procedure. Never copy a running database's raw directory and assume the result is consistent.

The coordinator will serialize conflicting operations and use an application-specific quiesce/dump/snapshot sequence. It must restore the application's previous running or paused state even on failure, without starting deliberately stopped services.

Manifests must include application/module versions, database versions/extensions, checksums, completed steps, consistency status, and verification status. A "command completed" backup is not automatically "restore verified".

Retention target: 7 daily, 4 weekly, and 3 monthly recovery points. Define whether tiers reference shared snapshots or independent copies before implementation. Prune only after a complete replacement backup and policy checks; retain the last known restore-verified recovery point. Do not erase older backups during an initial deployment.

Keep encrypted off-host copies, periodically test reading them, and rehearse recovery without the original machine. Backup destinations and keys are private installation configuration.

## Mandatory application details

| Application | Required recovery material |
| --- | --- |
| AFFiNE | PostgreSQL dump, config, storage, compatible release, required secrets |
| Paperless-ngx | Document exporter output, PostgreSQL dump, data/media/export, configuration, required keys |
| Immich | Database with compatible extensions, originals/upload/library/profile as applicable, reviewed full upload storage policy, secrets |
| Nextcloud | Database, data, config, app/custom-image provenance, secrets and any encryption keys |
| Vaultwarden | Verified database backup, attachments/sends, configuration and required keys; exact backend must be discovered |
| Firefly III | Database, uploads where configured, APP_KEY and relevant configuration |
| Matrix | Database, media, server signing keys and unchanged server identity; client E2EE recovery keys handled separately |
| code-server | Workspaces, settings/extensions manifests, private SSH/GPG material through encrypted recovery—not Git |
| Coolify | Database, APP_KEY and other required secrets, SSH keys, actual configuration sources and managed project data |
| Monitoring | Configuration, monitoring database/history if desired, notification secrets, native task definitions |

Immich database backups do not contain the original photographs and videos; both database and asset storage must be addressed. [Immich backup and restore](https://docs.immich.app/administration/backup-and-restore/).

Paperless offers a document exporter/importer for portable document and metadata recovery. Retain its output alongside the declared database/file recovery set; choose one documented restore path rather than blindly mixing imports and raw database restoration. [Paperless administration](https://docs.paperless-ngx.com/administration/).

## Restore rehearsal

Use a temporary project with unique names, separate data paths, loopback-only ports, and no production credentials or external registration. Disable outgoing mail, notifications, scheduled imports, federation, tunnels, and background jobs that could affect real users. Consider outbound-network isolation in addition to settings.

Restore pinned compatible versions first. Verify database integrity and real content: open a PDF, view an image, read a workspace document, and compare expected metadata/checksums. Health endpoints alone are insufficient. Record elapsed time and actual recovery point; do not promise zero data loss without measured continuous replication.

Never destroy the temporary environment until evidence is captured and exact owned resources are identified. Never use a broad prune operation or delete production volumes to prepare a test.

## Upgrade and rollback

```text
verified backup -> validate reviewed plan -> verify/pull pinned images
-> maintenance/quiesce -> migrate -> health + content checks -> accept
                                              |
                                           failure
                                              |
                    app-specific rollback or full consistent restore
```

Pulling an old image is not sufficient after an incompatible database migration. Restore all coupled data from the same consistent recovery point. Explain downtime and obtain approval before performing recovery on a live service.
