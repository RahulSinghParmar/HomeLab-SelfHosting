# Jellyfin encrypted recovery validation

Validation date: 2026-11-11
Reference platform: Windows, native Jellyfin 12.4.0, Restic 0.19.1

## Result

The isolated rehearsal passed. It used generated credentials and one generated MP4 only; production data was not read.

The sequence proved:

1. Jellyfin indexed and byte-exactly direct-played the synthetic original.
2. Jellyfin created a valid built-in application archive with required JSON database exports and system configuration.
3. The recovery set stored that archive and the owner-managed media original separately and bound both by SHA-256.
4. Restic encrypted the set, restored it locally, added the recovery-verified tag and completed `check --read-data`.
5. The source application state, source media, staging files and operational password file were deleted.
6. Recovery used only the transported encrypted repository, its nonsecret manifest and the independently held recovery key.
7. A second complete repository-data check passed before decryption.
8. The media replica matched the original SHA-256, the application archive restored into a clean same-version target, and HTTP direct play returned the exact original bytes after restore and after restart.

The sanitized proof records all application, media, encryption, restart and production-isolation gates as passed. The live `JellyfinServer` service was `Running`, `Automatic` and `Healthy` before and after the rehearsal. Port 8096, production users, playlists, configuration, media, GPU and transcoding were unchanged.

The successful disposable work, encrypted transport and test-key directories were removed. The sanitized proof was retained outside the repository for local audit.

## Scope boundary

This was a same-machine simulation of independent transport and key custody, not proof that an owner-operated remote disk or cloud repository is configured. It validates the recovery mechanism and destructive source-loss boundary. Physical off-host production storage, real offline key custody, scheduling, retention execution, notifications and representative-library capacity remain owner adoption work.
