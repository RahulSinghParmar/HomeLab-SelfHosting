# Media-management validation record

This record separates the 2026-11-15 read-only reference-host baseline from the synthetic recovery proof required before Phase 6 can close. Baseline observations are not deployment or restore approval.

## Read-only baseline

The reference `arr-stack` contained eight running components:

- Sonarr 4.0.20.3014;
- Radarr 6.4.4.10685;
- Lidarr 3.1.6.5079;
- Prowlarr 2.7.0.5723;
- Bazarr 1.6.2;
- Seerr 3.5.1;
- FlareSolverr 3.5.2; and
- qBittorrent 5.3.0.

The applications shared one `/data` mapping. All observed Compose references used floating `latest` tags, every UI and torrent port was bound on all host interfaces, only Seerr declared a container health check, and no per-container resource limits were present.

One idle snapshot used approximately 1.39 GiB across the eight containers. FlareSolverr was the largest single consumer at approximately 388 MiB. These values are one-time observations, not capacity guarantees.

The existing backup script did not implement the stated freeze step. It archived live configuration/SQLite trees and then applied age-based deletion without an independent restore. It therefore does not satisfy the repository recovery contract.

## Security finding

A private legacy stack test contained a hard-coded live-looking Jellyfin API token. The value was not printed, copied or committed. It must be revoked by the owner after its active consumer is identified and replaced with a private environment/file-backed value. This finding does not authorize automatic rotation or a production integration change.

## Candidate validation requirements

The reusable module is acceptable only if automated tests prove:

- an empty or unknown component selection fails closed;
- every component is individually selectable and no implicit default exists;
- Bazarr requires Sonarr or Radarr;
- Prowlarr requires at least one library manager;
- FlareSolverr requires Prowlarr;
- qBittorrent and FlareSolverr remain explicit opt-ins;
- UI bindings are loopback-only, FlareSolverr is internal-only and torrent peer ports are absent by default;
- images are immutable digest references;
- one `/data` mapping is preserved across the applications that exchange files;
- resource, PID and log bounds are present;
- no socket, privileged mode, host device, GPU request or secret is rendered; and
- automatic searches, RSS/download initiation, indexers and provider configuration are absent.

## Synthetic recovery requirements

The trial must use an empty disposable root and synthetic data. A passing result requires:

1. selected containers become locally ready without external providers;
2. the applications are stopped before configuration/database capture;
3. every discovered SQLite database passes `PRAGMA quick_check` or an equivalent read-only check;
4. hardlink identity and an atomic rename are proven within the shared filesystem;
5. exact synthetic fixture hashes are recorded before backup;
6. the source is removed and restored into an unrelated empty root;
7. restored applications become ready and exact fixture hashes match;
8. bounded idle resource measurements are recorded; and
9. all trial containers, networks and synthetic files are removed after evidence is saved.

No pass may depend on the reference stack, a real provider, a real download client, a Jellyfin token, a production media path or personal content.

## Completed synthetic proof

Two sequential trials were used to stay within the reference host's 10 GB Docker ceiling:

- video/requests/downloads: Bazarr, Prowlarr, qBittorrent, Radarr, Seerr and Sonarr;
- music/challenge handling: FlareSolverr, Lidarr and Prowlarr.

Their union covers all eight supported components. Both source projects reached healthy state on an internal network, were stopped before capture, restored into unrelated empty roots and reached healthy state again. Twenty-four SQLite checks passed across the source and restored configuration trees. The shared `/data` hardlink, atomic move and restored content hash passed in both trials. No provider, credential, automatic action, external request or production path was used.

The larger six-service rehearsal measured 816.9 MiB total idle memory with a largest component at 242.1 MiB and peak sampled CPU of 0.14%. The three-service rehearsal measured 445.17 MiB total, a largest component at 237.4 MiB and peak sampled CPU of 2.87%. These are bounded snapshots, not guaranteed production capacity figures.

All trial containers and networks were removed. The existing eight production containers were still running after the proof. Sanitized evidence remains outside Git.

## Result

Pass for the reusable selection, rendering and synthetic stopped-state recovery contract. This does not migrate the reference `arr-stack`, certify its current live-copy ZIP job, configure external services or authorize downloads.
