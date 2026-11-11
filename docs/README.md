# Documentation

Use this page as the entry point for the HomeLab-SelfHosting blueprint. Start with planning and safety, then open only the module you intend to test.

## Start safely

1. Read [architecture and boundaries](architecture.md).
2. Check [platform support](platform-support.md).
3. Follow the [planning guide](planning.md) to validate settings and inspect the host.
4. Review [safe execution](safe-execution.md) before running a module adapter.
5. Read the selected module guide and its validation record before applying a plan.

The general planner does not deploy applications. Existing deployments are not automatically adopted, upgraded or removed.

## Phase 4 modules

| Module | Operator guide | Validation |
| --- | --- | --- |
| Glance | [Starter module](glance-module.md) and [operations layout](glance-operations-layout.md) | [Layout and collector evidence](validation/glance-operations-layout.md) |
| Uptime Kuma | [Lifecycle module](kuma-module.md) and [desired-state configuration](kuma-configuration.md) | [Configuration and recovery evidence](validation/kuma-configuration.md) |
| Beszel | [Isolated module](beszel-module.md) and [Windows host adapter](beszel-windows-host.md) | [Hub/agent evidence](validation/beszel-trial.md) and [Windows evidence](validation/beszel-windows-host.md) |
| Stirling-PDF | [Module guide](stirling-pdf-module.md) | [Rotation and recovery evidence](validation/stirling-pdf.md) |
| Portainer | [Isolated-control guide](portainer-module.md) | [Permission and recovery evidence](validation/portainer.md) |

The combined decision and remaining gates are in [Phase 4 integrated validation](validation/phase4-integrated.md).

## Phase 5 modules

| Module | Operator guide | Validation |
| --- | --- | --- |
| Paperless-ngx | [Application-aware recovery module](paperless-ngx-module.md) and [encrypted vault](paperless-vault.md) | [Application recovery](validation/paperless-ngx.md) and [encrypted-vault evidence](validation/paperless-vault.md) |
| AFFiNE | [Application-aware recovery module](affine-module.md) and [encrypted vault](affine-vault.md) | [Application recovery](validation/affine.md) and [off-host recovery gate](validation/affine-off-host-recovery.md) |
| Nextcloud | [Application-aware recovery module](nextcloud-module.md) and [encrypted vault](nextcloud-vault.md) | [Local recovery evidence](validation/nextcloud.md) and [off-host recovery gate](validation/nextcloud-off-host-recovery.md) |
| Firefly III | [Application-aware recovery module](firefly-iii-module.md) and [encrypted vault](firefly-vault.md) | [Local recovery evidence](validation/firefly-iii.md) and [off-host recovery gate](validation/firefly-off-host-recovery.md) |
| Vaultwarden | [Application-aware recovery module](vaultwarden-module.md) and [encrypted vault](vaultwarden-vault.md) | [Local browser recovery](validation/vaultwarden.md) and [off-host recovery gate](validation/vaultwarden-off-host-recovery.md) |
| Karakeep | [Application-aware module](karakeep-module.md) · [encrypted vault](karakeep-vault.md) | [Local recovery](validation/karakeep.md) · [off-host recovery](validation/karakeep-off-host-recovery.md) |

Paperless, AFFiNE, Nextcloud, Firefly III, Vaultwarden and Karakeep now have application-aware and encrypted synthetic off-host recovery paths. The [Phase 5 encrypted recovery kit](phase5-recovery-kit.md) and [closure record](validation/phase5-closure.md) bind their consistency methods, nonempty fixtures, clean-runner semantic restores and restore-gated retention. The [owner-operated backup design](owner-operated-backups.md) remains disabled until private storage and key-custody choices are approved.

## Phase 6 media

The [media and acceleration foundation](phase6-media-foundation.md) defines authoritative originals, rebuildable derivatives, cache exclusions, manual heavy jobs and CPU-fallback acceleration gates. Its [validation record](validation/phase6-media-foundation.md) documents the read-only reference-host capability result. The [Immich recovery module](immich-module.md) proves exact original download, ML isolation and a quiesced PostgreSQL/protected-file backup. The [Immich encrypted vault](immich-vault.md) adds full-data-checked Restic storage and independent clean-runner recovery; see the [local evidence](validation/immich.md) and [off-host recovery record](validation/immich-off-host-recovery.md). The [Jellyfin module](jellyfin-module.md) adds explicit native/container selection, supported-platform enforcement and a non-activating Linux Compose renderer. The [Jellyfin recovery trial](jellyfin-recovery.md) proves built-in same-version application restore and exact direct play. The [Jellyfin encrypted recovery module](jellyfin-vault.md) now adds separate owner-managed media recovery, full-data-checked encryption, independent key custody and source-loss validation; see the [off-host recovery record](validation/jellyfin-off-host-recovery.md). Owner production storage adoption, client/concurrency testing and optional media-management selection remain subsequent milestones.

## Operations and recovery

- [Service requirements](services.md)
- [Backup and recovery design](recovery.md)
- [Owner-operated Phase 5 backup design](owner-operated-backups.md)
- [Phase 5 encrypted recovery kit](phase5-recovery-kit.md)
- [Public-access boundary](public-access.md)
- [Security policy](../SECURITY.md)
- [Per-service runbooks](runbooks/)

## Project status

- [Roadmap and acceptance gates](roadmap.md)
- [Current inventory](inventory.md)
- [Discovery findings](discovery/findings.md)
- [Release history and version policy](releases/README.md)
- [Changelog](../CHANGELOG.md)

## Validation commands

```sh
python tools/validate_repository.py
python tools/validate_phase4.py
python tools/validate_phase5.py
python tools/validate_phase5_closure.py
python tools/validate_phase6.py
python tools/check_publication.py --history
python -m unittest discover -s tests -v
```

Windows contributors should also run `./tests/Test-ReferenceCollector.ps1`. Validate the exact staged diff with `git diff --cached --check` before committing.
