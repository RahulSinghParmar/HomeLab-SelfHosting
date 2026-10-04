# Security policy

This repository is currently a pre-release blueprint, not a production installer.

The experimental Glance command operates a new loopback-bound container on a dedicated bridge network. Outbound connectivity is allowed; this is not an egress firewall. It does not mount the Docker socket or modify existing applications. The upstream image defaults to root inside the container, constrained by a read-only filesystem, dropped capabilities, no-new-privileges and resource limits. The digest is reproducible, not a claim of current vulnerability clearance. Read the [Glance boundaries](docs/glance-module.md) before use. Localhost access is not user authentication; other local processes/users can reach the dashboard.

Version 0.4.0's opt-in synthetic executor creates local test credentials and owned files only. Read its [security and recovery boundaries](docs/safe-execution.md) before use. Private files are permission-protected, not encrypted, and privileged/same-account tampering is outside the threat model. Do not publish sandbox state or treat its backup-staging directory as a recovery copy.

Never publish credentials or recovery bundles in issues, pull requests, screenshots, logs, or workflow artifacts. If a credential is exposed, revoke or rotate it first; deleting the file or commit is not sufficient.

Report vulnerabilities through the repository's private vulnerability reporting feature if enabled. If unavailable, open a minimal issue requesting a private contact without disclosing exploit details or sensitive configuration.

## Release requirements

- Review an allowlist of staged files, not only `.gitignore`.
- Scan generated examples, documentation, images, Git history, and release artifacts for secrets and private identifiers.
- Pin and review third-party images and CI actions; document update and rollback procedures.
- Keep Docker API access restricted. A mounted Docker socket, including a read-only socket bind, can still provide powerful daemon access; filesystem read-only is not API authorization.
- Run applications without unnecessary privileges. Record justified exceptions rather than applying incompatible blanket restrictions.
- Do not publish databases, Redis, administration APIs, metrics endpoints, or Docker ports by default.
- Backups and exported support bundles are sensitive even when credentials have been removed.
- Never disable TLS verification to make a deployment appear healthy.

The repository validator performs structural checks. `python tools/check_publication.py --history` checks the staged index and locally reachable history for a small explicit set of credential patterns and prohibited artifact paths, without printing matched values. It requires a Git checkout and intentionally fails on unreviewed binary artifacts. A synthetic credentialed-URL fixture has one narrow allowlist entry.

These tools are not a complete secret detector, vulnerability scanner, or security audit. Manual staged-diff review and installation-specific private-identifier checks remain mandatory. A dedicated maintained secret scanner and dependency/image checks are release gates in later phases. No raw private reports are uploaded by CI.
