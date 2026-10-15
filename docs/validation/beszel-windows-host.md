# Beszel Windows host adapter — validation in progress

Candidate Phase 4 milestone. It is not released or declared production-portable.

## Completed on 2026-10-09

- Reviewed the existing Beszel 0.18.7 source delta and separated Windows host metrics from the unrelated PocketBase authentication-origin patch.
- Identified and corrected two security/usability issues: `typeperf.exe` is launched hidden, and service command lines/accounts are never sent to the hub.
- Changed empty Windows `SERVICE_PATTERNS` behavior from all services to disabled. The existing reference service has explicit patterns, so it is not dependent on the old broad default.
- Added a public source patch and digest-pinned Docker build recipe against upstream commit `6e3fd90834309213aca32f2ff5fb0b027661c39a`.
- Added a secret-safe existing-service adapter with PE/amd64 checks, deterministic reviewed plan, exact service/environment fingerprint, private rollback copy, confirmation gate and drift refusal.
- Twelve adapter unit tests passed. A local candidate built successfully and its compiled Windows agent test executable returned `PASS`.
- The public patch applied cleanly to a new detached worktree at the exact upstream commit. A clean build produced the same agent SHA-256 as the reviewed working-tree build: `72a8144c4664ca429e9bb6f81c878c5d50b2c138cddfbaa2a13e96aa6d0400fc`. Its compiled Windows tests also returned `PASS`.
- Redacted live audit confirmed `BeszelAgent` is automatic, NSSM-managed, amd64 and configured with expected variable names. No values were emitted.
- A private upgrade plan was created. Its pre-apply status reported running, original binary installed and no configuration drift.
- The exact plan was applied through an administrator process. A private rollback directory was created, the binary was replaced once, and `BeszelAgent` returned to automatic/running with unchanged configuration fingerprint.
- Post-upgrade checks found the agent and its hidden `typeperf.exe` child running, three established TCP connections, three explicit service patterns and 838 available GPU counter samples. The sample maximum was 4.13%, proving the counter is available and not a hard-coded zero. The local hub health endpoint remained HTTP 200, with no matching recent hub warning/error lines.
- A network-disabled, read-only SQLite inspection of the production hub volume found a fresh post-upgrade record for the running Windows system. Its metric payload contains GPU data, and the restricted service collection contains two matching Windows service records. The check emitted only anonymized system references, timestamps, field names and counts; it did not read or print account, token, host-name or service-name values.
- The repository-wide suite passed **234 tests** with two expected platform skips in 460.987 seconds after the shared CLI integration.

## Pending gates

- Confirm the already-recorded GPU and service data renders correctly in the authenticated hub. Database field presence is not a substitute for visual evidence.
- Exercise a controlled stopped automatic test service and an inactive manual test service without touching production-critical services.
- Verify Windows reboot recovery. This is intentionally deferred because rebooting interrupts unrelated workloads.
- Complete staged publication review, cross-platform CI and the bounded prerelease only after runtime evidence passes.

The production hub and upgraded native agent remain operational. The first non-administrator apply attempt stopped before service access or mutation; the subsequent approved elevated apply succeeded. The rollback copy is retained.
