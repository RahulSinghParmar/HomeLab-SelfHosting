# Selectable media-management module

Phase 6 adds a reusable, deliberately inactive media-management module. It models the applications that were observed in the reference `arr-stack`, but it does not adopt the private stack, copy its databases, configure providers or start a download.

## Selection model

There is no implicit default. Every component must be selected explicitly:

| Component | Purpose | Dependency rule | Reusable exposure |
| --- | --- | --- | --- |
| Sonarr | Series library manager | None | Loopback-only UI |
| Radarr | Film library manager | None | Loopback-only UI |
| Lidarr | Music library manager | None | Loopback-only UI |
| Prowlarr | Indexer manager | At least one of Sonarr, Radarr or Lidarr | Loopback-only UI |
| Bazarr | Subtitle manager | Sonarr or Radarr | Loopback-only UI |
| Seerr | Request interface | None; Jellyfin linking remains private/manual | Loopback-only UI |
| qBittorrent | Download client | Explicit high-impact opt-in | Loopback-only Web UI; peer ports unpublished by default |
| FlareSolverr | Challenge solver | Prowlarr | Internal network only; no host port |

Useful selections can be expressed as profiles, but a profile is only a convenience for review. It must still expand to a visible component list before rendering:

- requests: Seerr;
- video: Sonarr and Radarr;
- music: Lidarr;
- subtitles: Bazarr with Sonarr or Radarr;
- indexers: Prowlarr with a selected library manager;
- downloads: qBittorrent, separately confirmed; and
- challenge solver: FlareSolverr with Prowlarr, separately confirmed.

Selecting an application does not authorize credentials, indexers, download clients, RSS monitoring, automatic search, provider access or a real library scan. Those remain owner-operated application settings after deployment.

## Storage contract

Sonarr, Radarr, Lidarr, Bazarr and qBittorrent use the same container path, `/data`, backed by one owner-selected filesystem. This is required if hardlinks and atomic moves are expected to work; visually similar paths backed by different filesystems do not satisfy that contract.

Each application also has a dedicated persistent configuration directory. Configuration and application databases are authoritative state. Downloads and media libraries are not included in the configuration recovery set and must have a separate owner-managed protection policy.

The renderer does not guess host paths. Copy the example selection outside the checkout and set private absolute roots there. Do not commit real library paths, API keys or provider details.

## Security and resource boundaries

The reusable Compose candidate:

- uses immutable image digests rather than floating `latest` tags;
- binds user interfaces to `127.0.0.1` only;
- leaves FlareSolverr without a published host port and bounds its browser scratch space with `tmpfs`;
- does not publish qBittorrent peer ports unless the owner creates a separately reviewed override;
- has no Docker socket, host devices, privileged mode or GPU request;
- applies CPU, memory, PID and log-rotation bounds;
- uses application-specific persistent configuration and one shared `/data` mapping; and
- contains no account, API key, indexer, provider, download or Jellyfin credential.

FlareSolverr must never be routed directly through a public tunnel or reverse proxy. Its browser process can also be the largest idle consumer in this group, so it stays an explicit optional dependency rather than a default service.

## Planning and rendering

Use the checked-in example only as a schema reference. Store the real selection and generated output in a private directory:

```powershell
python -m homelab media-management plan `
  --selection ..\private\media-management-selection.json `
  --output ..\private\media-management-plan.json

python -m homelab media-management render-compose `
  --plan ..\private\media-management-plan.json `
  --output ..\private\media-management-compose.json
```

Review the plan and Compose output before running Docker. A rendered file is not a deployment approval and does not prove that application integration is complete.

## Recovery proof

The module's trial is disposable and synthetic. It must not be pointed at the reference `arr-stack` or any directory containing personal media. The expected proof is:

1. create synthetic configuration and a shared-path fixture;
2. start only the selected applications in an isolated project/network;
3. verify local readiness without configuring providers;
4. stop the applications before copying SQLite/configuration state;
5. run SQLite integrity checks where an application produced a database;
6. prove that a hardlink and an atomic rename stay on the shared `/data` filesystem;
7. remove the disposable source state;
8. restore into an unrelated empty root;
9. restart and re-check readiness and exact fixture content; and
10. remove the trial project and synthetic data after evidence is written.

Run the trial only with a dedicated empty root:

```powershell
python tools\media_management_trial.py `
  --components sonarr,radarr,prowlarr,bazarr,seerr,qbittorrent `
  --confirm RUN-ISOLATED-MEDIA-MANAGEMENT-TRIAL `
  --output ..\private\media-management-recovery-evidence.json
```

The evidence is acceptable only when it identifies the contract/version, selected components and digests, stopped-state backup, database checks, shared-filesystem proof, independent restore, readiness after restore, resource measurements and successful cleanup. It must not contain credentials, server names, private paths or media titles.

## Existing-stack warning

The read-only baseline found eight running applications using floating images, broad host bindings, limited health checks and no per-container resource ceilings. The existing ZIP task also copies live SQLite/configuration trees despite a comment suggesting a freeze step. This baseline is discovery evidence, not a production recovery certificate.

One private legacy test script was also found to contain a live-looking Jellyfin API token. The token is not part of this module and must never be copied into Git or trial evidence. The owner should revoke it after confirming which current integration uses it, then re-create the integration with a secret supplied through private application configuration. Blind rotation is avoided because it can break a working private integration.

## Upstream guidance

- [LinuxServer Sonarr container guidance](https://docs.linuxserver.io/images/docker-sonarr/) describes the single shared path required for hardlinks and atomic moves.
- [LinuxServer qBittorrent container guidance](https://docs.linuxserver.io/images/docker-qbittorrent/) documents Web UI and peer-port configuration.
- [Seerr Docker installation](https://docs.seerr.dev/getting-started/docker/) documents its persistent application data.
- [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) warns against public exposure and documents its browser-backed service model.

No third-party application source is copied into this repository. The pinned container references remain third-party artifacts and must be reviewed during controlled updates.
