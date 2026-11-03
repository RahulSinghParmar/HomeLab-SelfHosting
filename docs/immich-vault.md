# Immich encrypted recovery vault

This optional Phase 6 adapter encrypts one already-verified Immich application backup. It does not read a live library directly, adopt an existing Restic repository, create an owner schedule or change the production Immich deployment.

## Recovery boundary

The vault accepts only the application-consistent format produced by the [Immich recovery module](immich-module.md):

- PostgreSQL custom archive;
- `library`, `upload` and `profile` protected-original content;
- required `.immich` system-integrity markers;
- private recovery credentials and configuration metadata;
- a nonempty fixture whose original bytes were downloaded through the Immich API.

Thumbnails, encoded video, automatic database dumps, Valkey data and the machine-learning model cache remain excluded. Immich requires both its database and uploaded files for comprehensive recovery; it does not reconstruct database state by scanning a library directory.

## Encryption and custody

The adapter accepts only the reviewed Restic 0.19.1 Windows/Linux amd64 executables whose archive and executable SHA-256 values are recorded in `modules/immich/restic.json`. It clears inherited `RESTIC_*` variables and disables the Restic cache.

Two matching private files are referenced:

1. an operational password file available to the backup identity;
2. an independently held recovery-key file used by disaster recovery.

The key value is never returned by the CLI, included in a plan, written to the portable manifest or uploaded with the encrypted repository. A repository copy on another internal drive is not automatically off-host; the owner must place it on a separately identified device or location.

## Workflow

```text
verified Immich recovery set
  -> encrypted Restic snapshot
  -> check --read-data
  -> decrypt and revalidate every manifest/hash
  -> protect the restored snapshot
  -> emit portable nonsecret manifest
  -> recover with repository + separately supplied recovery key
  -> restore into a fresh Immich project
  -> download exact original through the API
  -> stop/start and verify again
```

Retention remains `7 daily / 4 weekly / 3 monthly`. Preview is non-destructive. Apply/prune is confirmation-gated and blocked until the latest snapshot has passed a complete data read and a restore-verified snapshot still carries its protection tag.

## CLI

Create private directories for the operational and recovery copies before generating a key:

```powershell
python homelab_cli.py immich-vault key-create `
  --password-file C:\PrivateHomeLab\immich-operational\password.txt `
  --recovery-key-file E:\OfflineKeys\immich\password.txt `
  --confirm CREATE-IMMICH-RECOVERY-KEY
```

Create and review the plan:

```powershell
python homelab_cli.py immich-vault plan `
  --state-root C:\PrivateHomeLab\immich-vault-state `
  --repository X:\HomeLabBackups\immich-restic `
  --password-file C:\PrivateHomeLab\immich-operational\password.txt `
  --recovery-key-file E:\OfflineKeys\immich\password.txt `
  --restic C:\ReviewedTools\restic.exe `
  --output C:\PrivateHomeLab\immich-vault-plan.json
```

The remaining actions are `init`, `snapshot-plan`, `store`, `check`, `restore`, `portable-manifest`, `recovery-plan`, `recover-off-host`, `status`, `retention-preview` and `retention-apply`. Every mutating action requires the complete deterministic plan or snapshot-plan ID displayed during review.

## Production boundary

Version `0.7.0-alpha.3` validates synthetic encryption and independent recovery. It does not assert that a real off-host repository, two offline key copies, notification route, schedule or representative personal-media restore exists. Those are owner-operated activation decisions and remain separately gated.
