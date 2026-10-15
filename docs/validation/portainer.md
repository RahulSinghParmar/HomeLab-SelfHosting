# Portainer isolated-control validation

Validation date: 2026-10-15. Host: Windows Docker Desktop, Linux containers, `amd64`.

## Scope

The trial tested the `portainer-isolated-control-v4` contract using Portainer CE 2.39.8 and Docker-in-Docker 29.9.0. It did not mount the host Docker socket, expose the nested engine, import production configuration or mutate the existing `portainer` container.

Source and recovery trials used private roots outside Git and loopback HTTPS ports 19443 and 19444. All trial containers, networks, volumes, plans, credentials and backup files were removed after evidence was recorded.

## Results

| Gate | Result |
| --- | --- |
| Exact explicit grant | `isolated-engine-only` required; other values refused |
| Ownership and drift | Image, command, privileges, mounts, limits, ports, networks, health and labels checked |
| Host engine access | Absent; no host socket, device or host path |
| Portainer HTTPS | Running on `127.0.0.1:19443`; HTTP disabled |
| Endpoint registration | Exactly one `tcp://engine:2375` endpoint |
| Real control exercise | Network create, inspect, delete and post-delete 404 passed |
| Outer resources visible | No |
| Synthetic resource retained | No |
| Encryption secret | Private read-only secret present; no missing-key startup warning |
| Stopped backup | Passed; 6 files, 66,925 bytes, nonempty `portainer.edb` |
| Independent restore | Passed on port 19444 with successful authentication and repeated control exercise |
| Cleanup | No trial-labeled container, network or volume remained |

The backup content fingerprint was `25d10dd09119e191cf26159225890d5769229908097cf5012c1ba5de441cee96`. It is evidence for this disposable snapshot only, not a reusable expected value.

One idle sample after the control exercise showed:

| Service | CPU | Memory | PIDs |
| --- | ---: | ---: | ---: |
| Portainer | 0.00% | 18.64 MiB / 256 MiB | 5 |
| Nested engine | 0.15% | 18.28 MiB / 512 MiB | 15 |

The resource ceilings are limits, not reservations. The nested engine briefly used more CPU during startup and API exercise.

## Defects found and corrected

1. A loopback URL with a non-default port was rejected by Portainer's `--trusted-origins` parser. The override was unnecessary for direct same-origin HTTPS and was removed; no wildcard was substituted.
2. `--compact-db` prevented initialization of a fresh volume because there was no database to compact. It was removed from normal startup.
3. The initial backup gate expected the historical `portainer.db`; the pinned 2.39.8 image produced `portainer.edb`. The gate now requires the actual nonempty database.
4. Startup initially warned that no database encryption key was present. A generated private encryption secret was added to deployment, integrity checks, backup and recovery.

## Existing deployment observation

The existing `portainer` container remained running on `portainer/portainer-ce:2.39.6`, with host ports 9090 and 9443 and its pre-existing writable Docker proxy socket. It was not restarted, reconfigured or upgraded.

The existing image is behind 2.39.8. Upstream 2.39.7 included a critical Docker-proxy authorization fix, so production should receive a separate approved update only after its own `/data` backup and fresh restore rehearsal. This candidate does not authorize that change.

## Not certified

- host-engine or remote-agent control;
- public/reverse-proxy access, trusted-origin behavior or external TLS;
- real workload deployment, persistence or backup;
- Portainer RBAC for untrusted administrators;
- production upgrade/migration or rollback;
- Linux/macOS host runtime evidence;
- encrypted off-host backup retention.

The optional module remains an isolated Phase 4 candidate until release packaging and the remaining platform evidence are complete.
