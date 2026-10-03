# Doctor, wizard and deployment planning

The Phase 2 commands described here provide application planning, **not an installer**. All 21 catalog modules remain planned. Application review plans have `execution_allowed: false` and an empty `deployment_operations` array. These planning commands do not pull images, start/stop containers, write Compose files, change system settings or generate credentials. Version 0.4.0's separately gated [sandbox commands](safe-execution.md) can create private synthetic files and a test credential; application plans cannot be executed by that interface.

## Quick start

Install Python 3.12+ yourself if needed, review the repository, then run these commands from its root. No Python packages or administrator shell are required for offline planning.

```sh
python -m homelab --version
python -m homelab catalog
python -m homelab validate --config examples/windows.settings.example.json
python -m homelab plan --config examples/windows.settings.example.json
```

Use `examples/linux.settings.example.json` or `examples/macos.settings.example.json` for those targets. Examples are illustrative, not your installation settings. The Windows example intentionally uses dedicated D:/E: paths that may not exist. Offline validation checks intent, not actual drives. The older `*.plan.example.json` files are historical design fixtures and are rejected by the CLI.

`./bootstrap.ps1` on Windows or `sh ./bootstrap.sh` on Linux/macOS accepts the same arguments as `python -m homelab`. Launchers do not install Python, elevate, change execution policy, or change the current directory. If your policy blocks PowerShell scripts, use the Python entry point rather than weakening the policy. Outside the checkout, invoke `python /absolute/path/to/checkout/homelab_cli.py ...` or the absolute launcher path; relative input files remain relative to your working directory.

## Create your private settings

Choose a private directory outside **all Git checkouts**. Create it yourself and check that only intended accounts can access it. This directory stores settings/reports, not the future application data. Example on Windows:

```powershell
New-Item -ItemType Directory -Path C:\HomelabPrivate
./bootstrap.ps1 configure --output C:\HomelabPrivate\settings.json
```

Example on Linux/macOS (choose an unused, canonical directory path):

```sh
mkdir -m 700 "$HOME/HomelabPrivate"
sh ./bootstrap.sh configure --output "$HOME/HomelabPrivate/settings.json"
```

The wizard asks for service IDs/numbers, target platform/architecture, an installation identity, storage roots, database policy, access mode and budgets. Optional per-service storage and port overrides follow. Saving requires an explicit yes. Cancellation or validation failure does not save settings. Budget warnings can be saved for later editing; they still block a review plan from passing.

For a noninteractive starting point:

```powershell
./bootstrap.ps1 configure --from examples/windows.settings.example.json --output C:\HomelabPrivate\settings.json
```

Then edit that private JSON in your editor and validate it. Neither method overwrites an existing file. To preserve revisions, save a new filename. Output must be an absolute `.json` path with an existing parent, outside Git and without symlink/junction ancestors. Writes use exclusive creation; on POSIX files start with mode 0600. Windows files inherit the parent ACL: this phase does **not** configure ACLs. Protect the parent against other users and concurrent changes. A failed write can leave a partial file for inspection; the tool does not delete it automatically.

Do not enter passwords or tokens. Unknown fields are rejected. Private settings contain actual local paths and an installation identity; keep them outside Git even though they contain no credentials.

## Check and review

```powershell
./bootstrap.ps1 validate --config C:\HomelabPrivate\settings.json
./bootstrap.ps1 doctor --config C:\HomelabPrivate\settings.json
./bootstrap.ps1 plan --config C:\HomelabPrivate\settings.json --check-host
./bootstrap.ps1 plan --config C:\HomelabPrivate\settings.json --json --output C:\HomelabPrivate\review-v1.json
```

`doctor` without `--config` checks general local prerequisites only. It cannot evaluate selected ports, storage or resource intent without settings. `plan` is offline unless `--check-host` is supplied. A live report is attached as `host_report`, outside the deterministic plan hash; the core plan's `host_checked: false` means that the hashed intent does not certify a host snapshot. Retain the settings and catalog release with a review, and rerun live checks before any future execution.

Exit codes: 0 means the requested validation/planning command completed without detected blockers (or the wizard was declined); 2 means invalid input or detected blockers; 130 means interrupted input. Warnings can coexist with exit 0. **Exit 0 never means deployment-approved, healthy applications, or production-ready.** Doctor reports `review-required` even when it finds no blockers.

Plans redact path values and installation identity, but retain service choices, ports, target platform and budgets. Doctor reports resource totals and check outcomes, not command stderr, credentials or container names. Review reports before sharing: hashes are change fingerprints, not encryption or anonymization of predictable inputs. No report is uploaded automatically.

## Settings contract

| Field | Accepted meaning |
| --- | --- |
| `schema_version`, `kind` | `1`, `homelab-settings`; exact fields, no duplicate JSON keys |
| `installation_id` | Lowercase hyphenated identity, up to 32 characters; future projects use `hl-<identity>-<service>` |
| `platform`, `architecture` | `windows` / `linux` / `macos`; `amd64` / `arm64` (not proof of image availability) |
| `mode`, `gpu` | Only `fresh`, `disabled`; adoption, recovery, replicas and GPU provisioning are unavailable |
| `access` | `loopback` by default; explicit `lan` proposes all-interface IPv4 bindings but changes nothing |
| `services` | Unique module IDs from `catalog`; dependencies are resolved in stable order |
| `paths` | Absolute, dedicated, non-overlapping installation, media and backup roots; database root or null |
| `database_storage` | `docker-named-volumes` default, or expert/unvalidated `bind` proposal |
| `service_paths` | Optional selected-module `media_root` / `database_root` overrides on independent roots |
| `port_overrides` | Exact catalog key to integer first port; TCP/UDP and range length remain catalog-defined |
| `resource_budget` | Positive integer CPU ceiling, memory GiB and host RAM reserve GiB; planning only |
| `storage_reserve_gib` | Free-space reserve for each declared storage role; combined when sharing a filesystem |

Default module directories are `<role-root>/<module-id>`. Overrides must not overlap any global root or another effective module destination; omit an override to use the normal subdirectory. Database overrides require bind policy and a declared database-data role. Named volumes have **no independently selectable host database path**: their physical location follows Docker's data disk, which the tool does not move. A backup directory on the same physical device is staging, not hardware-failure protection.

To propose alternate ports, for example:

```json
"port_overrides": {
  "glance.http": 18081,
  "uptime-kuma.http": 13001,
  "paperless-ngx.http": 18010
}
```

These numbers are examples, not guaranteed free. See [planning metadata](../catalog/planning.json) for exact keys, protocol and span. Same-number TCP/UDP reservations are distinct. Same-protocol overlapping ranges block planning. Internal databases/caches do not need public host ports. Matrix TURN and other protocols still need application-specific networking validation later; a loopback plan is not a promise that remote clients will work.

## What doctor can and cannot prove

- It detects host OS/architecture, Python, physical RAM/CPU, a local Docker socket/pipe context, Linux engine architecture, engine resource ceiling and Compose compatibility. Remote SSH/TCP contexts are refused before any daemon query. Endpoint/TLS environment overrides block checks rather than being silently ignored; a selected `DOCKER_CONTEXT` is inspected and explicitly pinned for subsequent queries. See [Docker contexts](https://docs.docker.com/engine/manage-resources/contexts/) and [CLI environment precedence](https://docs.docker.com/reference/cli/docker/).
- Settings budgets are compared with physical RAM/host reserve and Docker's ceiling. Module allowances are provisional conservative planning choices, **not benchmarks, upstream minimums, measured demand, free engine capacity or configured container limits**. Existing workloads consume capacity too. Selecting every app is not a recommended preset.
- Existing Compose project identities and published bindings are checked. Native listener checks use Windows networking cmdlets, Linux `ss`, or macOS `lsof`. Missing tools/failed parsing block availability claims. Nonprivileged inventories can be incomplete and all results are snapshots, not reservations; a future executor must recheck and handle bind failure.
- Storage checks do not create directories or write probe files. They inspect an existing ancestor, advisory access rights, available filesystem space and occupied roots; missing drives, Git storage and symlink/junction mappings are refused. `/mnt/<mount>` and `/Volumes/<mount>` require a mounted filesystem. Other mount conventions need manual verification. Canonical paths avoid system aliases such as macOS `/var` pointing to `/private/var`. Free-space reporting uses [Python disk usage](https://docs.python.org/3/library/shutil.html#shutil.disk_usage), not media-health or write-durability testing.
- Docker VM image/named-volume free space, Desktop file sharing, database filesystem suitability, ACL effectiveness, quotas, image manifests, GPU compatibility and app readiness remain separate unverified requirements. ARM64 is selectable intent, not certified support.
- Time checks read OS synchronization status where recognizable; they do not measure clock offset. Localized Windows output and macOS synchronization remain unknown. The tool never sets the clock or starts a time service.

## Reference check and next boundary

On 2026-10-03 the live Windows reference check observed eight Docker CPUs, approximately 9.72 GiB engine memory and 31.77 GiB host memory. It correctly blocked the example because its drives were unavailable and the three default ports were already used by existing services. Time synchronization was unknown, not a pass. These are dated observations, not a current health guarantee or faults in the running apps.

Phase 3 adds storage/secrets/ownership and safe execution primitives with a **synthetic disposable module first**. This milestone makes no changes to the reference applications. Stop here until Phase 3 is explicitly requested.
