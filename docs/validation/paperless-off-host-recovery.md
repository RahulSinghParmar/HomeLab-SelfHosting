# Paperless off-host clean-runner recovery gate

Version: **0.6.0-alpha.3**

Scope: generated non-personal PDF only; no household Paperless data or credentials

## Required release evidence

The manually dispatched `Paperless off-host recovery rehearsal` workflow is the authoritative live gate for this prerelease. It must complete both jobs on the exact release commit:

1. **Prepare encrypted off-host artifact** creates a new digest-pinned Paperless deployment, imports one generated PDF, verifies searchable text and metadata, creates an application-consistent backup, stores it in a new encrypted Restic repository, runs `check --read-data`, decrypts it locally, and uploads only the encrypted repository plus nonsecret portable manifest.
2. **Recover on independent clean runner** downloads that immutable artifact on a new Linux amd64 runner, receives the synthetic recovery password separately from the `PAPERLESS_DR_TEST_PASSWORD` repository secret, verifies Restic independently, repeats `check --read-data`, decrypts the exact snapshot, imports it into a new Paperless project, and verifies content equality after a complete stop/start.

The artifact upload and download actions are pinned to immutable revisions. GitHub reports and validates the immutable artifact SHA-256 during transfer. The encrypted repository artifact expires after seven days; the sanitized proof artifact expires after thirty days.

## Pass criteria

- Source and recovery jobs use different fresh hosted runners.
- The transferred artifact contains an encrypted Restic repository and portable recovery manifest, but no operational or recovery key.
- The recovery key comes only from the repository Actions secret and is never printed.
- Both Restic archive and executable hashes match the reviewed Linux amd64 values.
- Repository identity, snapshot identity, required tags, Paperless manifest identity and semantic summary identity match.
- The clean runner completes a full repository data check before restore.
- The restored Paperless application contains the expected nonempty synthetic document and survives stop/start.
- The proof identifies the exact source commit and immutable artifact digest.
- The existing Windows host and production Paperless deployment are not contacted.

## Boundary

Passing this gate proves that the repository format, portable manifest, independently injected key and clean-runner recovery process work with synthetic data. It does not provide durable production storage, migrate personal documents, prove the user's real offline key, validate API-token recovery, establish recovery-time objectives or replace the existing production backup schedule.
