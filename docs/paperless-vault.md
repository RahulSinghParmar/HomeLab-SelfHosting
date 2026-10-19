# Paperless encrypted recovery vault

Version **0.6.0-alpha.2** adds a separately gated restic layer around the verified Paperless application backup from `0.6.0-alpha.1`. It accepts only a complete backup that passes the module's manifest, permission, checksum and nonempty-content checks. It does not inspect, adopt or back up an existing Paperless deployment automatically.

## Security boundary

- Restic 0.19.1 for Windows amd64 is identified by an official release URL plus reviewed archive and executable SHA-256 values in `modules/paperless-ngx/restic.json`.
- The binary is supplied by the operator. The project does not install it globally or execute an unreviewed version.
- The repository password and recovery copy must be separate absent files in different directories. `key-create` generates one strong value, writes both files exclusively, applies owner-only ACLs and never prints the value.
- Plans contain key-file references and tool checksums, never key material. Inherited `RESTIC_*` variables are removed before every subprocess.
- The encrypted repository, private state, operational key, recovery key and plaintext Paperless backup may not overlap.
- A same-machine repository is encrypted local backup, not disaster recovery. `off_host_verified` remains false until repository media and a recovery key are copied to independently recoverable locations and tested there.
- Raw restic output is hidden on failure because paths and filenames can be sensitive. Private state is operation-locked and binds the exact repository identity.

The plaintext Paperless staging set still contains documents, database content and credentials. Keep it only for the duration of a verified store/restore workflow, then remove it using a reviewed, exact path. Encryption does not make an online repository immune to deletion by a compromised administrator.

## Reviewed tool

Download the Windows amd64 archive from the [restic 0.19.1 release](https://github.com/restic/restic/releases/tag/v0.19.1), verify its archive checksum, extract it, and provide the extracted executable path to the plan command. The adapter independently verifies the executable SHA-256, reported version and `windows/amd64` target each time the plan is validated.

```text
Archive SHA-256:    da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d
Executable SHA-256: b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830
```

No Linux, macOS or ARM restic binary is certified by this prerelease.

## Workflow

Run from the repository root. Replace the example paths with new private locations outside Git. Create the parent directories first; keep the recovery-key directory on a different, removable or otherwise independent device for real recovery.

```powershell
python homelab_cli.py paperless-vault key-create `
  --password-file D:\HomeLab-Private\paperless-operational\password.txt `
  --recovery-key-file E:\HomeLab-Recovery\paperless\password.txt `
  --confirm CREATE-PAPERLESS-RECOVERY-KEY

python homelab_cli.py paperless-vault plan `
  --state-root D:\HomeLab-Private\paperless-vault-state `
  --repository E:\HomeLab-Backups\paperless-restic `
  --password-file D:\HomeLab-Private\paperless-operational\password.txt `
  --recovery-key-file E:\HomeLab-Recovery\paperless\password.txt `
  --restic D:\Reviewed-Tools\restic_0.19.1_windows_amd64.exe `
  --output D:\HomeLab-Private\plans\paperless-vault.json

python homelab_cli.py paperless-vault init --plan D:\HomeLab-Private\plans\paperless-vault.json --confirm VAULT_PLAN_ID
python homelab_cli.py paperless-vault status --plan D:\HomeLab-Private\plans\paperless-vault.json
```

Create the application-consistent staging backup with the `paperless backup` workflow documented in [the Paperless module](paperless-ngx-module.md). Then bind, store, check and restore that exact backup:

```powershell
python homelab_cli.py paperless-vault snapshot-plan `
  --plan D:\HomeLab-Private\plans\paperless-vault.json `
  --source D:\Paperless-Staging\paperless-backup `
  --output D:\HomeLab-Private\plans\paperless-snapshot.json

python homelab_cli.py paperless-vault store `
  --plan D:\HomeLab-Private\plans\paperless-vault.json `
  --snapshot-plan D:\HomeLab-Private\plans\paperless-snapshot.json `
  --confirm SNAPSHOT_PLAN_ID

python homelab_cli.py paperless-vault check `
  --plan D:\HomeLab-Private\plans\paperless-vault.json `
  --confirm VAULT_PLAN_ID

python homelab_cli.py paperless-vault restore `
  --plan D:\HomeLab-Private\plans\paperless-vault.json `
  --snapshot-plan D:\HomeLab-Private\plans\paperless-snapshot.json `
  --snapshot-id COMPLETE_SNAPSHOT_ID `
  --target D:\Paperless-Restore-Trial\decrypted `
  --confirm SNAPSHOT_PLAN_ID
```

`check` binds a complete `--read-data` pass to the latest recorded snapshot. `restore` decrypts to a new absent private directory, revalidates every Paperless backup file and semantic summary, and only then adds the `recovery-verified` tag. Complete recovery proof still requires feeding that decrypted root to a new `paperless plan --restore-backup ...` project and checking the application content.

## Retention

The policy is 7 daily, 4 weekly and 3 monthly snapshots. Retention is blocked until the latest stored snapshot has passed a full repository data check and an encrypted restore has passed. Preview is the default and never prunes:

```powershell
python homelab_cli.py paperless-vault retention-preview --plan D:\HomeLab-Private\plans\paperless-vault.json
```

Apply is a separate confirmation-gated operation and invokes restic forget/prune while preserving the snapshot tagged `recovery-verified`:

```powershell
python homelab_cli.py paperless-vault retention-apply `
  --plan D:\HomeLab-Private\plans\paperless-vault.json `
  --confirm VAULT_PLAN_ID
```

Review the preview, repository capacity and off-host copies before apply. This prerelease validated preview behavior and regression-tested the apply contract; it did not prune the one live validation snapshot.

## Remaining gates

This is an experimental Windows amd64 recovery component. It does not schedule backups, download tools, rotate keys, move a repository off-host, validate removable-media failure, recover a lost operational key from an offline device, back up production data or replace the existing production schedule. Clean-machine and hardware-failure recovery remain Phase 9 work.

Upstream references: [preparing a restic repository](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html), [backup](https://restic.readthedocs.io/en/stable/040_backup.html), [restore](https://restic.readthedocs.io/en/stable/050_restore.html), and [forget/retention](https://restic.readthedocs.io/en/stable/060_forget.html).
