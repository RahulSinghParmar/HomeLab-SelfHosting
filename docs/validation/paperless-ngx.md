# Paperless-ngx 0.6.0-alpha.1 validation

Date: 2026-10-16
Platform: Windows Docker Desktop, Linux/amd64 engine 29.8.2, Compose 5.6.0
Data: generated non-personal PDF only

## Decision

**Go for the bounded Paperless-ngx prerelease. No-go for production adoption or completed Phase 5.**

The existing Paperless deployment was inspected read-only. Its three services were healthy and digest-pinned. Point-in-time use was approximately 710 MiB for Paperless, 61 MiB for PostgreSQL and 20 MiB for Valkey. Twelve scheduled/manual backup directories were present across daily, weekly, monthly and manual tiers, but every recorded semantic inventory contained zero documents. Those reports prove automation and empty-database restoration, not representative document recovery. No production container, file, task, configuration or backup was changed.

## Isolated runtime evidence

The candidate created two unrelated projects on distinct loopback ports. The original project passed:

- digest-pinned fresh start with healthy Paperless, PostgreSQL and Valkey;
- internal-only database/broker network and no database/broker host ports;
- one generated PDF consumed with searchable marker text;
- persisted title and tag edit;
- Paperless checksum and stored-original SHA-256 both equal to `9f8dbce3c8ea723da3a8cc8e6ba6a015a9f68e28197114a33f8de880c0e0aaac`;
- application quiesce followed by successful exporter, semantic inventory, readable PostgreSQL custom archive, filesystem/configuration hashing and automatic healthy restart.

The first exporter test exposed two real integration errors before release: an ordinary Compose one-off command started the image supervisor instead of the requested tool, and the exporter required its target directory to exist. The final implementation uses an explicit `s6-setuidgid` management-command entrypoint and creates the exact private staging directory first. Interrupted one-off resources were removed by exact name; the isolated application recovered healthy.

The second project initialized clean volumes, stopped its application processes, imported the supported document-exporter set, and restarted healthy. Its semantic inventory matched the backup exactly: one document, title, tag, searchable marker, Paperless checksum and stored-file SHA-256. A subsequent complete stop/start retained the verified inventory and healthy state.

After evidence capture, all three disposable projects were stopped. Their exact owned containers and networks were removed; 18 synthetic-only volumes were deleted only after project/module labels and zero attachments were verified. Private trial roots, plans, generated credentials and the synthetic backup were then removed from the dedicated validation directory. The existing production project was not selected by any cleanup operation.

## Backup contents and restore choice

The tested local staging set contains:

- Paperless document-exporter result;
- PostgreSQL custom dump, validated with `pg_restore --list`;
- data, media and export trees;
- private Compose configuration, sanitized configuration and generated credentials;
- exact image digests, consistency-step results, content inventory and SHA-256 maps.

The supported exporter/importer path is the selected portable restore method. Raw database/filesystem material is retained as a separate same-point set and was not overlaid onto the importer result. The restored project's private state records a verified manifest binding and semantic fingerprint.

## Unmet gates

- Plaintext staging is not an encrypted off-host backup.
- Restic installation, independent password/key custody, repository check, snapshot retention and restore are not implemented.
- API tokens require regeneration after importer recovery.
- Production backup tests still have zero documents and have not been replaced or modified.
- Public/authentication, mail ingestion, representative OCR, populated-library performance, upgrade/rollback, Linux/macOS/ARM64 runtime and clean-machine recovery remain unverified.

The next Phase 5 decision is the encrypted Paperless recovery layer or, after a separate go-ahead, the AFFiNE substage. AFFiNE work must begin with its own current backup and isolated recovery rehearsal; Paperless evidence cannot be reused for it.
