# Docker update-manager validation

Validation covered offline safety contracts plus a bounded reference-host exercise on Windows Docker Desktop.

## Offline contract

- Exact target tags or immutable digests are required; known rolling tags such as `latest`, `stable`, `main`, `develop` and `nightly` are rejected.
- Target repositories must match the audited running image.
- Plans bind the Compose-file hash, running image ID, service, target, backup paths and health policy.
- Unknown, controller-managed, disabled, multi-file and backup-unprepared services fail closed.
- The image editor changes exactly one simple `image:` field inside the selected service block.
- Apply uses an exclusive service lock, verified stopped backup copy, Compose validation, single-service recreation and retained recovery journal.
- A failure after update startup is not automatically downgraded because an application migration may already have changed persisted data.

## Reference exercise

The sanitized pre-update online audit observed 19 Compose projects and 56 services. It classified 13 images current, 17 immutable-digest pinned, 20 with changed remote digests and six local or registry-unavailable images. One stopped AFFiNE migration container remained correctly visible as a one-shot job rather than being restarted.

The controlled ARR exercise used exact target images and separate recovery sets. Bazarr, Lidarr, qBittorrent and Sonarr received same-application-version LinuxServer build refreshes. Seerr moved to 3.5.2, Prowlarr to 3.0.2.5780 and Radarr to 7.0.3.10918. The final eight-service stack passed its existing HTTP/storage/Jellyfin connectivity audit with zero container restarts; pre-upgrade Prowlarr and Radarr SQLite copies returned `ok`, and post-update logs contained no fatal migration/database matches. The post-update whole-host audit reported 19 current, 17 digest-pinned and three local images; 14 additional tagged images remained intentionally gated and three registry checks were unavailable.

This evidence does not authorize unattended updates or extend update readiness to other personal stacks. Their application-consistent backup and restore hooks remain separate gates.
