# Contributing

Start with [the roadmap](docs/roadmap.md). Changes must preserve the distinction between proposed, implemented, and runtime-tested capabilities.

1. Work only in this repository or explicitly approved disposable test environments.
2. Use synthetic data and placeholder domains such as `example.com`.
3. Update the catalog, runbook, tests, and compatibility evidence with each module.
4. Run the validator and unit tests before proposing changes.
5. Explain migration risks, required privileges, data ownership, and recovery behavior.
6. Do not silently change public endpoints, credentials, application versions, or existing Compose project names.

Imported upstream patches require provenance, licensing review, a reproducible build, and a documented update strategy. Do not publish compiled local images without the corresponding permitted build instructions.

Keep release notes product-focused and factual. Passing static CI on three operating systems is not proof that Docker workloads or GPU acceleration work on those operating systems.

## Version and release workflow

Every completed phase or independently useful update must end with a coherent reviewed commit. Use concise product-focused commit subjects and keep unrelated work in separate commits.

- Use `-alpha.N` while a phase is still being built.
- Use `-rc.N` when the phase is integrated and ready for final validation.
- Publish a stable milestone only after its documented acceptance gates pass.
- After a stable release, use a patch version for compatible fixes and documentation updates, a minor version for backward-compatible features, and a major version for incompatible changes.
- Create one annotated Git tag and one GitHub release for each published version. Mark alpha and release-candidate versions as prereleases.
- Never reuse or move a published tag. Correct a release with the next version.

Before committing, review the staged allowlist and run the repository, phase-specific, publication, regression and whitespace checks. Push the reviewed commit, require its GitHub Actions matrix to pass, then create the matching tag and release from that exact commit. Release notes must describe supported behavior, evidence and remaining limitations without process-tool attribution.
