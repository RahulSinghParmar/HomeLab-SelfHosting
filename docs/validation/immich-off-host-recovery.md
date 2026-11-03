# Immich encrypted off-host recovery validation

Date: 2026-11-03

Candidate: `0.7.0-alpha.3`

## Decision

**Go for the bounded encrypted off-host recovery prerelease. No-go for production adoption.**

The validation uses generated non-personal PNG content only. It does not read the existing Immich library, use production credentials, change production storage or alter production backup settings.

## Local Windows evidence

The disposable Windows Docker Desktop rehearsal used Restic 0.19.1 Windows amd64 with the reviewed executable SHA-256 `b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830`.

The source application uploaded and downloaded exact synthetic original SHA-256 `0054b8401f90de27aa1243f1d8e078b113f21137921961b6aa67a35602f60573`. Its application-consistent PostgreSQL/protected-original set was encrypted, restored locally, checked using `restic check --read-data`, decrypted again without using vault state, and restored into a different Immich project. The application returned the same original after initial recovery and after a complete stop/start.

The portable manifest recorded 109 protected bytes, no derived media and no ML model cache. Retention ran in preview mode only. Both key files and the repository were disposable and local, so this rehearsal by itself does not prove different-device storage or offline key custody.

During an earlier attempt, Docker Desktop's Linux engine stopped while production plus two disposable Immich stacks overlapped. Docker Desktop was restarted, production Immich returned healthy, and the rehearsal was changed to remove its source stack before recovered-stack startup. The corrected run passed with production plus at most one disposable stack active.

## Independent clean-runner contract

The manual `Immich off-host recovery rehearsal` workflow uses two GitHub-hosted Linux amd64 runners:

1. The first creates the synthetic Immich backup, encrypts it, performs a complete repository-data read, verifies a local decryption and uploads only the encrypted repository plus nonsecret portable manifest.
2. The second downloads that immutable artifact, installs the independently checksum-verified Restic binary, receives the recovery secret separately, performs another complete repository-data read, decrypts the backup and starts a fresh Immich project.
3. Recovery passes only when the exact original is returned through Immich and remains identical after a stop/start.

The release gate requires a successful hosted workflow run at the exact release commit. The resulting proof artifact contains hashes and validation booleans only; it contains no recovery secret, database dump, credentials or original media.

## Security and retention checks

- Plans and state contain key-file references, never key values.
- Repository identity, snapshot ID, manifest digest, summary digest and required tags are bound into the portable manifest.
- Off-host recovery refuses a changed repository, key, tool, manifest or snapshot.
- `RESTIC_*` variables inherited from the environment are removed.
- Retention apply is blocked without a complete data read and a restore-verified protection tag.
- Default retention is 7 daily, 4 weekly and 3 monthly; preview never prunes.

## Remaining gates

- No production repository, schedule, notification route or recovery key was created.
- No representative personal photo/video library, large video, mobile upload or external library was tested.
- Real owner-controlled off-host capacity, replica transport and two offline recovery-key copies remain unverified.
- Recovery-point/recovery-time objectives, power-loss behavior and hardware-loss recovery remain future Phase 9 work.
- GPU acceleration and derivative regeneration remain separate capability-gated work.
