# Matrix identity and recovery module

This Phase 7 module plans a private Matrix core without adopting, restarting or upgrading an existing homeserver. It treats the Matrix server name and signing key as durable identity, not cosmetic configuration, and separates homeserver recovery from client-side end-to-end-encryption recovery.

## Reviewed core

| Component | Reviewed release | Purpose |
| --- | --- | --- |
| Synapse | `1.164.2` | homeserver and client API |
| PostgreSQL | `15.19` | durable homeserver database |
| Element Web | `1.12.35` | browser client |

All three images use immutable multi-platform index digests plus reviewed amd64 and arm64 platform digests. The example renders loopback-only HTTP ports, a private database network, explicit resource ceilings, health checks, bounded logs and a file-backed PostgreSQL secret. It does not mount the Docker socket or request privileged/device access.

The reusable core disables open registration, federation, TURN, bridges, admin UI, metrics and URL previews. Those features have distinct trust, networking, secret and recovery requirements and must be reviewed independently before being enabled.

## Identity boundary

A recovery must preserve all of the following as one consistent set:

- PostgreSQL custom-format dump.
- Synapse configuration and the original server signing key.
- Media store.
- Element configuration.
- Sanitized Compose/image metadata.
- The unchanged Matrix `server_name`.

Changing `server_name` creates a different Matrix identity. Restoring only the database or only the signing key is not accepted. Synapse's [backup guidance](https://element-hq.github.io/synapse/latest/usage/administration/backups.html) likewise separates the database, configuration/signing key and media-store requirements.

## Client E2EE boundary

The server backup does **not** prove that an Element user can decrypt encrypted-room history on a new device. Each owner must separately enable and test Matrix key backup or another supported client recovery method, retain the recovery key outside the server, sign in from a fresh client and verify an older encrypted message. The module rejects evidence that represents server recovery as E2EE-key recovery.

## Plan without deployment

Copy the selection example to private storage and replace the example domains, paths and ports. The server name becomes permanent once accounts and rooms are created.

```powershell
python -m homelab matrix plan `
  --selection C:\private\matrix-selection.json `
  --output C:\private\matrix-plan.json

python -m homelab matrix render-compose `
  --plan C:\private\matrix-plan.json `
  --output C:\private\matrix-compose.json
```

Before deployment, create the private Synapse configuration, signing key, Element `config.json` and `secrets/postgres_password` beneath the selected state root. The repository never generates or stores production secrets.

## Validate recovery evidence

The isolated rehearsal tool uses generated credentials, a synthetic account, private room, text event and media object. It quiesces Synapse, creates a PostgreSQL custom dump, removes the source state and restores to an independent project/root with the same identity.

```powershell
python tools\matrix_trial.py `
  --confirm RUN-ISOLATED-MATRIX-TRIAL `
  --output C:\private\matrix-evidence.json `
  --plan-output C:\private\matrix-plan.json

python -m homelab matrix validate-evidence `
  --plan C:\private\matrix-plan.json `
  --evidence C:\private\matrix-evidence.json
```

The trial is destructive only to its generated `homelab-matrix-trial-*` roots and labelled Compose projects. It does not read production messages, accounts, credentials or media.

## Public access and calls

Element must be served over HTTPS; its upstream installation guidance notes that browser security and WebRTC require a secure context. An HTTP reverse proxy or Cloudflare Tunnel can publish Element and the Synapse client API, but it does not automatically provide Matrix federation or TURN UDP relay. TURN, federation and bridges remain separate Phase 7 gates.

## Production boundary

The live family-chat deployment remains unchanged. It currently contains Synapse, PostgreSQL, Element, coturn, Synapse Admin, a WhatsApp bridge and Cloudflare DDNS. Adopting this module requires a production-consistent encrypted backup, separate client E2EE recovery checks, exact optional-component decisions and a rollback-tested migration from floating image tags.
