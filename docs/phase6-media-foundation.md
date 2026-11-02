# Phase 6 media and acceleration foundation

Version 0.7.0-alpha.1 establishes the safety contract used by later Immich, optional media-management and Jellyfin adapters. It performs no deployment, does not read media, and cannot enable a GPU.

## Storage contract

Media state is classified before any lifecycle operation:

| Class | Contents | Recovery rule |
| --- | --- | --- |
| Authoritative | Configuration, database, originals and profile assets | Must be included in an application-consistent backup and verified by content hash after restoration |
| Derived | Thumbnails and encoded video | Rebuildable, but never deleted or mass-regenerated automatically |
| Cache | ML models, search indexes and transcode cache | Excluded from the authoritative recovery set and recreated only by a separately approved job |

The policy rejects moving originals into a derived/cache class. Cleanup remains confirmation-gated. Phase 6 modules must preserve the database together with the originals because Immich stores file paths and metadata in PostgreSQL and does not reconstruct that state by scanning the upload tree.

## Heavy-job policy

Thumbnail generation, OCR, facial recognition, smart search, library scans and video transcoding default to manual. A later isolated module may perform one bounded synthetic job when its test explicitly requires it. It may not trigger work against production media.

## Acceleration gate

CPU is always the fallback. GPU access requires all of the following:

1. A supported host and container runtime.
2. A backend supported by the selected application release.
3. Hardware and driver prerequisites.
4. A disposable synthetic workload that proves the device is actually used.
5. Measured resource behavior and an explicit reviewed plan.

The read-only command is:

```sh
python -m homelab media audit
```

Save a non-activating plan with:

```sh
python -m homelab media plan \
  --policy modules/phase6/media-policy.example.json \
  --output ../private/phase6-media-plan.json
```

The output records only bounded platform, engine, runtime, device and driver facts. It does not contain a host name, account, media path or credential.

## Immich release baseline

The candidate image set is Immich 3.3.5, its matching machine-learning image, the Valkey 9 digest and the exact PostgreSQL 14 VectorChord/pgvecto.rs-compatible digest published in the upstream 3.3.5 Compose file. The manifest is review input for the next milestone; no image is pulled or container started by this foundation.

Upstream references:

- [Immich v3.3.5 releases](https://github.com/immich-app/immich/releases/tag/v3.3.5)
- [Immich Docker Compose installation](https://docs.immich.app/install/docker-compose/)
- [Immich backup and restore](https://docs.immich.app/administration/backup-and-restore/)
- [Hardware-accelerated machine learning](https://docs.immich.app/features/ml-hardware-acceleration/)
- [Hardware transcoding](https://docs.immich.app/features/hardware-transcoding/)
- [NVIDIA legacy compute capability table](https://developer.nvidia.com/cuda/gpus/legacy)

## Not yet delivered

- No Immich Compose adapter, user, upload, album, browser or restore trial.
- No media-management application is selected.
- No Jellyfin lifecycle adapter or playback test.
- No GPU container or hardware transcode test.
- No production path adoption, media scan, thumbnail generation, cleanup or migration.

The next milestone is the isolated Immich application-aware recovery module.
