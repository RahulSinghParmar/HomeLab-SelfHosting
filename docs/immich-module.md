# Immich application-aware recovery module

Version 0.7.0-alpha.2 adds an isolated Immich 3.3.5 recovery candidate. It is a synthetic validation path, not an adopter or updater for an existing Immich deployment.

## Recovery boundary

Immich needs PostgreSQL and original files from the same application-consistent point. The module stops the server and machine-learning services, creates and validates a custom PostgreSQL archive, then copies these protected locations:

- `library`
- `upload`
- `profile`

Thumbnail, encoded-video and automatic-dump contents are excluded as rebuildable derivatives. Their small `.immich` integrity markers are retained separately because a restored database expects those folders to pass Immich's mount checks. Valkey state and the machine-learning model cache are excluded.

The backup manifest hashes every protected file, configuration artifact, database archive and integrity marker. A backup remains `pending-independent-restore` until a fresh project returns the exact uploaded original through the authenticated Immich API.

## Machine-learning boundary

The machine-learning service is internal-only, has no host port or device request, and is independently stoppable. Its candidate limits are:

| Control | Value |
| --- | --- |
| CPU | 1 core |
| Memory | 1536 MiB |
| PIDs | 256 |
| Worker processes | 1 |
| Request/inter-op/intra-op threads | 1 / 1 / 1 |
| Face/OCR batch ceiling | 1 / 1 |
| Idle model TTL | 60 seconds |
| Model arena | disabled |
| Acceleration | CPU; no device access |

Stopping machine learning does not stop browsing or downloading originals. The exercise verifies that separation explicitly. The Phase 6 foundation's CUDA rejection for the reference GT 730 remains unchanged.

## Storage and access

- The server is bound only to `127.0.0.1` on the reviewed port.
- PostgreSQL, Valkey and machine learning are reachable only on an internal Docker network.
- The media bind lives under the selected module root; no external library or host-wide path is mounted.
- PostgreSQL, Valkey and ML cache use project-owned volumes.
- The database password is supplied through a private Docker secret file and is not embedded in Compose.
- Docker socket, privileged mode and device access are absent.
- Stop and remove retain the media bind and named volumes; volume deletion is not a module action.

## Workflow

Use an absent root and a private plan outside that root:

```sh
python -m homelab immich plan \
  --root ../private/immich-test \
  --port 18060 \
  --output ../private/immich-plan.json
```

Review the full `plan_id`, then use it as the confirmation value:

```sh
python -m homelab immich up --plan ../private/immich-plan.json --confirm <plan-id>
python -m homelab immich exercise --plan ../private/immich-plan.json --confirm <plan-id>
python -m homelab immich backup --plan ../private/immich-plan.json \
  --output ../private/immich-backup --confirm <plan-id>
```

Create a different root, port and plan for restoration:

```sh
python -m homelab immich plan \
  --root ../private/immich-restore \
  --port 18061 \
  --restore-backup ../private/immich-backup \
  --output ../private/immich-restore-plan.json
python -m homelab immich up \
  --plan ../private/immich-restore-plan.json --confirm <restore-plan-id>
```

The local staging set contains credentials and plaintext original media. It must not be committed or treated as an off-host backup. Encryption, separate recovery-key custody, durable storage and production adoption are later gates.

## Proven scope

The Windows Docker Desktop trial created a fresh admin, uploaded a deterministic PNG, downloaded its exact bytes, repeated the download while ML was stopped, restarted ML, captured a quiesced backup, and restored into an unrelated project. The recovered original was verified again after a complete stop/start cycle.

See the [validation record](validation/immich.md) for exact evidence and [Immich's backup guidance](https://docs.immich.app/administration/backup-and-restore/) for the upstream consistency model.

## Not yet delivered

- No encrypted or off-host recovery workflow.
- No production library adoption, migration or update.
- No external library, mobile-client, album or large-video validation.
- No derived-media regeneration test.
- No GPU or hardware-transcode enablement.
- No durable scheduling, retention or alerting.
