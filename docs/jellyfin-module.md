# Jellyfin explicit deployment-selection module

Version 0.7.0-alpha.4 adds a privacy-bounded Jellyfin audit and requires the deployment owner to select `native` or `container`. It never silently replaces an existing installation and performs no deployment, migration, scan, playback or configuration change.

## Platform decision

| Host | Native | Container | Module decision |
| --- | --- | --- | --- |
| Windows | Supported upstream | Unsupported upstream | Native only |
| macOS | Supported upstream | Unsupported upstream | Native only |
| Linux | Supported upstream | Supported upstream | Owner must choose explicitly |

Jellyfin's container documentation says Windows and macOS containers are unsupported and calls out broken hardware-accelerated transcoding on those hosts. The module therefore rejects that combination instead of producing a Compose file that appears production-ready.

The native choice does not mean every service manager is equally preferred. Jellyfin's Windows installer documentation currently describes service installation as optional and not recommended. An existing service can still be audited and retained without conversion; changing tray/service ownership is a separate migration.

## Read-only audit

```sh
python -m homelab jellyfin audit --port 8096
```

The report contains only:

- host platform;
- native service presence, running and autostart state;
- matching container count and Docker engine operating system;
- local public-API reachability, Jellyfin version and setup completion; and
- the detected deployment type.

It does not enumerate libraries, inspect media, read credentials, expose a server name or call an authenticated API.

## Explicit selection

Native example:

```sh
python -m homelab jellyfin plan \
  --deployment native \
  --port 8096 \
  --output ../private/jellyfin-native-plan.json
```

Linux container example:

```sh
python -m homelab jellyfin plan \
  --deployment container \
  --port 18096 \
  --output ../private/jellyfin-container-plan.json
```

There is no `auto` choice. The plan refuses conflicting native/container ownership, refuses an in-place deployment-type change and remains `disabled-review-only`.

## Linux container rendering

The optional renderer is available only after an explicit Linux container plan. A private media map must use absolute sources, unique `/media/name` targets and read-only mounts. Copy `modules/jellyfin/media.example.json` outside the checkout and replace its example source with the real Linux media path before rendering:

```json
{
  "kind": "homelab-jellyfin-media-map",
  "contract": "jellyfin-explicit-deployment-v1",
  "mounts": [
    {"source": "/srv/media/video", "target": "/media/video", "read_only": true}
  ]
}
```

```sh
python -m homelab jellyfin render-compose \
  --plan ../private/jellyfin-container-plan.json \
  --root /srv/homelab/jellyfin \
  --media ../private/jellyfin-media.json \
  --uid 1000 --gid 1000 \
  --output ../private/jellyfin-compose.json
```

The renderer uses the official Jellyfin 12.4 image by immutable multi-platform digest, loopback-only HTTP, a non-root UID/GID, read-only root filesystem and media, dropped capabilities, no-new-privileges, bounded CPU/RAM/PIDs and no Docker socket or device access. DLNA is deliberately not claimed through the bridged loopback profile.

## Recovery and upgrade boundary

Jellyfin 10.11 and later provide a built-in online backup. The application database is always included and metadata, subtitles and trickplay can be selected. This is the preferred future recovery source for both deployment choices. Media originals remain separately owner-managed; a Jellyfin archive is not a media backup.

Jellyfin applies database migrations and does not provide a downgrade path without restoring a compatible backup. A future lifecycle adapter must therefore create and validate an application backup before any upgrade, retain the exact server version with the manifest and restore into the same version before attempting an upgrade.

This milestone does not create a backup or restore production data. The previous exact playlist repair evidence remains an operational result, not a substitute for complete application recovery testing.

## Acceleration boundary

CPU is the only selected mode. GPU/device access stays absent until a separately approved synthetic-video test proves:

1. the selected native or Linux-container backend is supported;
2. the installed driver and hardware support the required decode and encode codecs;
3. Jellyfin uses `jellyfin-ffmpeg`;
4. a non-personal fixture actually transcodes; and
5. CPU, GPU, memory and output integrity are measured.

The reference Windows host has a GeForce GT 730 with driver 391.35. Jellyfin's current NVIDIA Windows guidance requires driver 522.25 or newer, so GPU acceleration is not eligible there. Merely seeing a GPU or NVIDIA Docker runtime is not evidence of working NVENC/NVDEC.

## Not yet delivered

- No native installation, update, tray/service conversion or service restart.
- No production configuration, library, plugin, user, playlist or media mutation.
- No container pull/start or Windows/macOS container support.
- No synthetic playback/transcode, client compatibility or concurrency evidence.
- No built-in backup creation, independent restore, encryption or off-host recovery.
- No production-adoption or stable Phase 6 claim.

Upstream references:

- [Jellyfin Windows installation](https://jellyfin.org/docs/general/installation/windows/)
- [Jellyfin container installation](https://jellyfin.org/docs/general/installation/container/)
- [Jellyfin backup and restore](https://jellyfin.org/docs/general/administration/backup-and-restore/)
- [Jellyfin hardware acceleration](https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/)
- [Jellyfin NVIDIA acceleration](https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/nvidia/)
