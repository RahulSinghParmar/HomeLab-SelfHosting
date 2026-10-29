# Vaultwarden application-aware recovery module

Version **0.6.0-alpha.10** adds a bounded Vaultwarden recovery adapter for generated test data. It does not inspect, import, restart, upgrade or modify an existing vault.

## What the module proves

- exact Vaultwarden 1.37.1 and Playwright/Chromium images are pinned by digest;
- one app container runs on an internal bridge with only a loopback HTTP port;
- the long-running container drops all capabilities, uses a read-only root filesystem, enables `no-new-privileges`, and has CPU, memory, PID and log limits;
- a real rendered Web Vault registers a generated account, creates an encrypted secure note, uploads a 49-byte attachment, reloads/unlocks, opens the item from an independent browser context and downloads exact bytes;
- the same semantic checks pass after an application restart;
- Vaultwarden's built-in backup command creates a consistent SQLite snapshot before the app is stopped briefly for the file set;
- a fresh unrelated project restores the snapshot, RSA keys, attachments, sends and optional configuration, then repeats browser decryption, download and restart checks.

The browser helper uses an ephemeral self-signed HTTPS proxy only inside the disposable Docker network because Web Crypto requires a secure context. The published host endpoint remains loopback HTTP for diagnostics and is not a production Web Vault URL.

## Safety boundaries

The trial root, project name, owner label, port and generated credentials are plan-bound. Every mutating command requires the complete plan ID. Existing Docker resources are never adopted. `remove` deletes only owned containers/network and retains the data root; deleting generated files is a separate operator decision.

Registration is enabled only inside this disposable loopback trial so the browser fixture can create its generated first user. Invitations and mail are disabled, the admin route has no token, no Docker socket/device/GPU is mounted, and no public proxy is created. These settings are not production recommendations.

## Commands

Create the source plan outside the installation root:

```sh
python -m homelab vaultwarden plan --root C:/Docker/homelab-vaultwarden-trial --port 18050 --output C:/Docker/homelab-vaultwarden-plan.json
```

Review the redacted output and use its complete `plan_id`:

```sh
python -m homelab vaultwarden up --plan C:/Docker/homelab-vaultwarden-plan.json --confirm PLAN_ID
python -m homelab vaultwarden exercise --plan C:/Docker/homelab-vaultwarden-plan.json --confirm PLAN_ID
python -m homelab vaultwarden backup --plan C:/Docker/homelab-vaultwarden-plan.json --output C:/Docker/homelab-vaultwarden-backup --confirm PLAN_ID
```

Create an unrelated restore plan with a different root and port:

```sh
python -m homelab vaultwarden plan --root C:/Docker/homelab-vaultwarden-restore --port 18051 --restore-backup C:/Docker/homelab-vaultwarden-backup --output C:/Docker/homelab-vaultwarden-restore-plan.json
python -m homelab vaultwarden up --plan C:/Docker/homelab-vaultwarden-restore-plan.json --confirm RESTORE_PLAN_ID
```

Status is read-only. Stop before removal:

```sh
python -m homelab vaultwarden status --plan C:/Docker/homelab-vaultwarden-plan.json
python -m homelab vaultwarden stop --plan C:/Docker/homelab-vaultwarden-plan.json --confirm PLAN_ID
python -m homelab vaultwarden remove --plan C:/Docker/homelab-vaultwarden-plan.json --confirm PLAN_ID
```

## Recovery set

The private backup contains generated credentials, `db.sqlite3`, RSA keys, attachment and Send trees when present, optional `config.json`, sanitized Compose metadata, browser semantic evidence, complete file-tree checksums and a manifest. Transient SQLite WAL/SHM files, icons and temporary files are rejected. Restore refuses a changed plan, image set, credential checksum, database checksum, data tree, browser evidence or manifest identity.

The set is plaintext-sensitive and local. Keep it outside Git and synchronized folders. It is not a hardware-failure recovery point until an encrypted off-host copy and separately recoverable key have themselves passed an independent restore.

## Not covered

Organizations, collections, Sends semantics, TOTP/passkeys, emergency access, password history, mobile/desktop extensions, SMTP, public reverse proxies, load, upgrades and rollback are untested. The module has one Windows Docker Desktop Linux/amd64 rehearsal; Linux, macOS and ARM64 runtime behavior are not certified.

See [validation evidence](validation/vaultwarden.md), the [production inventory runbook](runbooks/vaultwarden.md), and Vaultwarden's [backup guidance](https://github.com/dani-garcia/vaultwarden/wiki/Backing-up-your-vault).
