# Security policy

This repository is currently a pre-release blueprint, not a production installer.

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

The current validator performs structural and limited publication checks. It is not a complete secret detector, vulnerability scanner, or security audit. A dedicated secret scanner and dependency/image checks are release gates in later phases.
