# Native Windows lifecycle and Glances

The Phase 7 native-lifecycle module verifies the parts of a Windows Docker Desktop host that Compose cannot own: Windows services, user-startup applications, Scheduled Tasks, a private Glances process and the dashboard collector samples. It audits an existing host; it is not a general Windows installer and never reboots the machine.

## Support boundary

The reviewed platform is `windows-interactive-docker-desktop`:

- Docker Desktop uses the `desktop-linux` context and requires an interactive Windows sign-in.
- Glances listens only on `127.0.0.1:61208` below `/glances/`.
- private process, user, interface, address and raw metric values are not copied into audit evidence;
- native services remain Windows-owned and user applications remain user-startup-owned;
- Scheduled Tasks run as the interactive user with limited privileges;
- unattended pre-logon application recovery is not claimed; and
- no audit, checkpoint or verification command initiates a reboot.

The example policy maps the reference host. Review its service names, startup entries, task names, paths and exact Glances version before using it elsewhere.

## Glances process ownership

Task Scheduler must execute the virtual-environment `python.exe` directly. A PowerShell wrapper can start Glances successfully, but stopping that task may terminate only the wrapper and leave the Python child alive. Direct ownership makes task state, failure restart and controlled stop/start behavior agree with the real process.

The audit also requires the reviewed privacy flags:

- loopback bind;
- disabled process and process-list collection;
- disabled IP plugin and autodiscovery;
- disabled configuration command execution and update checks; and
- hidden public information.

The API must expose CPU, memory, load, process-count, disk-I/O and network aggregate plugins. Raw API values are used only for the live check and are not persisted in the evidence.

## What is checked

The strict policy verifies:

1. required Windows services are running with automatic startup;
2. required user-startup entries exist and their processes are running;
3. scheduled task actions, triggers, principals, run levels, catch-up behavior, restart counts and result classes match policy;
4. first-of-month backup wrappers retain their explicit day-one gate;
5. Glances is the exact reviewed version, private, responsive and directly task-owned;
6. five dashboard samples are valid, fresh and report only accepted healthy source states; and
7. required logon tasks last ran after the current Windows boot.

Audit output is hash-bound, refuses unsafe overwrites and contains no secrets, private paths, raw metrics or Windows identity.

## Commands

Create a read-only audit in a private directory:

```powershell
.\tools\Manage-NativeLifecycle.ps1 `
  -Action Audit `
  -OutputDirectory C:\private\homelab-evidence
```

Create the before-reboot audit and checkpoint:

```powershell
$result = .\tools\Manage-NativeLifecycle.ps1 `
  -Action Checkpoint `
  -OutputDirectory C:\private\homelab-evidence
$result.Checkpoint
```

The owner then performs a normal Windows restart at a suitable maintenance time and signs in. The tool does not do this. After Docker Desktop and the user-startup tasks settle, verify the new boot:

```powershell
.\tools\Manage-NativeLifecycle.ps1 `
  -Action VerifyReboot `
  -BeforeCheckpoint C:\private\homelab-evidence\native-reboot-checkpoint-YYYYMMDDTHHMMSSZ.json `
  -OutputDirectory C:\private\homelab-evidence
```

Verification passes only when the Windows boot timestamp advances, task-definition fingerprints and Glances configuration hashes remain unchanged, and every post-reboot readiness gate passes. Reusing a checkpoint on the same boot is rejected.

## Recovery

If a task definition drifts, stop and restore the owner-approved exported task XML before running it again. If Glances fails, confirm that no stale process owns port 61208, then inspect the direct task action and private configuration. If a collector is stale, repair that collector rather than loosening its freshness limit. Keep task XML, audit files and reboot evidence outside Git because host identities and local paths can exist in task exports even though the public audit format excludes them.
