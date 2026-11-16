# Matrix, Element and optional TURN integration

This Phase 7 adapter validates the existing Matrix family-chat deployment without renaming its server identity, replacing its signing key or silently enabling optional networking. It treats Synapse, Element and coturn as one user-facing communication path while retaining their separate network and recovery boundaries.

## Integration model

| Path | Required transport | Publication model |
| --- | --- | --- |
| Matrix client API | HTTPS | Native Cloudflare Tunnel to loopback port `8008` |
| Element Web | HTTPS | Native Cloudflare Tunnel to loopback port `8089` |
| Synapse Admin | Local HTTP | Loopback port `8448` only |
| TURN listener | UDP and TCP | Direct DNS-only record and router/firewall forwarding on `3478` |
| TURN relay | UDP | Direct forwarding of `49160-49200` |

Cloudflare Tunnel carries the Matrix and Element HTTP routes. It does not replace a public UDP TURN endpoint. `turn.parmar.homes` must therefore remain a direct, unproxied DNS record that follows the current public address.

Element must be served over HTTPS for browser security and WebRTC. Synapse's TURN integration uses short-lived credentials derived from a secret shared with coturn. The public adapter never stores or prints that secret. See the upstream [Element installation security notes](https://github.com/element-hq/element-web/blob/develop/docs/install.md) and [Synapse TURN guide](https://element-hq.github.io/synapse/latest/turn-howto.html).

## Reviewed reference runtime

- Synapse `1.164.2`.
- Element Web `1.12.33`.
- coturn `4.18.0`.
- Server identity `matrix.parmar.homes`.
- Element origin `https://chat.parmar.homes/`.
- Matrix origin `https://matrix.parmar.homes/`.

The reference policy records the resolved live image IDs because the private Compose file still uses floating tags. Recording an image is not the same as approving an update. A later production image migration still needs a consistent Matrix backup, exact candidate images and rollback evidence.

## Private audit and plan

Keep the sanitized audit outside Git. It contains only booleans, versions, image IDs and classified error states—never credentials, messages, media or public address values.

```powershell
python -m homelab matrix-integration validate-audit `
  --audit C:\private\matrix-integration-audit.json

python -m homelab matrix-integration plan `
  --policy modules\matrix\integration.example.json `
  --audit C:\private\matrix-integration-audit.json `
  --output C:\private\matrix-integration-plan.json
```

The generated plan cannot change production. It reports Matrix/Element readiness, loopback hardening, local TURN configuration and independent public TURN readiness separately.

## External TURN probe

The credential-free probe sends a standards-based STUN binding request and deliberately omits the mapped public address from its output:

```powershell
python tools\matrix_turn_probe.py `
  --host turn.parmar.homes `
  --port 3478 `
  --transport udp

python tools\matrix_turn_probe.py `
  --host turn.parmar.homes `
  --port 3478 `
  --transport tcp
```

Run the manual `Matrix external TURN probe` workflow to obtain an independent internet vantage point. Its optional authenticated relay step requires temporary, expiring TURN REST credentials in `MATRIX_TURN_TEST_USERNAME` and `MATRIX_TURN_TEST_PASSWORD`. Delete those repository secrets immediately after the run. The shared coturn secret itself must never be uploaded.

A STUN response proves listener reachability only. Selected TURN is certified only after an authenticated relay succeeds and a real Element audio/video call works between devices on different networks.

## Evidence gate

```powershell
python -m homelab matrix-integration validate-evidence `
  --plan C:\private\matrix-integration-plan.json `
  --evidence C:\private\matrix-integration-evidence.json
```

Evidence must preserve the server name and signing-key hash, prove loopback Matrix/Element bindings, validate local and public endpoints after restart, and explicitly select or decline TURN. If TURN is selected, both external STUN transports, authenticated relay, and real audio/video calls are mandatory. If TURN is declined, no TURN success field may be inferred.

## Current reference-host blocker

The dedicated Cloudflare DDNS token is rejected by its client-IP filter after the ISP address changed. The DDNS container detects the new address but cannot update the direct TURN record, leaving DNS stale. For a dynamic-address updater, either remove that location restriction from this narrowly scoped token or maintain it whenever the address changes. Keep the token limited to DNS edit for the single required zone.

Until DDNS succeeds and independent relay/call tests pass, Matrix and Element messaging remain healthy but TURN calling is **not certified**.
