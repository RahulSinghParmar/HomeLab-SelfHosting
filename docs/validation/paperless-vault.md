# Paperless encrypted vault 0.6.0-alpha.2 validation

Date: 2026-10-19

Platform: Windows Docker Desktop, Linux/amd64 engine 29.8.2, Compose 5.6.0

Restic: 0.19.1 windows/amd64, supplied as a standalone validation binary
Data: one generated non-personal PDF only

## Decision

**Go for the bounded encrypted-vault prerelease. No-go for production adoption, off-host disaster-recovery claims or stable 0.6.0.**

The trial built on the released `0.6.0-alpha.1` application-consistent backup. It did not point at the existing personal deployment, read its documents, change its backup schedule or restart its services.

## Tool and key checks

- The official restic 0.19.1 Windows amd64 archive SHA-256 matched `da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d`.
- The extracted executable SHA-256 matched `b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830`; its version output identified Windows amd64.
- No global restic installation was used.
- Key generation produced matching operational and recovery files without displaying their value.
- An attempted key file under an unsuitable inherited `C:\Docker` ACL failed closed. The partial exact file was removed without reading it. The successful trial used a private user temporary root; no permission rule was weakened.
- The plan and status output contained only key references and explicit `off_host_verified: false` state.

The two trial key files were on the same Windows volume, so this run does not prove independent off-device key custody.

## End-to-end evidence

The source project on loopback port 18012 started three healthy digest-pinned services. It consumed one generated PDF, recovered searchable marker text, saved title `Phase 5 Recovery Fixture` and tag `phase5-recovery`, and matched the original SHA-256 `9f8dbce3c8ea723da3a8cc8e6ba6a015a9f68e28197114a33f8de880c0e0aaac`.

The application-aware backup then passed exporter, semantic inventory, readable PostgreSQL custom archive, data/media/export copy and complete hash verification. The vault accepted that nonempty manifest only after producing a deterministic snapshot plan. Restic created one encrypted snapshot and a complete `check --read-data` passed.

The adapter restored the encrypted snapshot into a new absent private directory, revalidated all files plus the manifest and semantic fingerprint, and tagged the snapshot `recovery-verified`. The decrypted set was then imported into a second unrelated Paperless project on loopback port 18013 and six new volumes. The restored application reported the same single document, title, checksum and content fingerprint, and remained verified and healthy after a complete stop/start.

The retention preview returned 7 daily, 4 weekly and 3 monthly points, protected the restore-verified snapshot and performed no prune. All environment-provided `RESTIC_*` variables were excluded by the adapter.

## Cleanup and production safety

Both disposable projects were stopped and removed. Twelve exact synthetic volumes were deleted only after their module/plan labels and zero container attachments were checked. The private trial root, plaintext backup, both key files, encrypted repository and standalone restic binary were removed after exact-path and reparse-point checks. Zero `hl-paperless-*` containers and zero candidate-labelled volumes remained.

After cleanup, the existing production Paperless web, PostgreSQL and Valkey containers were still running and healthy on the same immutable digests. Point-in-time memory use was approximately 607 MiB, 49 MiB and 10 MiB respectively. No production mutation was made.

## Automated evidence

Thirteen focused vault tests cover deterministic secret-free plans, separate matching keys, confirmation-gated generation, initialization identity, manifest binding, encrypted store, tampered-reference refusal, restore-before-tag, latest-snapshot check binding, restore-gated dry-run retention, missing-tag refusal and malformed restic output. The offline Phase 5 validator checks the CLI surface, public evidence, exact image digests, reviewed release URL and both restic checksums. The complete repository regression and cross-platform CI matrix are release gates.

## Unmet gates

- The tested repository and both keys were local and disposable; independent media, off-host repository, recovery-key loss and hardware-failure recovery were not tested.
- Retention apply/prune is confirmation-gated and regression-tested but was not applied to the single live snapshot.
- There is no scheduler, automatic tool download/update, production-backup migration or credential rotation.
- Production content, API-token recreation, mail ingestion, representative OCR, populated-library performance, upgrades, Linux/macOS/ARM64 restic/runtime and clean-machine recovery remain unverified.
- AFFiNE, Nextcloud, Firefly III, Vaultwarden and Karakeep remain separate later Phase 5 substages.
