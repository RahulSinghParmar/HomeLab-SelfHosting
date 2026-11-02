# Phase 5 encrypted recovery kit

Phase 5 closes with a recovery kit contract for Paperless-ngx, AFFiNE, Nextcloud, Firefly III, Vaultwarden and Karakeep. The kit is a recoverable set of runtime artifacts and instructions—not an archive committed to Git.

## Kit layout

For each application, retain:

1. The exact tagged repository source and application runbook.
2. One Restic encrypted repository containing a verified application-consistent backup.
3. One portable recovery manifest bound to the repository and restore-verified snapshot.
4. One recovery key held separately from the encrypted repository.
5. One sanitized clean-runner proof showing that actual nonempty test content was restored and checked through the application.

The machine-readable contract is `modules/phase5/closure.json`. It declares the consistency method, authoritative material, fixture marker and application-level proof fields for every module.

## What “restore validated” means

A backup file, successful command or HTTP health response is insufficient. The hosted recovery workflows rebuild each application on a different clean runner, then verify its content:

| Application | Restored-content proof |
| --- | --- |
| Paperless-ngx | Nonempty document inventory, application import and restart persistence |
| AFFiNE | Rendered note title/body, reload, independent session and restart persistence |
| Nextcloud | Exact WebDAV fixture checksum and restart persistence |
| Firefly III | Finance transaction semantics, exact attachment, exports and restart persistence |
| Vaultwarden | Decrypted secure note, exact attachment download, independent sessions and restart persistence |
| Karakeep | Rendered bookmark, full-text search, exact asset, rebuilt search index and restart persistence |

Every fixture is synthetic and bounded. No personal document, finance record, password-vault item, note, cloud file or bookmark is included in source control or hosted-runner artifacts.

## Encryption and key custody

The six vaults use the reviewed Restic release and perform full repository data reads. Hosted workflows transport only the encrypted repository and nonsecret recovery manifest. The recovery key is injected independently and is never included in the transport artifact.

For an owner deployment, follow the separate [owner-operated backup design](owner-operated-backups.md): one primary and one replica off-host repository, plus two offline recovery-key copies on distinct devices. Phase 5 completion certifies the recovery toolkit and synthetic test contract; it does not assert that an owner's production media or keys already exist.

## Retention

The common policy is:

```text
7 daily snapshots
4 weekly snapshots
3 monthly snapshots
```

Retention preview is non-destructive. Apply is permitted only after the selected snapshot has passed full-data checking and application restore verification, and the protected restore-verified snapshot must remain available.

## Closure validation

```sh
python tools/validate_phase5.py
python tools/validate_phase5_closure.py
python -m unittest discover -s tests -v
```

The final manual `Phase 5 integrated recovery review` must also pass all six prepare jobs and all six independent recover jobs on the exact release commit. Standard CI alone does not execute Docker application recovery.

## Deliberate boundary

Version `0.6.0` completes the reusable Phase 5 recovery-kit milestone. It does not install owner schedules, create production repositories, generate real keys, copy personal data or certify a production backup deployment. Those actions require the private owner policy, media, credentials and explicit activation approval.
