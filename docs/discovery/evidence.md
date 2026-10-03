# Phase 1 evidence register

Discovery date: 2026-10-03, reference Windows host. No production start, stop, restart, upgrade, backup, restore, data migration or account change was performed.

## Evidence classes

| ID | Evidence collected | What it proves | What it does not prove |
| --- | --- | --- | --- |
| E01 | Filtered Docker inspect and image inspect | Runtime image ID/digest/architecture, mount sources/targets, port bindings, limits, ownership labels, state | Content correctness, security of every setting, future registry availability |
| E02 | Compose source labels and `compose config --format json`, immediately reduced to metadata | Current resolvable file combinations, service/dependency/build declarations, environment names | Historical shell/environment used to create containers; identical regeneration |
| E03 | Selected configuration key names, Dockerfiles, scripts, local operational documents | Customization intent, file-based secret carriers, source/build requirements | Application database settings not queried; secrets not exported |
| E04 | Windows services, scheduled tasks, listener/process metadata and Jellyfin startup registration | Native lifecycle owner, task result/status and current listeners | End-to-end public reachability or unattended boot test |
| E05 | Existing backup script source and selected backup-metadata files | Actual script behavior and recorded verification result | New backup/restore success, complete off-host recovery or nonempty-content coverage |
| E06 | Beszel Git revision/status, local license headers and build files | Upstream revision, tracked/untracked patch scope, local MIT notices, hard-coded architecture | Clean reproducible build or permission to redistribute every transitive dependency |

The public [discovery ledger](../../catalog/discovery.json) and [runbook index](runbooks.md) are manually curated from these sources. Raw reports are deliberately not committed. Actual image digests, paths and Compose source hashes remain in the private report.

## Coverage reconciliation

- 54 containers observed: 53 running, one AFFiNE migration container exited successfully.
- 52 containers mapped to the 21 catalog modules; four modules are native-only.
- Two personal, controller-generated Coolify applications are explicitly excluded from reusable templates.
- 19 distinct Compose source combinations found; 17 resolve on the host.
- The two unresolved combinations point at transient controller build-artifact paths. Their running containers were inspected; the missing source files are not silently invented.
- Coolify appears in two source combinations under the same project name. This is tracked as configuration drift, not two independent installations.
- 14 relevant scheduled tasks discovered. System/third-party tasks outside the declared service scope were not exhaustively audited.
- A final snapshot matched all 54 original container IDs, states, start times and restart counts: zero observed lifecycle changes during the audit.

## Private collection

The implemented Windows/PowerShell 7 collector reads metadata only and writes a new JSON report outside the checkout. Use an owner-protected private directory; this report contains deployment paths and identities even though environment values are excluded.

```powershell
# Example only: choose actual approved paths on your machine.
./tools/Collect-ReferenceInventory.ps1 `
  -StackRoot 'C:\YourStacks' `
  -OutputPath 'D:\HomelabPrivate\discovery\inventory.json'
```

It refuses existing output files and output inside the checkout. It does not export full container environment values, Docker health-command text, service command lines, scheduled-task arguments, labels beyond ownership fields, database rows, documents or credential files. Compose interpolation temporarily reads values in memory; only selected metadata is retained. Failed Compose resolution is recorded as unresolved, not healthy.

The collector is a Windows reference-audit utility, not the Phase 2 cross-platform doctor or a deployment tool. A report may expose private directory/container/project names and must never be attached to a public issue without review. Hashes provide change detection, not encryption or proof of safety.

## Discovery boundaries

- No account-level Cloudflare or Tailscale export, DNS change, registry pull, GPU workload or public login test.
- No vault contents, financial transactions, media originals, chat messages or document payloads were read.
- No application database enumeration to infer every GUI setting. Runbooks identify database-owned settings as private state.
- Native exact version/dependency locking, remote-provider policy export and off-host recovery remain explicit follow-up work.
- Existing experiment directories for a budget trial, legacy media-request configuration, standalone office, speed testing and a separate reverse-proxy trial are excluded. No corresponding running containers were found in this snapshot. No files were deleted or enabled.
- No custom third-party source was imported. Source extraction is gated by provenance, licensing and sanitization.

The inventory is sufficient to plan the coordinator and module contracts, not sufficient to declare all applications reproducibly deployable today.
