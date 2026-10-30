# Vaultwarden encrypted off-host clean-runner recovery gate

Version: **0.6.0-alpha.11**

Scope: generated non-personal vault fixture only; no household users, vault items, attachments, credentials, settings or database rows

Decision: **Go for the bounded experimental recovery gate only after both clean-runner jobs pass on the exact release commit. No-go for production adoption or backup replacement.**

## Required clean-runner evidence

The manually dispatched `Vaultwarden off-host recovery rehearsal` workflow is the authoritative Linux amd64 portability gate:

1. **Prepare encrypted off-host artifact** starts a fresh digest-pinned Vaultwarden project, creates and decrypts one exact secure note in the rendered Web Vault, uploads and downloads one exact attachment, proves independent-session and restart persistence, makes an application-consistent backup, stores it in a new encrypted Restic repository, reads every repository data pack, locally decrypts it and uploads only the encrypted repository plus a nonsecret portable manifest.
2. **Recover on independent clean runner** downloads that immutable artifact on a new hosted runner, receives `VAULTWARDEN_DR_TEST_PASSWORD` separately from the repository artifact, independently verifies Restic, checks all data packs, decrypts the exact snapshot, restores a fresh Vaultwarden project and repeats rendered note decryption, exact attachment download and restart-persistence checks.

Artifact upload/download actions and application images use immutable references. The encrypted repository expires after seven days; the sanitized proof expires after thirty days.

## Pass criteria

- source and recovery use separate fresh hosted runners;
- transferred content excludes operational/recovery keys and plaintext backup;
- Restic archive and executable checksums match the reviewed Linux amd64 values;
- repository, snapshot, backup-manifest, vault-item and attachment fingerprints match;
- a full repository data check precedes decryption;
- the fresh application renders and decrypts the exact nonempty secure note, downloads the exact attachment and survives restart;
- proof identifies the exact source commit and immutable artifact digest;
- the Windows host and production Vaultwarden deployment are never contacted.

## Boundary

Passing proves the synthetic repository format, portable manifest, separately injected key and clean-runner application recovery process. It does not provide durable production storage, migrate personal vault data, prove the owner's real offline key, test organizations, Sends semantics, TOTP/passkeys, native clients, SMTP or public access, establish recovery objectives or replace the current production schedule.
