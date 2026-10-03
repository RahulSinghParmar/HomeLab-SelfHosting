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
