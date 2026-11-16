# Matrix validation record

Validated on Windows Docker Desktop on 2026-11-16. Evidence remains outside Git at `C:\Docker\Matrix-Plan-20261116.json` and `C:\Docker\Matrix-Evidence-20261116.json`.

## Read-only production audit

- Seven production project containers remained running throughout the work.
- Synapse reported `1.164.2`; PostgreSQL reported `15.19`; Element reported `1.12.33`; coturn reported `4.18.0`.
- Synapse, PostgreSQL and Element were healthy.
- Synapse state is bind-mounted separately from the media store; PostgreSQL has its own data bind; Element uses a read-only configuration bind.
- Synapse, Element, coturn, Synapse Admin, the WhatsApp bridge and DDNS still use floating tags in the private Compose source. Their resolved local image digests were recorded read-only but no production image was replaced.
- No production message, account, media object, credential or signing-key content was read.

## Reviewed candidate identity

- Synapse `1.164.2`: immutable amd64/arm64 index and platform manifests.
- PostgreSQL `15.19-alpine`: immutable multi-platform index; amd64 and arm64 manifests selected.
- Element Web `1.12.35`: immutable amd64/arm64 index and platform manifests.
- Reusable Compose is loopback-only, uses a private database network and does not mount the Docker socket or request device/privileged access.

## Isolated application exercise

The disposable project used generated credentials and the synthetic server name `matrix-recovery.invalid`.

- Synapse, PostgreSQL and Element passed health checks and exact runtime-version checks.
- A synthetic administrator was registered through Synapse's shared-secret registration endpoint.
- Two independent client login sessions succeeded.
- The first session created a private room, sent a text event, uploaded exact synthetic media bytes and downloaded those bytes successfully.
- Element returned a healthy browser page before backup.

## Application-consistent recovery

1. Synapse was stopped while PostgreSQL remained healthy.
2. PostgreSQL produced a nonempty custom-format `PGDMP` archive.
3. Synapse configuration, the signing key, media and Element configuration were copied into a manifested recovery set.
4. The source containers, database volume, state root and media root were removed.
5. An unrelated Compose project and independent state/media roots were created.
6. The database dump was restored before Synapse started.
7. The recovered server used the same server name, exact candidate versions and byte-identical signing-key SHA-256.
8. A new login session read the original room/text event and downloaded the exact original media bytes.
9. Element rendered after recovery.

The final measured three-container memory snapshot was approximately `190.01 MiB`. This is an idle synthetic sample, not a concurrency or production-capacity benchmark.

## Safety and cleanup

- Production paths, credentials, messages and media were not used.
- Production container identity/status matched before and after the rehearsal.
- No trial container, volume or `homelab-matrix-trial-*` root remained.
- The persisted evidence was independently accepted by `python -m homelab matrix validate-evidence`.

## Explicitly unproven

- Client E2EE key-backup recovery from a fresh Element device.
- Production-consistent encrypted/off-host recovery.
- Federation and `.well-known` delegation.
- TURN/UDP calls and the actual public-network path.
- WhatsApp bridge session recovery and outbound-message isolation.
- Production migration away from floating image tags.
- arm64 runtime execution.

The live family-chat service was not adopted or modified. These remaining gates must pass before production recovery is certified.
