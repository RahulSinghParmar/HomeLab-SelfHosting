# media-management

Discovery baseline observed 2026-10-03 and refreshed 2026-11-15. Phase 6 now provides an opt-in, digest-pinned renderer and synthetic stopped-state recovery proof. It does not adopt the existing stack.

## Evidence and ownership

- Lifecycle owner: Compose: arr-stack.
- Observed containers assigned to this module: 8.
- Evidence classes: [E01–E06 and scope limits](../discovery/evidence.md).
- Source locators below are relative to the private stack root. `NATIVE/` denotes an OS-managed location resolved in private evidence, not a repository file.

- `arr-stack/docker-compose.yml`
- `arr-stack/backup-arr.ps1`
- `arr-stack/test-stack.ps1`

## Observed configuration

Eight services use floating latest tags. UI ports 8989, 7878, 8686, 9696, 6767, 5055, 8191, 8095; torrent 6881 TCP/UDP.

## Installation and dependencies

Use the [selectable media-management module](../media-management-module.md). Every component is explicit; dependency rules are validated before rendering. The checked-in example selects nothing and cannot deploy by itself. Existing state is never implicitly adopted.

## Configuration mapping

- Reusable after review: Common paths, selective module model and health-check structure.
- Private installation values: Library roots, indexers, credentials, preferences and historical state.
- Manual/platform-specific work: Prove filesystem hardlinks/atomic moves where wanted; initiate no searches/downloads automatically.

## Storage and secrets

Per-app config binds; shared /data for library/download paths; FlareSolverr has anonymous /config volume.

Secret names/purposes only: Per-app API keys and provider/download credentials stored in private application configuration.

Never publish actual values, database records, private keys or generated content. Storage locators and image digests are retained in the private inventory; paths in these runbooks are logical mappings, not commands to copy production data.

## Operations

Use the actual owning Compose project/service or native manager above. Read-only Docker checks are `docker ps -a`, `docker inspect --format '{{.State.Status}}' CONTAINER`, and `docker stats --no-stream`; substitute a verified container, not a guessed generated name. Do not paste unfiltered inspect/log output into public issues.

The public CLI can plan, render and validate evidence. It does not run Compose:

```powershell
python -m homelab media-management plan --selection <private-selection.json> --output <private-plan.json>
python -m homelab media-management render-compose --plan <private-plan.json> --output <private-compose.json>
python -m homelab media-management validate-recovery --plan <private-plan.json> --evidence <private-evidence.json>
```

## Backup and recovery

The existing scheduled ZIP job reports success but only Compress-Archive runs: its freeze-state comment is not implemented; age-based deletion follows without restore verification.

The reusable module's [validation record](../validation/media-management.md) proves stopped-state capture, SQLite checks, shared-filesystem semantics, independent restore and healthy restart with synthetic state. That proof does not certify the current live-copy ZIP job.

## Update and rollback

Capture a consistent backup and required secrets, resolve the exact image/build and configuration inputs, and test the target release against isolated restored state. If database migration is incompatible, roll back the whole consistent state, not only the image. Do not use blanket pull/up commands against a custom or floating build.

## Acceptance checks

Restore synthetic configuration consistently; verify shared-path semantics without scanning/downloading production media.

## Limitations and follow-up

The reference stack still requires a separately approved migration from floating images and broad port bindings. Its live SQLite/config archive and unverified retention remain unsuitable as a recovery certificate. FlareSolverr has no authoritative configuration in the reusable module; its browser scratch space is bounded and disposable.

For upstream links and implementation phase, see the [service catalog](../../catalog/services.json). No third-party application source is copied into this release; see [build provenance](../discovery/build-provenance.md).
