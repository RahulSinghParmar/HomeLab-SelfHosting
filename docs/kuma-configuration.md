# Uptime Kuma desired-state configuration

This unreleased Phase 4 extension manages the **isolated Kuma module only**. It does not discover, import or edit the existing household Kuma deployment. The workflow is deliberately fail-closed: if the isolated project contains a monitor or notification whose name is not declared in the reviewed file, the operation stops instead of adopting or deleting it.

## Supported configuration

- HTTP and HTTPS `GET` or `HEAD` monitors, bounded to 64 entries.
- Explicit intervals, retries, timeout, redirects, TLS verification and accepted status-code ranges.
- One named status page with up to 16 groups and explicit monitor membership.
- Up to 16 webhook or SMTP notification profiles.
- Exact secret references stored in a separate owner-private JSON file outside Git.
- Reconcile, drift inspection and explicit notification delivery tests against pinned Uptime Kuma 2.5.5.

Docker, push, ping, DNS, database, browser and certificate-only monitors are not implemented. Notification schedules, maintenance windows, tags, proxy credentials, custom webhook bodies, OAuth providers and provider-specific integrations are also outside this contract. Configure those manually only if you accept that the desired-state inspection will refuse the resulting foreign state.

## Files and trust boundaries

[`monitor-config.example.json`](../modules/uptime-kuma/monitor-config.example.json) is a public, versioned example. Copy it and edit names, endpoints, intervals, groups and secret **identifiers**. `validate-config` redacts every monitor and inline webhook URL before displaying the document.

[`secrets.example.json`](../modules/uptime-kuma/secrets.example.json) is a shape example, not usable credentials. Put the real copy outside Git on a local filesystem with owner-private permissions. Its `values` keys must match the configuration's secret references exactly: missing and unused values are both refused. Secret values are passed to the pinned client through stdin only and are never included in normal command output, configuration hashes, backup summaries or documentation.

The Kuma application still stores the provider configuration in its private database because that is required to deliver alerts. Therefore the stopped-state backup contains notification secrets and remains sensitive even though its manifest exposes only counts and one-way fingerprints.

## Review and apply

Run from the repository root. The paths below are examples; use the private plan and storage paths created for your isolated module.

```powershell
python -m homelab kuma validate-config `
  --config modules/uptime-kuma/monitor-config.example.json
```

Copy both examples to private locations, replace the placeholder webhook endpoint, then review the redacted output and the complete plan ID. Applying may create or update only the declared resources; it never deletes foreign resources.

```powershell
python -m homelab kuma apply-config `
  --plan D:/HomeLab-Trials/kuma-plan.json `
  --config D:/HomeLab-Trials/kuma-monitor-config.json `
  --secrets D:/HomeLab-Trials/kuma-secrets.json `
  --confirm FULL_PLAN_ID

python -m homelab kuma inspect-config `
  --plan D:/HomeLab-Trials/kuma-plan.json `
  --config D:/HomeLab-Trials/kuma-monitor-config.json `
  --secrets D:/HomeLab-Trials/kuma-secrets.json
```

`inspect-config` performs no intended mutation but must read the private values to compare the stored provider configuration exactly. Successful output includes the configuration hash, logical IDs, safe display names, provider types and counts; it does not include URLs, headers, usernames or passwords.

The original `seed` command remains for the alpha.2 synthetic fixture. After adopting the desired-state workflow, use `apply-config` and `inspect-config` consistently; the old seed's intentionally stricter 20-second/no-notification contract may report drift.

## Test alert delivery

The test command causes **real provider delivery**. The example can use `http://fixture:8080` as a harmless isolated webhook target. SMTP configuration sends a real message to the private `to` value. Review the provider recipients and use the same full plan confirmation required for other mutations.

```powershell
python -m homelab kuma test-notifications `
  --plan D:/HomeLab-Trials/kuma-plan.json `
  --config D:/HomeLab-Trials/kuma-monitor-config.json `
  --secrets D:/HomeLab-Trials/kuma-secrets.json `
  --confirm FULL_PLAN_ID
```

A successful API callback proves that Kuma accepted the test request. For SMTP or an external webhook, confirm receipt at the destination as separate end-to-end evidence. Never treat a provider callback alone as proof that an email reached an inbox.

## SMTP shape

SMTP uses private references for username/password and addresses. `from_secret` and `to_secret` are required; username/password are optional for a trusted relay. Use port 465 with `secure: true` for implicit TLS, or typically 587 with `secure: false` and `disable_starttls: false`. Keep `ignore_tls_errors: false` unless a separately reviewed private-CA design requires otherwise.

The configuration validator accepts an optional subject/body but intentionally does not guess Gmail app-password, relay, SPF, DKIM or DMARC settings. Those are account/domain responsibilities and must be tested at the destination.

## Backup and recovery

New backups use `kuma-stopped-backup-v2`. The full application data and private credentials are retained; semantic evidence accepts the declared HTTP monitor set plus webhook/SMTP profiles and records only provider type/name fingerprints. Version 1 synthetic-only snapshots remain verifiable for recovery compatibility.

Always stop, back up, restore into a fresh isolated project, authenticate, run `inspect-config`, load the rendered status page, and confirm a real test delivery. A copied archive without this rehearsal is not a verified recovery.

See the [Windows Docker Desktop validation record](validation/kuma-configuration.md) for the pinned webhook and recovery evidence. SMTP structure is regression-tested, but real inbox delivery remains specific to the operator's relay/account.
