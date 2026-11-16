# code-server development module

This Phase 7 module produces a reviewed, architecture-aware browser development environment without adopting an existing workspace or copying private credentials into Git. It is a candidate for fresh installations and isolated recovery rehearsals, not an automatic production upgrade.

## What it builds

- code-server `4.145.0` from an immutable multi-platform GHCR index.
- Explicit amd64 and arm64 platform digests.
- Node.js `24.19.0` from the correct architecture archive after an official SHA-256 check.
- C/C++, Python, Go, Rust, Java, PHP, Ruby and common database/client tools.
- Eighteen version-pinned developer extensions staged at image-build time.
- Copy-once autosave, window/session restoration, persistent-terminal policy and local-history defaults.

The APT package names are reviewed, but Debian repository snapshots are not yet locked. The immutable base image and recorded trial evidence make the candidate substantially more reproducible than the observed private build, but a future package-lock step remains necessary for byte-identical rebuild claims.

## Security and persistence

The generated service is loopback-only and has no Docker socket, host devices or privileged mode. It drops all Linux capabilities, enables `no-new-privileges`, uses an init process, bounds CPU/memory/PIDs, rotates logs and checks `/healthz`.

Four scopes persist independently:

| Scope | Container path | Contains |
| --- | --- | --- |
| Config | `/home/coder/.config` | Private code-server authentication configuration |
| Local state | `/home/coder/.local` | Settings, editor state and installed extensions |
| Secure state | `/home/coder/.secure` | Owner-managed SSH/GPG material |
| Workspace | `/home/coder/project` | Source repositories and build products |

Config, secure state and private repositories must be encrypted outside Git. The module never generates or displays a production password, Git token, SSH key or GPG key. Public access remains a separate Phase 8 concern.

## Planning commands

Copy `modules/code-server/selection.example.json` to private storage and select new, non-overlapping state and workspace roots. Then run:

```powershell
python -m homelab code-server plan `
  --selection C:\private\code-server-selection.json `
  --output C:\private\code-server-plan.json

python -m homelab code-server render-compose `
  --plan C:\private\code-server-plan.json `
  --output C:\private\code-server-compose.json
```

These commands do not create directories, build an image or deploy a container. Create the private config file only after reviewing the rendered plan. The reusable definition intentionally binds `127.0.0.1`; use an authenticated reverse proxy or tunnel rather than publishing the editor directly.

## Extension behavior

Extensions are installed into an immutable seed during the image build and copied into an empty persistent extension directory on first start. Existing settings and extension directories are never overwritten. Additional owner-installed extensions may persist, but they are not part of the reproducible manifest until explicitly pinned and reviewed.

code-server uses an Open VSX-compatible marketplace by default. Marketplace availability and extension licensing can differ from desktop Visual Studio Code, and not every desktop extension is expected to work in a browser-hosted server.

## Backup and recovery

A consistent recovery set contains all four persisted scopes plus the reviewed build/selection metadata. Stop code-server before capturing editor databases and extension state. SSH/GPG keys and repository credentials require encrypted transport and separate recovery-key custody.

Recovery is successful only after an independent root serves `/healthz`, compiles synthetic content server-side and preserves settings, extension and workspace hashes across recreation. Validate sanitized evidence with:

```powershell
python -m homelab code-server validate-evidence `
  --plan C:\private\code-server-plan.json `
  --evidence C:\private\code-server-evidence.json
```

## Reference production migration

Version `0.8.0-alpha.4` closes the previously recorded tag/version blocker on the reference Windows host. Production state was captured while code-server was stopped, encrypted using the reviewed Restic 0.19.1 binary and fully checked. The recovery key and repository live on different physical disks. An independent restored 4.145.0 candidate passed exact runtime identity, 20 persisted extensions, server-side compilation, HTTP health and restart persistence before production changed.

The live container now uses the reviewed `localhost/homelab-code-server:4.145.0-amd64` image, retains all four state mounts and the existing resource ceilings, and publishes `127.0.0.1:8443` only. Local and public health passed after cutover and a Compose restart. The old image, exact Compose rollback copy and encrypted state recovery remain available. See the [controlled migration runbook](code-server-migration.md).

This is reference-host evidence, not automatic adoption permission for another installation. The encrypted repository and key are on separate local disks but are not yet off-machine or offline custody.
