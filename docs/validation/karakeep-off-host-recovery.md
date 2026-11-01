# Karakeep encrypted off-host clean-runner recovery gate

Version: **0.6.0-alpha.13**

Scope: generated non-personal bookmark and asset fixtures only; no household users, personal bookmarks, assets, credentials, settings or database rows

Decision: **Go for the bounded experimental recovery gate only after both clean-runner jobs pass on the exact release commit. No-go for production adoption or backup replacement.**

## Required clean-runner evidence

The manually dispatched `Karakeep off-host recovery rehearsal` workflow is the authoritative Linux amd64 portability gate:

1. **Prepare encrypted off-host artifact** starts a fresh digest-pinned Karakeep project, creates one exact searchable text bookmark and one exact binary asset, renders/searches/downloads them, verifies restart persistence and the supplementary logical export, makes an application-consistent SQLite/assets backup, stores it in a new encrypted Restic repository, reads every repository data pack, locally decrypts it and uploads only the encrypted repository plus a nonsecret portable manifest.
2. **Recover on independent clean runner** downloads that immutable artifact on a new hosted runner, receives `KARAKEEP_DR_TEST_PASSWORD` separately from the repository artifact, independently verifies Restic, checks all data packs, decrypts the exact snapshot, restores a fresh Karakeep project, rebuilds the search index and repeats rendered bookmark, full-text search, exact asset-download and restart-persistence checks.

Artifact upload/download actions and application images use immutable references. The encrypted repository expires after seven days; the sanitized proof expires after thirty days.

## Local Windows rehearsal — 2026-11-01

The complete workflow passed against disposable projects on Windows Docker Desktop before publication. This is implementation evidence, not the authoritative off-host portability gate because the copied repository and recovery-key paths remained on the same physical host.

- application plan: `190c0413a44fa6029b838f3668fedaa255bd20bbba99650048f4c04e1f60ef1b` on loopback port 18064;
- encrypted repository: `e19b9946374a02b7c323ebae04a2ce6f05cbe698b26a3e5ab04ad9b7777cca0c`;
- protected snapshot: `c66c3bc6e6058ba815d5b7ff1c822021ff9046026349d2b1798626c63af2e363`;
- application manifest: `22e0fc69eb63999bcccbe438671821eabe01a27d59a284d75346b27091d10f23`;
- portable manifest: `88f18c435ef5a73273bc1af7fe75fc398847be385934dd03c0bcbf7744b52bed`;
- evidence: two bookmarks, five authoritative data files, 392-byte logical export and a 68-byte asset with SHA-256 `613fe786197ef233bcb1b6d3ab7647c7b3c985889d0d56bca6d28b60e3cfe126`;
- the copied artifact contained seven encrypted/metadata files, no key file, no `db.db` and no `credentials.json`;
- independent-path recovery performed a second full-data check with `source_machine_state_used=false`;
- fresh project `65e010265228821e4ad2c57f69312cbdbb637daef66498fdb8e3696769063bca` on port 18065 rebuilt search, rendered the exact bookmark, downloaded the exact asset and repeated browser validation after restart;
- source/recovered restart screenshots were visually reviewed; SHA-256 values were `4d405bcc23d18ac22d0bbcd105edfab72e16d0f0cda3012e6b9bef395b343394` and `3894f00eb256d979f56553056109dac842ac7aea03df5ac1f804f8753a247d61`;
- retention preview protected the verified snapshot and performed no prune.

One fail-safe was exercised: key generation rejected a file created beneath ordinary inherited Windows ACLs and stopped before creating the second key. The disposable rejected path was removed, private parent directories were created through the repository ACL adapter, and replacement key creation passed without displaying secret material. No permission check was bypassed.

The short post-recovery snapshot observed roughly 304–325 MiB per app, 17–19 MiB per Meilisearch service and 271–314 MiB per Chrome service within their declared ceilings. It is not capacity guidance. Production `karakeep_web` and `karakeep_meilisearch` remained healthy, all three production containers retained their original image identities and restart counts stayed at zero.

## Pass criteria

- source and recovery use separate fresh hosted runners;
- transferred content excludes operational/recovery keys and plaintext backup;
- Restic archive and executable checksums match the reviewed Linux amd64 values;
- repository, snapshot, backup-manifest, bookmark, asset and logical-export fingerprints match;
- a full repository data check precedes decryption;
- the fresh application renders and searches the exact nonempty bookmark, downloads the exact asset and survives restart;
- proof identifies the exact source commit and immutable artifact digest;
- the Windows host and production Karakeep deployment are never contacted.

## Boundary

Passing proves the synthetic repository format, portable manifest, separately injected key and clean-runner application recovery process. It does not provide durable production storage, migrate personal bookmark data, prove the owner's real offline key, test large archives, link rot, tags/lists, browser extensions, multi-user behavior, public access, recovery objectives or the current production schedule.
