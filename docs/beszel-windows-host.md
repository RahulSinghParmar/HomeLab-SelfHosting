# Experimental Beszel Windows host adapter

This bounded Phase 4 adapter safely upgrades an **existing NSSM-managed Windows Beszel agent**. It preserves all connection configuration, produces a private rollback copy, fingerprints service configuration without recording environment values, and refuses an unexpected executable, architecture, service manager or configuration change.

It does not install NSSM, create a Windows service, edit the firewall, pair a system, change ports, migrate a hub or alter Docker. Fresh Windows installation remains a later clean-machine milestone. The upstream isolated Beszel module remains separate.

## Why a version-local agent is still needed

The reference server uses Beszel 0.18.7. Its agent detects the older GeForce GT 730 through NVIDIA tooling, but that driver does not return utilization. Windows GPU Engine performance counters do. Upstream service monitoring is systemd-specific, so native Windows services are otherwise absent.

The patch adds:

- a Windows GPU Engine utilization fallback while preserving vendor name, temperature and memory data;
- read-only Service Control Manager discovery, limited to explicit `SERVICE_PATTERNS`;
- automatic stopped services reported as failed and manual/disabled stopped services as inactive;
- a hidden `typeperf.exe` child process; and
- service details that omit executable command lines and service accounts because those fields can contain credentials or identify a user.

No patterns means no Windows service collection. The earlier private build defaulted to all services; the reviewed candidate fails closed instead. The fallback reports one logical utilization value and is certified only for the reference single-GPU use case. Multi-GPU mapping, localized counter names and newer Beszel versions require separate work.

## Reproducible source preparation

Review [source metadata](../modules/beszel-windows-host/source.json), the MIT-licensed upstream source and the patch before building:

```powershell
git clone https://github.com/henrygd/beszel.git C:\Build\beszel-windows-host
git -C C:\Build\beszel-windows-host checkout 6e3fd90834309213aca32f2ff5fb0b027661c39a
git -C C:\Build\beszel-windows-host apply --check C:\Path\To\HomeLab-SelfHosting\modules\beszel-windows-host\beszel-0.18.7-windows-host.patch
git -C C:\Build\beszel-windows-host apply C:\Path\To\HomeLab-SelfHosting\modules\beszel-windows-host\beszel-0.18.7-windows-host.patch
docker build --file C:\Path\To\HomeLab-SelfHosting\modules\beszel-windows-host\Dockerfile.agent-windows --output type=local,dest=C:\Build\beszel-output C:\Build\beszel-windows-host
```

The build fetches pinned Go/.NET dependencies and Smartmontools during execution. Image digests are pinned, but registry/dependency availability and a complete transitive-license or vulnerability assessment remain external gates. Do not accept an unexplained binary-hash difference.

Run the produced Windows test binary before planning an upgrade:

```powershell
C:\Build\beszel-output\beszel-agent-windows-tests.exe
```

## Audit and controlled upgrade

Run from the blueprint repository. Audit output includes configuration names and fingerprints, never values:

```powershell
python -m homelab beszel-windows audit --service BeszelAgent
python -m homelab beszel-windows plan `
  --service BeszelAgent `
  --candidate C:\Build\beszel-output\beszel-agent-windows-amd64.exe `
  --backup-root C:\Private\BeszelAgentBackups `
  --output C:\Private\beszel-windows-plan.json
python -m homelab beszel-windows status --plan C:\Private\beszel-windows-plan.json
```

Review the entire plan ID. `apply` requires an elevated terminal because it stops and starts the existing service and replaces its executable:

```powershell
python -m homelab beszel-windows apply --plan C:\Private\beszel-windows-plan.json --confirm FULL_PLAN_ID
```

The adapter refuses candidate drift, a non-amd64 PE, non-NSSM service management, nonautomatic startup, missing `KEY`/`TOKEN`, service-configuration drift, an existing backup destination and a plan stored inside backup storage. It changes only the binary. Existing environment values, port, account, working directory and firewall remain untouched.

Rollback requires the same plan and confirmation. It verifies the retained manifest and original binary before replacement; the backup remains after rollback:

```powershell
python -m homelab beszel-windows rollback --plan C:\Private\beszel-windows-plan.json --confirm FULL_PLAN_ID
```

## Acceptance gates

- Compiled Windows tests pass from a clean patched upstream checkout.
- Redacted audit and reviewed plan show no drift.
- Apply creates a verified private rollback copy and returns the service to running.
- The hub receives a newer host record after restart.
- Configured services appear without command lines/accounts, and a controlled stopped automatic test service is distinguishable from an inactive manual service.
- GPU utilization changes under a real workload; absence is not interpreted as zero.
- Agent restart and Windows reboot preserve connectivity.

See the [validation record](validation/beszel-windows-host.md). A running service alone is not complete evidence.
