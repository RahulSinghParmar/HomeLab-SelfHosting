# Owner-operated Phase 5 backup design

This design converts the six synthetic Phase 5 recovery modules into an owner-reviewable storage, scheduling and recovery-key policy. It deliberately does **not** install tasks, create keys, initialize repositories, read production data or replace an existing backup process.

## Storage architecture

```text
application-consistent backup
          |
          v
local plaintext staging on the host (short lived)
          |
          v
encrypted primary repository on owner-controlled off-host storage
          |
          v
encrypted replica on a second device/location

operational key on host ----X---- repository devices

offline key copy 1 ---------X---- host/repository devices
offline key copy 2 ---------X---- host/repository devices/key copy 1
```

The reviewed vault adapters accept filesystem paths. Therefore the supported design target is a mounted filesystem: for example, a securely mounted NAS/UNC path or external storage that is present only during the backup window. Native S3, SFTP and cloud-object adapters are not implemented by this release.

A different internal drive letter is not automatically off-host. A disk inside the same Windows computer can be useful staging or a fast local copy, but it does not survive theft, fire, power damage or loss of the entire machine. The policy requires logical device identities as well as different paths to make that distinction explicit.

## Capacity model

For each application, the owner supplies:

- estimated current authoritative data;
- an explicit retention/growth reserve;
- recovery-point objective (RPO);
- recovery-time objective (RTO).

Each primary and replica repository must independently hold the sum of those values plus a minimum-free-space reserve. This is a conservative admission check, not a prediction of Restic deduplication or compression. Measure real growth after adoption and revise the private policy before capacity becomes tight.

The public example contains placeholders, not measurements of a real deployment.

## Schedule design

The policy defines one staggered daily backup slot per module, then one weekly full-data repository check and one retention preview. Retention remains `7 daily / 4 weekly / 3 monthly`; apply is allowed only when a restore-verified snapshot would remain protected.

All generated Windows task definitions must eventually use:

- hidden execution so no console interrupts the desktop;
- `IgnoreNew`/single-instance behavior so jobs cannot overlap;
- start-when-available behavior after sleep or reboot;
- a bounded execution timeout;
- secret files or protected environment references, never secrets in arguments;
- explicit success/failure output and notification of backup, missed-window, full-check and replica failures.

The policy command does not generate or register those tasks. That is a later, separately confirmed activation milestone. Existing tasks must first be reconciled by name, action and ownership to avoid duplicate backups.

## Recovery-key custody

Every application retains its own vault key. The operational key can be available to the scheduled backup account, but it must not be stored in the repository. Two recovery copies are required on distinct offline devices, separate from the host and both repository devices.

Recommended custody procedure:

1. Generate a high-entropy key through the module's reviewed `key-create` command only after paths and access controls are approved.
2. Keep the operational file readable only by the dedicated backup identity.
3. Place two exact recovery copies on separately labeled encrypted media.
4. Store at least one copy away from the server location.
5. Record only media identifiers and custody checks in the policy—never key contents.
6. Test one offline copy in a clean recovery rehearsal, then return it offline.
7. Rotate only through a documented Restic key procedure after every repository and recovery copy has been verified.

A password manager entry synchronized from the same server can be a convenience copy, but it is not the only recovery-key custody location.

## Policy workflow

Copy the example to a private directory outside Git, replace every path/device/capacity value, and keep scheduling disabled:

```powershell
Copy-Item .\modules\phase5\owner-backup-policy.example.json C:\PrivateHomeLab\owner-backup-policy.json
python .\homelab_cli.py owner-backup validate --policy C:\PrivateHomeLab\owner-backup-policy.json
python .\homelab_cli.py owner-backup plan --policy C:\PrivateHomeLab\owner-backup-policy.json --output C:\PrivateHomeLab\owner-backup-plan.json
```

The plan is deterministic and contains no secret values, but its real paths, device labels, capacity estimates and evidence references are private. The terminal view redacts paths and device identities. Output is no-overwrite and cannot be saved inside this Git checkout.

The example remains blocked because owner confirmations, notifications and a representative production-data drill are false. Even a policy with no blockers is only `ready-for-separate-activation-review`; it does not enable scheduling.

## Activation gates

Do not activate production backups until all are true:

1. The primary and replica destinations are physically distinct, mounted reliably and capacity-checked.
2. Two offline key copies exist and one has recovered a test repository without the host's operational key.
3. Existing backup tasks have been reconciled so the new schedule will not duplicate or race them.
4. The notification route has delivered a controlled failure message.
5. One representative, approved production-data backup has been restored into an isolated project and content was rendered or decrypted—not merely health-checked.
6. RPO, RTO, duration and repository growth are measured.
7. Activation commands and rollback steps receive a separate owner approval.

## Current limitations

- Design and offline validation only; no task installer or coordinator is released.
- Mounted filesystems only; no native object-storage or SFTP transport.
- The replica transfer mechanism is not implemented.
- No production credentials, backup contents, paths or key values are supplied.
- Windows Task Scheduler semantics are designed but not reboot-tested by this release.
- Linux systemd timers and macOS launchd definitions remain future platform work.
