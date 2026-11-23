# Native lifecycle validation

Validated on the Windows Docker Desktop reference host from 2026-11-19 through 2026-11-23.

## Result

Pass for stable `0.8.0`. The final live audit had no blockers and reported ready native services, user startup, Scheduled Tasks, Glances, Docker Desktop and dashboard samples. The first candidate audit proved that required logon tasks ran after the 2026-11-16 boot; the final proof compared that prior-boot checkpoint with a real Windows boot on 2026-11-23.

A controlled restart of only the two monitoring tasks then passed:

- both task definitions were exported before the test;
- Glances and the resource collector returned to `Running`;
- the Glances status API returned version 4.5.7;
- `resources.json` advanced after the restart; and
- no hosted application, Docker container or Windows host restart was performed.

## Corrections made

`ArrStackBackup` was the only task missing catch-up execution. Its complete XML was exported, `StartWhenAvailable` was enabled, and its action and trigger were verified unchanged.

The first Glances restart rehearsal exposed a lifecycle defect: Task Scheduler owned a PowerShell wrapper while the Python child survived a task stop. The task definition was backed up and changed to execute the reviewed virtual-environment Python directly with the same loopback, configuration and privacy arguments. The repeated controlled restart then passed.

The adapter also corrected two evidence interpretations found by live testing:

- an active Explorer session is used to detect an interactive sign-in when the audit itself runs non-interactively; and
- the storage collector's intentional `reported` physical-health state is accepted alongside `ok`, while unknown states still fail closed.

The first post-reboot audit found two genuine operational defects. The storage collector assumed a pending backup's null `testedUtc` value was a string and stopped publishing its aggregate sample. The AFFiNE backup captured table counts before stopping the application, allowing a normal background row to race the dump. Rollback copies were retained; parsing was made null-safe and the count capture was moved after application quiescence. A real scheduled AFFiNE backup then exited `0`, passed its independent restore test and returned the application container to `running|healthy`.

Private task XML, local reports, process details and reboot checkpoint remain outside Git. No credential, raw Glances metric, account, document, media item, message, workspace or application database was read.

## Reboot evidence

The owner-controlled reboot proof passed on 2026-11-23. The Windows boot timestamp advanced; task-definition fingerprints and Glances configuration hashes remained unchanged; native services, user startup, Scheduled Tasks, Glances and samples all recovered. Evidence identifier: `99c470b0e7fa55cf2b2c21ce0e50e7ea66d060dc41b5fcadf12b72ba64360972`.

No command initiated the reboot. A same-boot check remains rejected, and the evidence format still contains no credentials, local paths, identities or raw metrics.
