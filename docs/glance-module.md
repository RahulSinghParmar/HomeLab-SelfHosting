# Experimental Glance starter

This is a bounded Phase 4 experiment, not a replacement for an existing dashboard. It has two original, sanitized pages, a dashboard self-check and an intentionally unavailable synthetic endpoint. No production configuration, personal statistics, accounts, feeds or API keys are imported. The monitor URLs are container-local diagnostic targets, not navigation to installed host services.

## Supported scope

- Python 3.12+, local Docker context, Linux **amd64** engine, Compose CLI.
- Windows Docker Desktop live-tested. Linux/macOS unit tests do not certify their Docker runtime behavior. ARM/emulation and remote contexts are refused.
- Fresh, absent installation directory outside Git, with an existing parent. No adoption, shared database, named volume or arbitrary Compose input.
- Glance v0.8.6 reference image pinned in [image metadata](../modules/glance/image.json). This uses the reproducible reference version, not a claim that it is the latest or vulnerability-free.
- A private plan binds the root, selected port, template, image and exact local engine. Plans are machine-specific and must not be committed.

Read [upstream configuration documentation](https://github.com/glanceapp/glance/blob/v0.8.6/docs/configuration.md) for the application itself. The original starter is stored as JSON, which Glance accepts as YAML. General custom-template execution is deliberately not yet supported.

## New installation example (PowerShell)

Choose a new private parent outside your checkout. The examples use placeholder paths; adapt them before running. Never target your existing application folder.

```powershell
New-Item -ItemType Directory -Path 'D:\HomeLab-Trials'
python -m homelab glance plan --root 'D:\HomeLab-Trials\glance' --port 18081 --output 'D:\HomeLab-Trials\glance-plan.json'
```

Review the returned plan, including the network policy. Download the exact reviewed digest if it is not already cached (this explicit step contacts the upstream registry):

```powershell
docker pull --platform linux/amd64 glanceapp/glance@sha256:9dfb09470b207dcb67ac715994bdb1929374ba3f9c0d7df7462c24adf10fd073
python -m homelab glance up --plan 'D:\HomeLab-Trials\glance-plan.json' --confirm '<full-plan-id>'
python -m homelab glance status --plan 'D:\HomeLab-Trials\glance-plan.json'
```

Open `http://127.0.0.1:18081/home` on the Docker host. Verify **OK** for the self-check, **ERROR** for the expected unavailable fixture, and navigation to Operations. The lifecycle report deliberately says `requires-rendered-verification`: a running process is not proof of application health.

On Linux/macOS, the Python syntax is identical with native absolute paths and an existing parent directory; this remains runtime-unverified. No command installs Docker, edits WSL limits or opens firewall/tunnel routes.

## Operations

```powershell
python -m homelab glance stop --plan 'D:\HomeLab-Trials\glance-plan.json' --confirm '<full-plan-id>'
python -m homelab glance up --plan 'D:\HomeLab-Trials\glance-plan.json' --confirm '<full-plan-id>'
python -m homelab glance export --plan 'D:\HomeLab-Trials\glance-plan.json' --output 'D:\HomeLab-Trials\glance-export.json'
```

Retrying `up` against an unchanged running deployment does not recreate or restart it. `stop` retains configuration. To remove only the owned container and network, stop it first, then:

```powershell
python -m homelab glance remove --plan 'D:\HomeLab-Trials\glance-plan.json' --confirm '<full-plan-id>'
```

Removal retains `glance.yml`, `compose.json`, `state.json`, the operation lock file and exports. It never deletes installation files or volumes. The lock file persists by design; the kernel lock is released when the operation exits. Removed roots cannot be implicitly reactivated: use a new recovery root.

## Starter-configuration recovery

The export contains the starter configuration and a SHA-256 integrity check. It has no credentials, databases, custom assets or monitoring history. This is **not** an off-host encrypted backup or general Glance recovery tool. Export destinations must be outside installation storage and must not exist.

```powershell
python -m homelab glance plan --root 'D:\HomeLab-Trials\glance-restored' --port 18082 --output 'D:\HomeLab-Trials\restored-plan.json' --restore-config 'D:\HomeLab-Trials\glance-export.json'
python -m homelab glance up --plan 'D:\HomeLab-Trials\restored-plan.json' --confirm '<new-full-plan-id>'
```

The recovery gate verifies the export hash and exact certified starter content before generating a new plan. Open the new port and verify both pages and the checks. Compare configuration hashes. Stop/remove the separate trial afterward. Arbitrary modified exports are refused even if their checksum matches.

## Security and resource boundary

The container publishes only IPv4 loopback, uses a dedicated bridge and has no Docker socket, other application mounts, credentials or administration functions. The bridge **allows outbound connectivity**; it is not a network firewall. The original internal-only test did not publish a working host port on Engine 29.8.1. Effective Docker port mappings are now checked, rather than assuming a requested binding was realized. See [Docker networking](https://docs.docker.com/engine/network/) for internal/front-end network distinctions.

Limits: 128 MiB RAM, 0.5 CPU, 100 processes, two 5 MiB log files. The upstream image defaults to root inside the container; this experiment keeps that behavior but drops all capabilities, enables no-new-privileges and mounts both root filesystem and configuration read-only. Localhost has no authentication and is accessible to other local users/processes. Do not expose it publicly or attach a tunnel without a separate access review.

Host execution requires Docker access, which is powerful. File permissions are owner-restricted using the Phase 3 adapter, not encrypted. Same-user/root/Docker-administrator tampering and race attacks are outside the threat model. The coordinator checks owner/plan labels, image, mount source, resource limits, ports, privileges and network membership before mutations. It refuses unexpected resources rather than attempting repair.

## Failure and update boundaries

- Missing cached image: review and explicitly pull the pinned digest; `up` never pulls or builds.
- Occupied root/port or foreign project: choose fresh storage/port. Do not delete the existing resource to make the test pass.
- Changed engine/context/template/configuration: preserve state and review; do not edit hashes or labels to bypass checks.
- Interrupted creation after Docker created the exact owned container: retry can reconcile it. A recorded running container that disappears is not silently recreated.
- Interrupted removal: retry can finish removing exact owned stopped resources. Foreign attachments block network removal.
- Partial private initialization or `.pending-*` artifacts: preserve evidence for manual review; no blind cleanup or automatic permission repair.
- Raw Docker logs are not echoed by the coordinator. Inspect only the identified trial locally if a command fails, and sanitize before sharing.
- No upgrade or automated rollback command exists. Retain the tagged source, export configuration, and test a new reviewed image/template in a separate root. Never run a general Compose command against existing production folders as part of this experiment.

Uptime Kuma check registration/state transitions, Beszel host data, richer dashboard customization, Stirling-PDF and opt-in Portainer are later Phase 4 milestones.
