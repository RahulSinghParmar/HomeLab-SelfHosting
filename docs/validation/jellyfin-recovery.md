# Jellyfin application recovery validation

Validated on 2026-11-10 with installed native Jellyfin 12.4.0 and its bundled FFmpeg on the reference Windows host.

## Isolation result

- Production remained a running, automatic `JellyfinServer` service on port 8096 and continued returning `Healthy` before, during and after the rehearsal.
- The trial used loopback port 18096, generated credentials, a one-second synthetic MP4 and separate state under a disposable root.
- No production credential, library, playlist, configuration, plugin or media path was read or changed.
- No production service stop/restart occurred.

## Application backup result

- Jellyfin created its built-in online archive with database, metadata, subtitle and trickplay options enabled.
- The archive used backup engine 0.2.0, contained 46 entries and passed ZIP integrity checking.
- Jellyfin 12 represented database contents as JSON table exports rather than embedding the live SQLite file. Required user, item and user-data exports, `manifest.json` and system configuration were present.
- The complete source application state was stopped and deleted before target recovery.

## Independent restore result

- A fresh unrelated target was initialized with the same Jellyfin 12.4.0 binary so the matching database schema existed.
- `--restore-archive` imported the built-in archive into that target.
- The restored synthetic administrator authenticated successfully.
- The restored movie item and external media mapping were present without re-creating the library.

## Playback and persistence result

- Source direct play returned HTTP 200 `video/mp4` and exactly 11,323 bytes.
- Restored direct play returned the same size and SHA-256.
- After a complete stop/start of the recovered target, direct play again returned the same size and SHA-256.
- The trial requested static direct play only. It did not request transcoding and did not use a GPU.

The sanitized evidence was written outside the disposable root and independently accepted by `python -m homelab jellyfin validate-recovery`. Successful disposable application state was then removed.

## Issues discovered and fixed in the rehearsal

1. Jellyfin 12's startup-user step requires the same GET-then-POST sequence used by the installed web client.
2. The built-in archive contains JSON database exports, not a raw `jellyfin.db` file.
3. Backup creation correctly refuses to run during a media-library scan, so the trial uses one scan and waits for a sustained idle state.
4. A clean restore target must first initialize the matching same-version database schema before importing the archive.

## Decision

The application-aware same-version backup/restore and synthetic direct-play gate passes. This does not yet approve production adoption: encrypted off-host storage, independent media-original backup, owner scheduling, representative recovery, client/concurrency checks and any transcoding/GPU work remain separate gates.
