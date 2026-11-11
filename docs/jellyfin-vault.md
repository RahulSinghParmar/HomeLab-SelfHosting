# Jellyfin encrypted application and media recovery

Version 0.7.0-alpha.6 adds a bounded recovery contract around the application-aware Jellyfin archive introduced in alpha.5. It protects two intentionally separate materials:

- **Application state:** Jellyfin's built-in ZIP containing the database exports, server configuration, metadata, subtitles and trickplay selected by the backup request.
- **Owner-managed media:** original media files stored outside the Jellyfin archive and replicated by the owner as a separate recovery source.

Jellyfin's archive does not become a media backup simply because it contains library paths. A usable disaster-recovery set needs both materials.

## Encryption and custody

The rehearsal uses Restic 0.19.1 pinned by official archive and executable SHA-256. The operational password file and recovery password file contain the same generated secret but occupy separate custody directories. Only the encrypted repository and a nonsecret portable manifest enter the transport directory.

The portable manifest binds:

- Restic repository and snapshot identities;
- the complete application-archive and media-original SHA-256 values;
- the Jellyfin version and built-in backup engine;
- the verified snapshot tags;
- the time of the complete `restic check --read-data` pass; and
- explicit false values for source-state dependency and key-in-transport.

The recovery set rejects links, hard-linked material, unexpected files, invalid ZIPs, missing Jellyfin database exports and any size or hash difference.

## Validation commands

```powershell
python -m homelab jellyfin-vault validate-set --source C:\private\jellyfin-recovery-set
python -m homelab jellyfin-vault validate-manifest --manifest C:\private\recovery-manifest.json
python -m homelab jellyfin-vault validate-proof --proof C:\private\recovery-proof.json
```

The disposable Windows rehearsal requires explicit paths and confirmation:

```powershell
python tools/jellyfin_offhost_trial.py `
  --work-root C:\private\jellyfin-work `
  --transport-root E:\off-host\jellyfin-transport `
  --key-root F:\offline-key\jellyfin `
  --output C:\private\jellyfin-proof.json `
  --restic C:\reviewed-tools\restic.exe `
  --binary "C:\Program Files\Jellyfin\Server\jellyfin.exe" `
  --web "C:\Program Files\Jellyfin\Server\jellyfin-web" `
  --ffmpeg "C:\Program Files\Jellyfin\Server\ffmpeg.exe" `
  --port 18097 `
  --confirm RUN-ENCRYPTED-OFFHOST-JELLYFIN-TRIAL
```

The tool refuses production port 8096, generates a one-second synthetic MP4 and temporary credentials, and never reads production Jellyfin state or media. On success it removes the disposable plaintext state, encrypted trial repository and test key, retaining only the sanitized proof at the separately supplied output path.

## Owner adoption remains separate

This release validates the mechanism; it does not configure the owner's production media replica, schedule, retention job, notification route or physical/off-site destination. Before production adoption, choose storage that is independent of the server, estimate capacity from real media growth, place the recovery key outside that storage, and perform a non-destructive restore of representative owned media. Retention must remain restore-gated; no snapshot is eligible for pruning until a checked snapshot has recovered successfully.
