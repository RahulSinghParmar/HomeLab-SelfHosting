# Phase 6 media recovery and acceleration kit

Version 0.7.0 completes the repository's bounded media milestone. It combines three independent modules without turning them into one lifecycle or one database.

## Included

- Immich protects PostgreSQL together with `library`, `upload` and `profile`, separates rebuildable derivatives and model caches, and keeps machine learning independently limited on CPU.
- Media management supports Sonarr, Radarr, Lidarr, Prowlarr, Bazarr, Seerr, FlareSolverr and qBittorrent as individually selected, digest-pinned services. It renders no provider credentials or automatic activity.
- Jellyfin requires explicit native/container ownership, protects its application archive and owner-managed media separately, and validates native Windows Intel QSV through synthetic performance tests with CPU fallback.

The modules share the Phase 6 originals rule: authoritative files and their database/configuration context are protected together; thumbnails, transcode caches, search indexes and model caches are not substitutes for originals.

## Recovery contract

The public kit proves recovery with generated content only:

1. application-consistent state is captured while the relevant services are stopped or quiesced;
2. database/configuration integrity is checked;
3. source state is removed from the rehearsal;
4. recovery occurs in an unrelated root or clean runner;
5. actual content is read again through the application or exact file path contract; and
6. restart persistence and cleanup are verified.

Media-management configuration recovery does not include downloaded or library media. Those remain owner-managed data sets. Jellyfin's application archive likewise does not contain the media originals; its encrypted recovery set binds the two materials separately.

## Acceleration contract

Acceleration is application-specific:

- Immich machine learning remains CPU on the reference host because the installed NVIDIA device/driver does not meet the reviewed CUDA contract.
- Jellyfin Intel QSV is accepted only after CPU, single-QSV and dual-QSV synthetic output passes duration, frame, dimension, quality and real-time checks.
- CPU is always the Jellyfin fallback. NVENC, HDR tone mapping, low-power modes and higher concurrency require separate evidence.

## Production boundary

Stable `0.7.0` describes the versioned public toolkit, not automatic adoption of a private server. It does not migrate existing application databases, enable downloads, configure indexers, choose physical off-host storage, schedule production backups, rotate private credentials or certify a representative personal media library.

See the [Phase 6 closure record](validation/phase6-closure.md), [media-management module](media-management-module.md), [Jellyfin acceleration module](jellyfin-acceleration-module.md) and [release review](releases/v0.7.0.md).
