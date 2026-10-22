# Nextcloud encrypted off-host clean-runner recovery gate

Version: **0.6.0-alpha.7**

Scope: generated non-personal WebDAV fixture only; no household Nextcloud users, files, credentials, shares, settings or database rows

Decision: **Go for the bounded experimental recovery gate only after both clean-runner jobs pass on the exact release commit. No-go for production adoption or backup replacement.**

## Required clean-runner evidence

The manually dispatched `Nextcloud off-host recovery rehearsal` workflow is the authoritative Linux amd64 portability gate:

1. **Prepare encrypted off-host artifact** starts a fresh digest-pinned Nextcloud project, creates and reads an exact WebDAV fixture, exercises cron and restart persistence, makes an application-consistent backup, stores it in a new encrypted Restic repository, reads every repository data pack, locally decrypts it and uploads only the encrypted repository plus a nonsecret portable manifest.
2. **Recover on independent clean runner** downloads that immutable artifact on a new hosted runner, receives `NEXTCLOUD_DR_TEST_PASSWORD` separately from the repository secret, independently verifies Restic, checks all data packs, decrypts the exact snapshot, restores a fresh Nextcloud project and repeats exact WebDAV content and stop/start persistence checks.

Artifact upload/download actions and application images use immutable references. The encrypted repository expires after seven days; the sanitized proof expires after thirty days.

## Pass criteria

- source and recovery use separate fresh hosted runners;
- transferred content excludes operational/recovery keys and plaintext backup;
- Restic archive and executable checksums match the reviewed Linux amd64 values;
- repository, snapshot, backup manifest and WebDAV fixture fingerprints match;
- a full repository data check precedes decryption;
- the fresh application returns the exact nonempty fixture and survives stop/start;
- proof identifies the exact source commit and immutable artifact digest;
- the Windows host and production Nextcloud deployment are never contacted.

## Boundary

Passing proves the synthetic repository format, portable manifest, separately injected key and clean-runner application recovery process. It does not provide durable production storage, migrate personal files, prove the owner's real offline key, test external storage or native clients, establish recovery objectives or replace the current production schedule.
