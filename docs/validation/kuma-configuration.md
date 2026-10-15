# Uptime Kuma desired-state validation

Date: **2026-10-14**

Scope: unreleased Phase 4 monitor/status-page/notification extension

Host: Windows, Docker Desktop local `desktop-linux`, Linux amd64 engine
Application: pinned Uptime Kuma **2.5.5** digest from `modules/uptime-kuma/image.json`

No observed household/production Uptime Kuma container, database, monitor or notification was modified. Validation used two newly owned projects on loopback ports 13001 and 13002 plus a synthetic internal fixture. The already-running `uptime-kuma` service on loopback port 3001 remained outside the module ownership boundary.

## Static and regression gates

- Repository structure validator: pass, 21 catalog modules and 55 documents at the time of validation.
- Publication guard: pass, 103 indexed/history file versions; manual review still required.
- Complete Python suite: **254 passed, 2 environment skips**, no failures.
- Focused Kuma suite: **42 passed**, including closed schemas, endpoint redaction, exact secrets, pre-host confirmation gates, SMTP/webhook mapping, backup fingerprints and legacy v1 verification.
- Python compilation and Node syntax validation: pass.
- Public example validation: pass; monitor and inline notification endpoints were redacted.

## Fresh apply and inspection

The trial initialized its random private account through the original synthetic seed, then applied `monitor-config.example.json` with an owner-private webhook value pointing only to `http://fixture:8080`.

- Configuration hash: `3e665d13f64db8cf5df734cc37aade5a2bd85c66dff262525c9c9eb2cc0e6d2a`.
- First apply: pass; two monitors, one webhook profile and one `blueprint` status page.
- Repeated apply: pass with the same logical objects and hash; no duplicate monitor or notification.
- Independent `inspect-config`: pass with `applied: false` and the same hash/counts.
- `test-notifications`: pass; the pinned server accepted and delivered one webhook test to the isolated fixture.
- Rendered `/status/blueprint`: HTTP 200 and contained both the configured page title and fixture monitor text.

The live run exposed one pinned-interface detail before success: `notificationList` exports provider configuration as a JSON string in the bean's `config` field. The adapter was corrected to normalize this representation before exact drift comparison. Errors continued to expose only a bounded stage name, never the provider endpoint or credentials.

## Backup and independent restore

Both source services were stopped before backup. The emitted `kuma-stopped-backup-v2` evidence reported:

- 2 HTTP monitors;
- 1 supported notification profile;
- 1 user and 1 status page;
- 16 successful heartbeat rows at snapshot time;
- monitor fingerprint `bf5f9f59a039cae303f3f0a5322b8c50801be85a3155874d365824da895b8da3`;
- notification name/type fingerprint `bbdaf7cff1c13f0ca789f1254e0b65c86604897757660d2a629fa99814eee7b4`.

The snapshot was restored into a new named volume and fresh project on loopback port 13002. Without reapplying or reseeding:

- `inspect-config` matched the original configuration hash and all declared objects;
- notification test delivery succeeded again through the restored provider configuration;
- the restored status page returned HTTP 200 with the expected rendered title and monitor text.

This verifies the tested HTTP/webhook path and stopped-state recovery on this host. SMTP field mapping is regression-tested but no real SMTP account or inbox was used, so SMTP destination delivery remains operator-specific evidence. Cross-platform runtime certification and upgrades beyond pinned 2.5.5 remain out of scope.

After evidence capture, both disposable projects were stopped and removed using their reviewed plan IDs. Exact owned test volumes and private trial artifacts were then eligible for scoped cleanup; production services were not selected.
