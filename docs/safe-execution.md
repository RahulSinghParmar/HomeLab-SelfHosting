# Phase 3: storage, secrets and safe execution

This release executes exactly one built-in **synthetic file module**. It does not deploy a Docker container, run a server, expose a port, pull an image, edit an existing application, or accept a production module as an execution target. The 21 application modules remain planning-only.

The purpose is to test the ownership and recovery mechanisms before allowing them to control real services. This is a core-primitives prerelease, not a production application installer or disaster-recovery solution.

## What the sandbox does

An explicit plan chooses three new, separate directories. Apply requires the full plan ID and performs these ordered operations:

1. Create protected installation storage and an ownership journal; claim new data and backup-staging roots.
2. Create a synthetic 256-bit credential once and retain its fingerprint in the journal.
3. Write known nonempty synthetic content into the owned data root.
4. Write an activation record with a keyed content proof, verify actual files, and mark the operation ready.

```text
installation/             private owner-only state (plus Windows SYSTEM/Admins)
  operation.lock          kernel lock; retained after process exit
  state.json              ownership, plan ID, secret fingerprint, ordered events
  secret.json             synthetic credential; never printed
  active.json             verified activation receipt; removable by retire only
data/
  owner.json              installation and role marker
  synthetic.json          fixed test content; retained on retirement
backup-staging/
  owner.json              reservation only; no backup is created
```

The backup directory is a reserved storage role, not a backup job or recovery guarantee. No actual database exists in this module. Per-application database/volume execution remains future work; the Phase 2 planner still documents those choices separately.

## Windows walkthrough

Choose a private parent you own, outside every Git checkout. Use **new child names**, never your production directories. If the parent already exists, do not recreate it; review its access permissions first. The executor does not alter the parent's permissions.

```powershell
New-Item -ItemType Directory -Path C:\HomelabPrivate
python -m homelab sandbox plan --root C:\HomelabPrivate\trial-install --data-root C:\HomelabPrivate\trial-data --backup-root C:\HomelabPrivate\trial-backups --output C:\HomelabPrivate\trial-plan.json
Get-Content C:\HomelabPrivate\trial-plan.json
```

Review the exact paths and operations in the private plan file. Terminal output redacts path values. Copy the complete `plan_id` into the confirmation argument below; do not blindly generate and confirm a plan in one command.

```powershell
python -m homelab sandbox apply --plan C:\HomelabPrivate\trial-plan.json --confirm "PASTE_REVIEWED_PLAN_ID"
python -m homelab sandbox status --plan C:\HomelabPrivate\trial-plan.json
```

Re-running the same confirmed apply verifies existing ownership, permissions, credential fingerprint, content and activation. Once ready, it changes neither data nor journal and does not rotate the credential. A journal entry alone is never treated as proof that the corresponding file is still valid.

For Linux/macOS, use the same CLI with three absolute local paths under an owned private parent, for example `/home/example/HomelabPrivate` or `/Users/example/HomelabPrivate`. Create the parent with mode 0700. Use canonical paths: system aliases such as `/var` pointing to `/private/var` are rejected. Only the **current host platform** can execute its plan.

## Data-preserving retirement

```powershell
python -m homelab sandbox retire --plan C:\HomelabPrivate\trial-plan.json --confirm "PASTE_REVIEWED_PLAN_ID"
python -m homelab sandbox status --plan C:\HomelabPrivate\trial-plan.json
```

Retirement verifies the stored credential, content and activation before deleting exactly the owned `active.json` receipt. It retains the credential, synthetic data, storage markers, lock file and complete journal. Retirement is retryable, including interruption after receipt removal. A retired installation cannot be silently reactivated; create a separately reviewed trial for another run. Recreating an activation would require a future explicitly designed recovery operation; this release does not supply one.

There is no recursive delete, data purge, production stop, directory adoption or uninstallation command. Never delete an unfamiliar directory just to make a check pass.

## Permissions and credentials

On POSIX, new directories use 0700 and private files use 0600; owner and exact modes are checked before use. On Windows, only the current account, SYSTEM and Administrators receive full control on newly created roots and private files. The current account is explicitly assigned as owner, including when Windows would default to Administrators under an elevated token. Existing files are checked for the expected owner and allowed principals. The adapter changes only newly created resources' owner/DACL information, not audit/SACL policy, and never auto-elevates. Windows PowerShell's module environment is isolated from inherited PowerShell 7 module paths. If a filesystem cannot honor the required permissions or hard links, execution stops.

The token uses Python's operating-system-backed [secrets API](https://docs.python.org/3/library/secrets.html), with 32 bytes of randomness. The token and its file contents never appear in status, errors, plans or journal events. The journal stores a fingerprint and logical reference. Secrets are local protected **plaintext**, not encrypted backups; this module's token is only a synthetic test credential. There is no credential export, external vault, rotation, recovery-key handling or encrypted recovery bundle in this phase.

Do not place private state in Git, shared/synchronized folders or a publicly served directory. Trusted parent directories and the current OS account are security boundaries. Same-account malicious processes, administrators/root and concurrent parent-path manipulation are outside this release's threat model. Path checks are not a race-proof sandbox against a hostile privileged host. Local ACLs do not replace full-disk encryption or off-host encrypted recovery.

## Ownership, journal and locking

- New roots must not exist, including empty directories. Initialization never adopts an existing directory just because its name matches.
- State records a generated owner ID and the exact reviewed plan ID. Data/backup markers bind each role to that installation. Moving paths or editing a plan changes its ID and blocks reuse of old state.
- Steps follow a validated transition sequence: initialized, storage verified, secret created, content verified, ready, retiring, retired. Arbitrary tasks, command strings or plugins are not loaded from a plan.
- JSON writes are staged, flushed, then atomically published. New files use no-clobber hard-link publication; owned state snapshots use atomic replacement. Temporary residue and unexpected hard links block further work.
- The lock uses nonblocking [Windows byte-range locking](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking) or POSIX `flock`, held for the entire operation. Another writer is rejected. The OS releases the lock on process death; the lock file is not deleted based on a stale PID. Do not remove or replace it while operations run.
- Status also holds the lock to avoid reading a changing installation. Ready/retired status verifies real content; an interrupted `applying` status is not a health claim. Exit 0 means the command succeeded, not that an `applying` installation is ready.

## Interruption and failure handling

| Observation | Safe behavior |
| --- | --- |
| Failure between completed operations | Reapply the same reviewed plan; reconcile files and continue without rotating a published secret |
| Process forcibly exits after secret creation | Kernel lock releases; reapply verifies and reuses the same credential |
| Secret/content missing after being recorded complete | Stop; preserve state, do not regenerate or overwrite |
| Foreign/edited marker, token or activation | Stop; retain the file and request investigation |
| Another process holds the lock | Stop immediately; retry when that process exits |
| Directory created but ownership publication interrupted | Stop; no automatic adoption of the unmarked directory |
| `.pending-*` file or hard-link residue from interrupted atomic write | Stop; preserve all files for manual evidence-backed recovery |
| Retirement interrupted after receipt removal | Repeat retire with the same plan; retained data and secret are verified |

For ambiguous initialization/publication failures, keep the reviewed plan and entire private directory set. Do not post raw files containing the token. This phase does not implement automatic forensic reconciliation or rollback of every possible write failure. File flushes and atomic namespace updates do not certify power-loss durability on every filesystem or storage device. Network filesystems, mount changes and a failed disk require separate qualification.

## Validation boundary

Tests exercise actual filesystem permissions, creation, no-overwrite behavior, kernel lock contention, hard process exit, retry/idempotency, changed/missing credentials and content, failed dependencies, journal tampering, atomic replacement failure, private CLI output and retirement retention. Windows DACL and POSIX mode drift have separate tests. Real-container interruption, Docker volumes, database consistency, service health, image availability and restore rehearsals remain future gates.

The ordinary `apply` command remains unavailable; only the deliberately named `sandbox apply` exists. Application review plans cannot be used as sandbox plans. Stop before Phase 4 until explicitly authorized.
