# Reproducible configuration mapping

Every [module runbook](runbooks.md) separates four sources of configuration. The machine-readable version is [discovery.json](../../catalog/discovery.json).

| Category | Examples | Future destination |
| --- | --- | --- |
| Upstream behavior | One-shot migrations, expected database extensions, service entrypoints | Verified upstream version contract; do not fork without need |
| Reusable customization | Resource profiles, dashboard layout, safe polling defaults, source patches | Reviewed module templates/build recipes with tests |
| Private installation values | Passwords, signing keys, domains, mail accounts, paths, app identities | Protected installation plan, secret store and encrypted recovery bundle |
| Manual/platform/external | Native task/service registration, GPU driver support, DNS/TURN/VPN enrollment | Explicit platform adapter or guided owner task with validation |

## Storage translation

- Record each runtime source and container target before proposing changes. Windows drive paths and Docker Desktop aliases can describe the same host location; normalize carefully without assuming equivalence.
- Keep existing database bind mounts as observed evidence. A future default of named volumes is not permission to relocate the running databases.
- Map each app's database, authoritative files, derived cache, logs and secret carrier separately.
- Do not replace original mount paths with new paths during a restore unless the application supports the mapping and content checks pass.
- Treat anonymous volumes, external drives, named secret volumes and container-managed controller data as explicit entries, not incidental leftovers.

## Secret carriers found

| Carrier | Examples | Recovery requirement |
| --- | --- | --- |
| Environment/interpolated files | App/database passwords and API integration keys | Reference-only public examples; protected private values |
| Application config files | Nextcloud PHP config, Vaultwarden JSON, Matrix YAML, code-server password config | Allowlisted nonsecret settings plus encrypted complete recovery copy |
| Key files | AFFiNE private key; Matrix signing key; developer SSH/GPG keys | Preserve exact original keys for restoration; generate new keys for fresh installs |
| Named secret volume | Firefly app/database/cron credentials; code-server secure directory | Explicit encrypted export; not recovered by cloning Compose |
| Windows protection | Kuma push-secret CLIXML and Firefly DPAPI backup | Portable recovery method independent of failed Windows identity |
| Application database | Users, integration settings, monitoring history, workspace identity | App-aware backup; do not infer all GUI settings from environment alone |
| External account | Cloudflare ingress/DNS and Tailscale policy/identity | Owner-controlled export/re-enrollment and separate authorization |

Names and purposes can be public; values and user-specific identifiers cannot. A file named `.env.sanitized` is not automatically safe to publish: URLs, emails, identifiers or unexpected credential names may remain.

## Phase 2 input contract

The planner can now present all 21 modules, resolve logical storage roles, identify custom-build/native/external dependencies and show unsupported/manual steps. It must not generate deployable templates from these prose runbooks or automatically reuse reference-host credentials.

The original examples remain non-executable. Template extraction, live adoption, data migration, release locking and restore proof are later, separately tested operations.
