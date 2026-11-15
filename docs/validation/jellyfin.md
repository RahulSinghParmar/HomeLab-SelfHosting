# Jellyfin deployment-selection validation

Validated on 2026-11-09 against the public 0.7.0-alpha.4 source and the reference Windows host.

## Reference-host evidence

- The audit detected the native `JellyfinServer` Windows service.
- The service was running and configured for automatic startup.
- The unauthenticated loopback public API reported Jellyfin 12.4.0 with initial setup complete.
- No matching Jellyfin container was present.
- Docker Desktop exposed a Linux engine, but the module still rejected Windows container selection because that deployment is unsupported upstream.
- The audit did not enumerate a library, inspect media, authenticate, read a credential or mutate the service.

The correct reviewed selection for this host is therefore `native`, adopting the existing installation without conversion.

## Image and rendering evidence

- `docker.io/jellyfin/jellyfin:12.4` resolved to immutable multi-platform digest `sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771`.
- The manifest contained Linux amd64 and arm64 images; it was queried but not pulled or started.
- Focused tests proved that Windows/macOS container plans fail closed, Linux requires an explicit container selection and a Linux engine, and no `auto` selection exists.
- The Linux Compose renderer binds HTTP to loopback, uses read-only media, enforces a non-root UID/GID and resource/security limits, and contains no Docker socket, privileged flag, GPU device or device request.

## Acceleration result

The alpha.4 review queried only the GeForce GT 730 path. Driver 391.35 was below Jellyfin's Windows NVENC requirement, so that backend stayed blocked and no device access was granted by the deployment plan. The later [Jellyfin acceleration validation](jellyfin-acceleration.md) separately audits Intel UHD 730 and proves QSV with generated video while retaining CPU fallback.

## Safety result

No native service, container, database, configuration, plugin, account, playlist, library, media file, playback session, Docker setting or GPU setting was changed. The module remains non-activating.

## Remaining gates

- The nonempty built-in backup, same-version independent restore, synthetic direct play and restart-persistence gates subsequently passed in [0.7.0-alpha.5 validation](jellyfin-recovery.md).
- The bounded CPU/QSV workload and two-stream measurement subsequently passed in [0.7.0 validation](jellyfin-acceleration.md).
- Representative production clients, HDR/low-power paths and higher concurrency remain installation-specific gates.
- Encrypted synthetic off-host recovery subsequently passed; owner storage and scheduling remain required before production-adoption claims.
