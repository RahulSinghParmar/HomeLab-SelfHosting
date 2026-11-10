# Jellyfin application-aware recovery trial

Version 0.7.0-alpha.5 adds a disposable native-Windows recovery rehearsal for Jellyfin 12.4. It creates only generated credentials, an isolated application state and a one-second synthetic MP4. It does not authenticate to, stop, back up, restore or otherwise change the production server.

## What the trial proves

The trial performs the following sequence on a non-production loopback port:

1. generate a small MP4 with the installed Jellyfin FFmpeg;
2. initialize an isolated Jellyfin 12.4 source instance;
3. create one synthetic administrator and one synthetic movie library;
4. retrieve the fixture through Jellyfin's static video stream endpoint and compare exact bytes;
5. create Jellyfin's built-in database, configuration, metadata, subtitle and trickplay archive;
6. verify the ZIP and required Jellyfin 12 JSON database exports;
7. stop the source and delete its complete application state;
8. initialize an unrelated clean target with the same Jellyfin version;
9. restore the archive with `--restore-archive`;
10. authenticate with the restored identity and repeat exact direct play;
11. stop and restart the restored instance, then repeat exact direct play again; and
12. save sanitized evidence outside the disposable root and remove successful trial state.

The target initialization is required because Jellyfin 12's restore engine imports JSON table exports into a matching initialized database schema. The setup flow also follows the installed 12.4 web client's `GET /Startup/User` then `POST /Startup/User` sequence.

## Media boundary

Jellyfin's built-in archive contains application state and media path mappings. It does **not** contain media originals. The synthetic MP4 therefore remains in separate owner-managed storage while the source application state is deleted. Successful restored direct play proves that the restored database, user, library and media mapping resolve the separately protected bytes.

For production, protect media files with an independent storage backup and restore them to compatible paths before validating Jellyfin playback. Do not treat a Jellyfin ZIP as a media backup.

## Run on Windows

Use a root that does not exist, an evidence file that does not exist, a non-production port, and the matching installed Jellyfin binary/web/FFmpeg set. PowerShell example:

```powershell
python tools/jellyfin_native_trial.py `
  --root C:\Homelab-Trials\jellyfin-recovery `
  --output C:\Homelab-Evidence\jellyfin-recovery.json `
  --binary "$env:ProgramFiles\Jellyfin\Server\jellyfin.exe" `
  --web "$env:ProgramFiles\Jellyfin\Server\jellyfin-web" `
  --ffmpeg "$env:ProgramFiles\Jellyfin\Server\ffmpeg.exe" `
  --port 18096 `
  --confirm RUN-ISOLATED-JELLYFIN-TRIAL
```

The tool rejects port 8096, overlapping evidence/state paths, pre-existing trial state and a missing explicit confirmation. It binds the disposable instance to `127.0.0.1`, disables remote access and starts child processes without a visible console window.

Failed runs retain their disposable state and logs for diagnosis. A successful run removes the disposable root unless `--keep` is deliberately supplied. The evidence file remains outside that root.

## Validate evidence

```powershell
python -m homelab jellyfin validate-recovery `
  --evidence C:\Homelab-Evidence\jellyfin-recovery.json
```

The validator requires:

- the reviewed Jellyfin 12.4 and recovery contracts;
- a valid built-in archive with database exports, manifest/config evidence and all selected options;
- source, restored and post-restart HTTP 200 `video/mp4` responses whose size and SHA-256 exactly match the fixture;
- source-state deletion before restore and fresh same-version target initialization;
- restart persistence; and
- explicit false values for production service/media/credential use, GPU use, transcoding and retained synthetic credentials.

## Still outside this milestone

- production backup adoption or scheduling;
- encrypted off-host Jellyfin application archives or media replicas;
- representative production-data recovery;
- client, concurrency or remote-access playback testing;
- any transcoding or GPU enablement; and
- native service installation, conversion or upgrade automation.

See the [reference validation](validation/jellyfin-recovery.md) and [upstream backup/restore guide](https://jellyfin.org/docs/general/administration/backup-and-restore/).
