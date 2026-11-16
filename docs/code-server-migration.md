# code-server encrypted production migration

This Phase 7 contract turns a candidate image into a controlled production change only after recovery works. The public command surface plans and validates evidence; it never stops, backs up or replaces a production container by itself.

## Review commands

```powershell
python -m homelab code-server-migration plan `
  --policy modules\code-server\migration.example.json `
  --output C:\Private\code-server-migration-plan.json

python -m homelab code-server-migration validate-evidence `
  --plan C:\Private\code-server-migration-plan.json `
  --evidence C:\Private\code-server-migration-evidence.json
```

The reference policy records the observed source defect—image tag `4.144.0` carrying a 4.131.0 binary—and the reviewed 4.145.0/Node 24.19.0 candidate. Another installation must create a new policy and evidence set rather than reuse the reference claim.

## Required order

1. Audit the current runtime without reading credentials or workspace content.
2. Verify the candidate image identity and isolated recovery-trial evidence.
3. Stop code-server and archive config, local editor state, secure Linux volume, workspace and build metadata.
4. Restart the source immediately.
5. Encrypt the archive using the checksum-locked Restic 0.19.1 binary and run `check --read-data`.
6. Keep the repository, source and recovery key on separate physical disks.
7. Decrypt into an independent root and verify hashes, exact versions, extensions, server-side compilation, HTTP health and restart persistence.
8. Save an exact Compose rollback copy.
9. Recreate production from the reviewed candidate without changing mounts or limits; bind its direct host port to loopback.
10. Verify local and public health, compile server-side, restart through Compose and verify again.
11. Remove every plaintext staging and restored copy.

If any gate fails after the Compose edit, restore the exact previous Compose file and cached image. If persistent state is incompatible, restore all four scopes together from the matching encrypted snapshot; do not selectively roll back editor databases or credential directories.

## Recovery custody

The reference execution placed the encrypted repository and recovery key on separate local physical disks. That protects against failure of the source NVMe or backup disk individually, but both remain attached to the same Windows host. Copy the encrypted repository off-machine and move a recovery-key copy to owner-controlled offline custody before calling it site-loss disaster recovery.

The migration validator contains no repository path, key path, password, token, workspace filename or private source content.
