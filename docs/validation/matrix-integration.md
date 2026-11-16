# Matrix, Element and optional TURN validation record

Validated on the reference Windows Docker Desktop host on 2026-11-16. Sanitized machine-readable audit and plan evidence remain outside Git.

## Healthy Matrix and Element path

- Synapse `1.164.2`, PostgreSQL `15.19` and Element Web `1.12.33` were running; the declared Synapse, PostgreSQL and Element health checks passed.
- `https://matrix.parmar.homes/_matrix/client/versions` returned HTTP 200.
- `https://matrix.parmar.homes/health` returned HTTP 200.
- `https://chat.parmar.homes/` and its `config.json` returned HTTP 200.
- Matrix client and server `.well-known` documents returned the intended homeserver identity.
- Element's homeserver name and base URL match Synapse's immutable `matrix.parmar.homes` identity.
- The native `Cloudflared` Windows service was running in automatic-start mode.
- No account, message, room, media object, signing-key value or credential value was read.

## Loopback hardening

Synapse port `8008` and Element port `8089` were initially published on all host interfaces even though the native tunnel can reach loopback. Synapse Admin was already loopback-only.

An exact Compose rollback copy was saved under the private stack's timestamped `backups-host` directory. The first forced recreation encountered a transient retained Docker Desktop port; automatic rollback restored both healthy services. A controlled stop-and-port-release retry then bound Synapse and Element to `127.0.0.1` without pulling images. Both services were healthy after recreation and a subsequent controlled restart. Local and public Matrix/Element endpoints returned HTTP 200, discovery and Element identity still matched, the signing-key hash was unchanged across restart, and PostgreSQL, coturn, Synapse Admin, the WhatsApp bridge and DDNS containers remained running.

## TURN preflight

- Synapse advertises UDP and TCP TURN URIs for `turn.parmar.homes:3478`.
- coturn `4.18.0` was running with fingerprinting, REST shared-secret authentication, a one-hour credential lifetime and UDP relay ports `49160-49200`.
- The Synapse and coturn shared secrets were present and byte-equal; only the boolean result was retained.
- A local STUN binding request succeeded.
- The TURN hostname is direct DNS rather than Cloudflare-proxied, as required for UDP.
- The DDNS container was running every five minutes and correctly detected the current public address.

TURN is not publicly certified. The direct record did not match the current public address because Cloudflare rejected the dedicated DDNS token from the new address with error class `api-token-client-ip-filter`. A same-network request to the public TURN hostname timed out; that result alone cannot distinguish stale DNS from unsupported NAT hairpin behavior. No external authenticated relay or real cross-network Element call was claimed.

## Floating-image boundary

The live Compose source still declares mutable tags for Synapse, Element, coturn and optional companion services. The audit records exact resolved image IDs, but no image was pulled or upgraded. Pinning the whole production stack remains a separate backup-gated migration because Synapse, the bridge and PostgreSQL have state and compatibility requirements.

## Release decision

Go for `0.8.0-alpha.5` as an integration contract, loopback Matrix/Element hardening, public endpoint validation record and external TURN probe. No-go for a claim that TURN calls are working, for stable Phase 7, or for automatic production image updates. TURN can be accepted only after the dedicated DDNS credential is repaired, external UDP/TCP STUN and authenticated relay pass, and a real audio/video call succeeds across different networks.
