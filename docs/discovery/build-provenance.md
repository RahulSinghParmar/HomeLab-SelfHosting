# Custom build and licensing ledger

No upstream application code, compiled image, binary, production Compose file or private configuration is redistributed by this release. This ledger records what must be made reproducible in later module phases.

| Build/integration | Evidence | Reproducibility gap | Import gate |
| --- | --- | --- | --- |
| Beszel hub/agent | Local upstream revision `6e3fd90834309213aca32f2ff5fb0b027661c39a`; six tracked files modified plus new Windows collectors/build files and vendored PocketBase | Build stages float; hub/agent target amd64; untracked sources not captured by diff | Review full patch, lock source/toolchain, preserve Beszel and PocketBase MIT notices, review transitive licenses |
| Nextcloud app/cron | Dockerfile starts with `nextcloud:stable`, installs SMB packages | Floating base and apt dependencies; separate local app/cron image IDs | Pin compatible upstream release/digest; retain upstream notices and package licensing |
| code-server | Upstream 4.131.0 base digest pinned; Node download version/hash present; extension manifest present | Linux x64 tarball hard-coded; apt packages and extensions not fully version-locked | Architecture-aware downloads, reproducible extension policy, preserve upstream/extension licenses |
| Host metrics | Custom Python collectors/API files and PowerShell tasks referenced by Compose/startup | Hard-coded Windows paths and private app integrations; provenance not independently established for every helper | Review source file by file, sanitize, add fixtures and platform adapters before import |
| Coolify Windows adapter | Management scripts, testing-host image, bind-mounted updater wrapper and multiple Compose sources | Controller/root source drift and VM-specific path aliases | Reconcile lifecycle/source ownership; preserve upstream-supported Linux baseline and label custom adapter experimental |

Beszel's local `LICENSE` identifies MIT with upstream attribution; the vendored PocketBase `LICENSE.md` also identifies MIT with its own attribution. These headers were read locally. This is not a complete legal audit of every dependency or permission to relicense the entire application under this repository's license.

## Extraction rules

1. Record exact upstream release/commit and obtain permitted source through its canonical upstream.
2. Export only reviewed modifications, including required new files; do not archive an entire dirty working tree.
3. Preserve notices and document dependency/extension license constraints.
4. Separate code from credentials, compiled artifacts, databases, personal settings and generated data.
5. Build a new isolated image and test it without replacing production tags.
6. Record platform-specific image digest, source revision, build recipe and test evidence.

Observed runtime image IDs and registry digests are retained privately. They describe the current installation, not a guarantee of future pullability or a supported lockfile for new deployments.
