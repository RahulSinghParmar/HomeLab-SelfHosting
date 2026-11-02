# Immich application-aware recovery validation

Validated on 2026-11-02 with Windows Docker Desktop, the pinned Immich 3.3.5 release set and two disposable loopback-only projects.

## Application exercise

- All four source services became healthy under their exact image digests and resource limits.
- A new synthetic administrator uploaded `phase6-immich-original.png` through the v3 API.
- The authenticated original-download endpoint returned 70 bytes with SHA-256 `0054b8401f90de27aa1243f1d8e078b113f21137921961b6aa67a35602f60573` and `image/png` content type.
- Machine learning was stopped independently; the same endpoint still returned the exact bytes. ML restarted healthy afterward.
- No Docker socket, external library, public bind or device request was present.

## Consistent backup

- The server and ML services were stopped before capture.
- PostgreSQL remained healthy while `pg_dump --format custom` ran; `pg_restore --list` validated the archive before publication.
- `library`, `upload` and `profile` were copied and hashed.
- Thumbnails, encoded videos, automatic dump contents, Valkey state and ML models were excluded.
- Only the three required derived-directory `.immich` markers were preserved for system-integrity checks.
- The manifest reported four protected files, 109 total protected bytes, and the exact original fixture hash.
- The staging set was plaintext-sensitive and was deleted after the trial.

## Independent restoration

- The restore used a different root, port, Compose project, plan ID, owner label, media bind and three new named volumes.
- The custom PostgreSQL archive and protected directories were restored before the server's first start.
- All source-derived content was excluded; only integrity markers recreated the empty derived directories.
- All four restored services became healthy.
- The restored authenticated API returned the exact original SHA-256.
- A complete stop/start retained the application recovery result and repeated exact-content verification.

## Resource sample

One post-validation idle sample was captured with `docker stats --no-stream`:

| Project | Service | CPU | Memory | PIDs |
| --- | --- | ---: | ---: | ---: |
| Source | Server | 0.08% | 629.3 MiB / 2 GiB | 25 |
| Source | ML | 0.12% | 229.8 MiB / 1.5 GiB | 20 |
| Restored | Server | 0.00% | 739.4 MiB / 2 GiB | 25 |
| Restored | ML | 0.10% | 209.3 MiB / 1.5 GiB | 20 |

This is a single synthetic idle observation, not a production capacity forecast. No ML model was intentionally downloaded or inferred against personal media.

## Defects caught by the recovery gate

The initial validation rejected two implementation defects before release:

1. Compose tokenized the server secret wrapper, causing a clean restart loop. The server command is now one `bash -c` argument.
2. A protected-original-only restore lacked derived-directory integrity markers. The module now preserves only those markers while still excluding derived content.

Both failed disposable projects and their volumes were removed before the successful clean rerun.

## Cleanup and production safety

Both disposable projects, six test volumes, private plans, synthetic media and the sensitive staging backup were removed after validation. The pinned Valkey image remains in the normal Docker image cache. No existing Immich container, production media path, database, account, public route or Docker setting was read or changed.

This evidence supports the bounded local recovery candidate only. Production adoption still requires encrypted off-host recovery, owner storage/key custody, representative-data restore and operational scheduling.
