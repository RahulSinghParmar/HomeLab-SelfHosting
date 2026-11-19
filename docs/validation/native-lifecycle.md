# Native lifecycle validation

Validated on the Windows Docker Desktop reference host on 2026-11-19.

## Result

Pass for the `0.8.0-rc.1` native-lifecycle candidate. The final live audit had no blockers and reported ready native services, user startup, Scheduled Tasks, Glances, Docker Desktop and dashboard samples. It also proved that the required logon tasks ran after the current Windows boot on 2026-11-16.

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

Private task XML, local reports, process details and reboot checkpoint remain outside Git. No credential, raw Glances metric, account, document, media item, message, workspace or application database was read.

## Reboot evidence boundary

The current boot provides observed recovery evidence, and controlled monitoring-task recovery passed. A new secret-free checkpoint is ready for the stronger two-snapshot test, but Windows was not rebooted implicitly. Stable `0.8.0` remains gated on the owner performing a normal restart and running `VerifyReboot` with that prior-boot checkpoint. A same-boot check cannot pass.
