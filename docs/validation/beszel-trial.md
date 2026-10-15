# Beszel isolated trial — validation in progress

Candidate bounded Phase 4 milestone; **not yet released or declared complete**. Evidence collected 2026-10-04 and 2026-10-05 on Windows Docker Desktop with a local Linux amd64 engine. All identities and data below belong to an isolated trial, not an existing homelab hub.

## Completed evidence

- Upstream hub and agent 0.21.0 pinned by per-platform manifest digest in `modules/beszel/image.json`.
- Only the hub has a published loopback port; agent has no published port, socket, native host mount or device access. Both volumes and network have reviewed ownership labels.
- Fresh synthetic account, public-key pairing and one agent registration succeeded. Repeated `seed` and `up` succeeded without duplicating the registered system.
- Authenticated API collected nonempty CPU, memory, disk and network history; absent GPU/native-service exposure is explicitly reported as unsupported by this trial rather than healthy zero usage.
- Stopping only the agent produced **up -> down -> up** with fresh history after restart; hub was not restarted to force reconnection. Email/push delivery was not configured or tested.
- Initial idle sample: hub **11.49 MiB / 256 MiB**, agent **3.773 MiB / 128 MiB**, both **0.00% CPU**. This is a point-in-time sample, not a load benchmark or guaranteed size.
- The initial backup test caught SQLite read-only inspection creating `-wal`/`-shm` files and invalidating its own hashes. Fixed by immutable inspection of checkpointed stopped snapshots; nonempty WAL/journals are refused. Regression tests cover no-file-change and pending-journal refusal. The failed private snapshot was preserved, not reclassified as successful.
- A fresh stopped snapshot passed hashes, private-permission and semantic checks with **235 metric records**. Source data and credentials were not published.
- Independent restoration into a new project, new port and two new volumes succeeded. The original account ID, system ID and hub public key matched. **All 235 saved metric records** matched their restored API records by ID, relation, timestamp and parsed statistics; fresh records were also collected.
- The agent data directory was empty in this SSH-only mode; it is nevertheless explicitly mounted, copied and hashed. No persistent WebSocket token/fingerprint behavior is claimed.
- Repeating `up` on the recovered project preserved both exact container IDs and startup timestamps. Recovered idle sample: hub **10.9 MiB / 256 MiB**, agent **4.035 MiB / 128 MiB**, each at **0.00% CPU** and seven processes.
- The original trial's stopped containers and dedicated network were removed through the ownership-checked adapter. Its two volumes, private files and snapshots were retained. The restored trial remains running for the pending UI check. The separate production hub and native Windows agent remained running; neither was modified.
- The Beszel-focused suite passed **39 tests**, including the SQLite fix. Static catalog/documentation validation, candidate publication-pattern checks, the PowerShell launcher and discovery-collector regressions passed. These are not a substitute for cross-platform CI or rendered UI evidence.
- Final local full-suite run on 2026-10-08: **222 tests, OK with two expected platform skips**, in 524.473 seconds. Candidate privacy-pattern checks covered all nine changed/new public files without findings; documentation validation and whitespace checks also passed. This does not claim staged/history publication review or exact-commit CI completion.

## Gates still pending

2026-10-08 recheck: the restored hub and agent were still running, authenticated API status was **up**, and fresh metric history was present (296 records at the check). The first trial on port 18090 remains removed; the recovered trial is on 18091. Current idle samples were 32.68 MiB for the hub and 11.31 MiB for the agent, both at 0.00% CPU. Browser inspection was blocked by a local execution-tool sandbox initialization failure, not by an observed Beszel application failure. No UI success is inferred from API success.

- Authenticated rendered chart inspection of the recovered hub (user sign-in required).
- Final staged/history publication review.
- Trial cleanup, exact-commit cross-platform CI and prerelease publication after the bounded acceptance gates pass.

### 2026-10-09 release recheck

The restored hub and agent remain running and paired. Authenticated inspection returned one system with status **up**, 286 retained history records and a latest reading at **2026-10-09 04:21:04 UTC**. This is a new live sample, not a repeat of the initial 235-record exact restoration comparison; retention can change record counts. The separate production hub was healthy and its native Windows agent was running. Neither was modified.

The browser-control helper still fails during sandbox initialization before accessing the application. Rendered-chart validation remains pending; a user-supplied screenshot of the authenticated system detail and history is requested. The restored trial stays available until that check. No release or cleanup success is inferred from API reachability. Source implementation was not changed, so the 2026-10-08 full-suite result remains the latest local regression run; release-commit CI is still required.

### 2026-10-15 integrated release recheck

The recovered loopback hub rendered its Beszel sign-in page in the validation browser, and the ownership-checked adapter still reports both services running and paired. The validation browser had no authenticated session, so no credential was extracted, reused or transmitted to bypass the sign-in boundary. Authenticated chart/history inspection remains pending, while the trial stays available on loopback for that manual check. The integrated local repository suite passed **294 tests with two expected platform skips**; exact-commit CI remains pending.

Full native host integration, custom Windows collectors and authentication-origin email behavior remain separate unfinished work. The full Beszel catalog entry and general application execution remain planned. See the [module guide](../beszel-module.md) for commands, scope and recovery caveats.
