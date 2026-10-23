# Firefly III encrypted recovery vault

Version **0.6.0-alpha.9** adds a separate Restic layer for complete Firefly III staging backups. It accepts only a checksum-valid backup produced by the Firefly III module; it does not discover, adopt or copy the personal deployment.

## Security boundary

- Restic 0.19.1 Windows amd64 and Linux amd64 binaries are accepted only when their executable checksum, version and platform match `modules/firefly-iii/restic.json`.
- The operator supplies the reviewed binary. Nothing is installed globally.
- `key-create` writes one strong value to distinct operational and recovery files in different private directories and never prints it.
- Plans store key paths and the reviewed tool identity, not key material. Inherited `RESTIC_*` variables are removed.
- Repository, state, keys and plaintext staging may not overlap.
- Raw Restic output is hidden on failure because filenames can be sensitive.
- Same-machine encryption is not disaster recovery. The repository and recovery key need independently recoverable storage.

The plaintext Firefly III staging set contains MariaDB content, upload/export trees, configuration and credentials. Keep it outside Git and remove it only after an encrypted restore and application recovery have passed.

## Reviewed tool

Use the matching archive from the [Restic 0.19.1 release](https://github.com/restic/restic/releases/tag/v0.19.1).

```text
Windows amd64 archive:    da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d
Windows amd64 executable: b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830
Linux amd64 archive:      f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c
Linux amd64 executable:   20d4142678d0d95ec11a4759def1b73fd9190abc9ca19e4b62d067c0b387e639
```

macOS and ARM binaries are not certified by this prerelease.

## Local encrypted workflow

Create the parent directories first. Use independent media for a real recovery-key copy.

```powershell
python homelab_cli.py firefly-vault key-create `
  --password-file D:\HomeLab-Private\firefly-operational\password.txt `
  --recovery-key-file E:\HomeLab-Recovery\firefly\password.txt `
  --confirm CREATE-FIREFLY-RECOVERY-KEY

python homelab_cli.py firefly-vault plan `
  --state-root D:\HomeLab-Private\firefly-vault-state `
  --repository E:\HomeLab-Backups\firefly-restic `
  --password-file D:\HomeLab-Private\firefly-operational\password.txt `
  --recovery-key-file E:\HomeLab-Recovery\firefly\password.txt `
  --restic D:\Reviewed-Tools\restic_0.19.1_windows_amd64.exe `
  --output D:\HomeLab-Private\plans\firefly-vault.json

python homelab_cli.py firefly-vault init --plan D:\HomeLab-Private\plans\firefly-vault.json --confirm VAULT_PLAN_ID

python homelab_cli.py firefly-vault snapshot-plan `
  --plan D:\HomeLab-Private\plans\firefly-vault.json `
  --source D:\Firefly-Staging\firefly-backup `
  --output D:\HomeLab-Private\plans\firefly-snapshot.json

python homelab_cli.py firefly-vault store --plan D:\HomeLab-Private\plans\firefly-vault.json --snapshot-plan D:\HomeLab-Private\plans\firefly-snapshot.json --confirm SNAPSHOT_PLAN_ID
python homelab_cli.py firefly-vault check --plan D:\HomeLab-Private\plans\firefly-vault.json --confirm VAULT_PLAN_ID
python homelab_cli.py firefly-vault restore --plan D:\HomeLab-Private\plans\firefly-vault.json --snapshot-plan D:\HomeLab-Private\plans\firefly-snapshot.json --snapshot-id COMPLETE_SNAPSHOT_ID --target D:\Firefly-Restore-Trial\decrypted --confirm SNAPSHOT_PLAN_ID
```

`check` reads every repository data pack. `restore` decrypts into a new private directory, verifies the complete Firefly III manifest and finance fixture and only then adds the protected `recovery-verified` tag. Complete proof requires restoring that directory into a fresh Firefly III project, reading the exact transaction and raw attachment evidence and repeating the check after stop/start.

## Portable off-host recovery

Export a path-independent manifest only after the snapshot passes full-data and application restore checks:

```powershell
python homelab_cli.py firefly-vault portable-manifest --plan D:\HomeLab-Private\plans\firefly-vault.json --snapshot-plan D:\HomeLab-Private\plans\firefly-snapshot.json --snapshot-id COMPLETE_SNAPSHOT_ID --output D:\HomeLab-Private\plans\firefly-portable.json

python homelab_cli.py firefly-vault recovery-plan --repository E:\Recovered-OffHost\repository --recovery-key-file F:\Offline-Key\firefly.txt --restic D:\Reviewed-Tools\restic.exe --manifest E:\Recovered-OffHost\firefly-portable.json --output D:\Private-Recovery\firefly-off-host-plan.json

python homelab_cli.py firefly-vault recover-off-host --plan D:\Private-Recovery\firefly-off-host-plan.json --target D:\Private-Recovery\decrypted --confirm RECOVERY_PLAN_ID
```

The manual `Firefly III off-host recovery rehearsal` workflow transfers only the encrypted synthetic repository and nonsecret portable manifest. A new runner receives its test key independently, checks every data pack, decrypts the exact snapshot, restores Firefly III and repeats exact transaction, attachment and stop/start checks.

## Retention

The declared policy is 7 daily, 4 weekly and 3 monthly snapshots. Preview is read-only. Apply is blocked until the latest snapshot has passed full-data check and verified restore, and preserves the `recovery-verified` snapshot.

```powershell
python homelab_cli.py firefly-vault retention-preview --plan D:\HomeLab-Private\plans\firefly-vault.json
python homelab_cli.py firefly-vault retention-apply --plan D:\HomeLab-Private\plans\firefly-vault.json --confirm VAULT_PLAN_ID
```

This prerelease does not schedule backups, host the user's durable repository, rotate keys, prove a real lost-key event, migrate personal data or replace the production backup process.
