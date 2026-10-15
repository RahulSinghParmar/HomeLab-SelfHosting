# Reusable Glance layout and collectors — validation

Validated on Windows Docker Desktop on 2026-10-10 with synthetic data only. The existing production Glance stack was not modified or restarted.

## Completed

- Reviewed the ten-page private dashboard, five host collector families and seven metrics API areas without publishing private values.
- Kept direct application database queries, local credential readers, hard-coded paths/domains and personal statistics outside the reusable module.
- Added a deterministic seven-page `operations` profile with 21 top-level widgets. All custom API widgets are restricted to the internal metrics service.
- Added strict collector configuration, redacted validation output, owner-private atomic snapshots, operation locking, local-Docker refusal, allowlisted container checks, storage/backup freshness, credential-free endpoint/TLS checks and allowlisted Windows service state.
- Added a standard-library, read-only snapshot server with a five-route allowlist, one MiB input cap, schema validation, stale detection, no request logging and no published port in the Compose example.
- Nine focused layout/collector tests passed, including private-value redaction, credentialed-URL refusal, output/storage overlap refusal, remote-Docker refusal, raw command-error suppression, bounded snapshot publication and stale/malformed API behavior.
- The generated layout passed Glance v0.8.6 `config:validate` using the pinned image.
- The exact reusable Compose file ran a disposable dashboard and metrics sidecar on a dedicated bridge with only `127.0.0.1:18181` published. All seven shell routes returned HTTP 200; all seven Glance `/api/pages/<slug>/content/` fragments contained expected content with zero widget error headers.
- The internal overview was fresh and reported four of four healthy synthetic sections. Recent container logs contained no panic/fatal/error/failed matches.
- Final point-in-time Compose sample: dashboard 11.51 MiB / 128 MiB at 0.02% CPU and five PIDs; metrics sidecar 11.45 MiB / 64 MiB at 0.01% CPU and one PID. Both were healthy, read-only, unprivileged, no-new-privileges, `cap_drop: ALL`, running and not OOM-killed. The sidecar had no published ports.
- The two disposable containers and dedicated network were removed. Port 18181 had no remaining listener. Private synthetic configuration and snapshots were retained outside Git as validation evidence.

## Pending

- Cross-platform live Docker trials on Linux/macOS and ARM64.
- A reviewed private collector configuration for this production host; the public example is intentionally synthetic.
- Scheduled sampling and reboot persistence on each declared platform.
- Visual screenshot review was unavailable because the computer-use helper failed with `helper_unknown_error`; Glance's rendered fragment endpoints were verified instead.
- Migration of any selected private application-specific adapters, public deployment and rollback rehearsal.

These pending items prevent declaring the private production dashboard migrated or Phase 4 complete.
