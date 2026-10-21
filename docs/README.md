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

Phase 5 proceeds one personal-data application at a time. Paperless and AFFiNE now have experimental application-aware, encrypted local and synthetic off-host clean-runner recovery paths. AFFiNE additionally has a real browser-rendered note check across independent sessions and restarts. Production backup adoption, durable owner-operated off-host storage and the other four applications remain planned.

## Operations and recovery

- [Service requirements](services.md)
- [Backup and recovery design](recovery.md)
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
python tools/check_publication.py --history
python -m unittest discover -s tests -v
```

Windows contributors should also run `./tests/Test-ReferenceCollector.ps1`. Validate the exact staged diff with `git diff --cached --check` before committing.
