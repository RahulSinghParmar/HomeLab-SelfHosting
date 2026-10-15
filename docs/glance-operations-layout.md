# Reusable Glance operations layout and collectors

This Phase 4 component turns the useful structure of the private dashboard into a portable, privacy-bounded profile. It does **not** copy private YAML, domains, drive roles, API keys, account identifiers, application records or personal statistics.

The reusable system has three deliberately separate parts:

1. The `operations` layout: seven composable pages assembled deterministically into one Glance-compatible JSON document.
2. A host-side one-shot collector: reads only explicitly selected paths, containers, endpoints and Windows services and writes five aggregate snapshots.
3. An internal metrics sidecar: serves those files read-only to Glance and has no Docker socket, host command access or published port.

Glance v0.8.6 supports both environment/secret substitution and nested configuration includes. This blueprint uses deterministic JSON assembly instead so the reviewed profile has one stable hash while retaining one source file per page. See the [upstream configuration documentation](https://github.com/glanceapp/glance/blob/v0.8.6/docs/configuration.md).

## Pages

- Home command center
- Infrastructure
- Storage & Backups
- Applications & Services
- Security & Public Access
- Intelligence & Development
- Live System

Every operational custom API widget is restricted to `http://metrics:8765/v1/...`. Optional RSS, release and documentation links are public read-only sources; they are not operational truth and may be unavailable offline.

## Render the layout

Render outside this Git checkout. The writer refuses an existing destination and emits strict JSON, which Glance accepts:

```powershell
python -m homelab glance-layout list
python -m homelab glance-layout render `
  --profile operations `
  --output 'D:\HomeLab-Private\glance\glance.json'
```

The rendered profile contains no environment placeholders or secrets. Machine-specific links should be added in a separate private customization layer; do not edit the certified source profile and then keep its original hash.

## Configure and sample the host

Copy [the example collector configuration](../modules/glance/collector-config.example.json) outside Git, then select only the paths and services you intend to reveal. IDs and labels appear in snapshot output. Container names, filesystem paths and endpoint origins remain private configuration and are not copied to the snapshots.

```powershell
python -m homelab glance-collector validate `
  --config 'D:\HomeLab-Private\glance\collector.json'
python -m homelab glance-collector sample `
  --config 'D:\HomeLab-Private\glance\collector.json'
```

The collector creates owner-private snapshots atomically and refuses output inside Git, overlapping monitored storage, URL credentials, remote Docker contexts, unknown fields, duplicate identifiers, symlinked storage and unbounded lists. Docker inspection is allowlist-only. Endpoint checks use credential-free `HEAD` requests, never follow redirects and never store bodies. Errors expose exception classes/status, not command output.

`psutil` is optional. When available it adds CPU and memory percentages; otherwise the host section is visibly `limited`. Storage and backup checks report capacity/freshness only. A recent artifact is not restore evidence.

Run `sample` from an existing trusted scheduler at the desired interval. This milestone does not automatically create an administrator task, background service, login item or systemd unit.

## Isolated Compose example

Set the two private paths and an unused loopback port in the calling environment, then validate before starting:

```powershell
$env:GLANCE_CONFIG_FILE = 'D:\HomeLab-Private\glance\glance.json'
$env:GLANCE_SNAPSHOT_DIR = 'D:\HomeLab-Private\glance\snapshots'
$env:GLANCE_PORT = '18081'

docker compose -f modules/glance/operations.compose.yml config --quiet
docker compose -f modules/glance/operations.compose.yml up -d --pull never
```

The example has a normal dedicated bridge because Docker Desktop did not publish the requested loopback port on an internal-only bridge. Only the dashboard is published, on `127.0.0.1`; the metrics sidecar is reachable only by the dashboard service. Both services use digest-pinned images, read-only roots, dropped capabilities, no-new-privileges, bounded memory/CPU/PIDs and rotated logs. Neither service receives a Docker socket.

Stop or remove only the reviewed project:

```powershell
docker compose -f modules/glance/operations.compose.yml stop
docker compose -f modules/glance/operations.compose.yml down
```

`down` removes these containers and their dedicated network, not the rendered config or snapshot directory. This example does not adopt, update or replace an existing Glance project.

## Known boundaries

- Application-specific SQL, log parsing and authenticated APIs remain private optional adapters. They are not safe universal defaults.
- Endpoint success is availability evidence, not login, upload, WebSocket or workflow evidence.
- TLS checks validate the configured HTTPS origin from the collector host; they do not change DNS or certificates.
- Snapshot ACLs protect against ordinary other users, not the same user, administrators or Docker administrators.
- The sidecar detects missing, malformed and stale snapshots; dashboard page refresh is still required by Glance.
- Production migration, public exposure, scheduled-task installation and automatic update/rollback remain separately reviewed operations.

See the [validation record](validation/glance-operations-layout.md).
