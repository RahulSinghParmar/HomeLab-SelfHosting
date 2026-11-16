# code-server migration validation record

Validated on 2026-11-16 using Windows Docker Desktop and Linux amd64 containers.

## Encrypted application-consistent backup

- The exact Restic 0.19.1 Windows amd64 archive and executable matched both reviewed SHA-256 values.
- Production code-server was stopped before archiving config, local editor state, secure Linux volume, workspace, Compose and build metadata.
- The source restarted healthy before encryption work continued.
- The encrypted repository was created on physical disk 1, separate from source disk 7; the recovery key was created with a private ACL on physical disk 3.
- Snapshot `d43f5204` completed and `restic check --read-data` read all repository data.

## Independent restore

The encrypted snapshot was decrypted into a new temporary root. Both archive hashes and sizes matched their stopped-state manifest. The restored candidate reported code-server `4.145.0`, Node `24.19.0` and 20 persisted extensions. A synthetic C program compiled and executed server-side, HTTP health passed, and the candidate remained healthy after restart.

The first diagnostic start correctly failed closed because the required expected-version environment gate was missing. After adding the reviewed `4.145.0` value, the complete restore passed. This failed attempt did not touch production.

## Production cutover

- An exact pre-change Compose copy and the old cached image were retained.
- The old build/tag was replaced by the reviewed local candidate with pulls disabled.
- Config, local state, secure volume and workspace mounts were preserved.
- Six CPUs, 6 GiB memory, 512 MiB reservation and 2,048 PID ceiling were preserved.
- The direct host publish changed from all interfaces to `127.0.0.1:8443`.
- `no-new-privileges`, all-capability drop and bounded non-executable tmpfs are active.
- Production reported exact code-server `4.145.0`, Node `24.19.0`, 20 extensions, zero OOM events and healthy state.
- A server-side compile passed and its temporary files were removed.
- Local and `code.parmar.homes` health returned HTTP 200 before and after a controlled Compose restart.

The initial recreate briefly encountered Windows retaining the old 8443 bind after container removal. The listener cleared, the already-created candidate then started normally, and no rollback or data restore was needed.

All three plaintext staging/restore directories were deleted after the recovery and production gates passed. The encrypted repository, recovery key, proof, evidence, rollback Compose file and old image remain.

## Privacy and remaining boundary

No credential value, SSH/GPG key, workspace filename or private source content was read. The synthetic production compile used a temporary local-state directory and removed it immediately.

Authenticated browser autosave/reconnect and WebSocket behavior were not automated in this migration. The repository and recovery key are on separate local disks, not yet an off-machine repository plus offline key copy. arm64 remains unexecuted.
