# Phase 5 owner backup design validation

Date: 2026-11-01

Candidate: **0.6.0-rc.2**

## Decision

Go for repository-level review of the owner policy schema and deterministic disabled plan. No-go for installing scheduled tasks, generating production keys, initializing repositories, copying production data or claiming durable disaster recovery.

## Validated offline controls

- exactly six Phase 5 modules in reviewed order;
- one primary and one replica mounted-filesystem repository on distinct declared off-host devices;
- operational key separation from repository devices;
- exactly two offline recovery-key copies on distinct devices, separate from host and repositories;
- non-overlapping staging, repository and key paths;
- explicit per-module current-size, retention-reserve, RPO and RTO inputs;
- capacity admission for both repositories;
- disabled scheduling, unique daily slots, hidden non-overlapping task requirements and bounded runtime;
- restore-gated `7/4/3` retention and quarterly manual recovery rehearsal;
- required failure/missed-window/full-check/replica notifications;
- secret-value field rejection, deterministic plan identity and terminal path/device redaction.

The example intentionally produces six readiness blockers: two unconfirmed repositories, two unconfirmed offline key copies, an unconfigured notification route and no representative production-data restore drill.

## Read-only host observations

The reference Windows host exposed several healthy fixed volumes, but no drive was classified as removable or network storage by the read-only volume query. Those volumes are not accepted as off-host merely because they have different drive letters.

Seven existing scheduled backup tasks were observed for Paperless-ngx, AFFiNE and Firefly III. Their most recent recorded results were successful. They use non-overlapping settings, but all were visible rather than hidden; the Paperless/AFFiNE monthly task registrations use daily triggers and delegate month selection to their scripts. No existing task was changed. Before activation, these definitions must be reconciled and either retained or replaced without running duplicate jobs.

## Test commands

```sh
python -m unittest discover -s tests -p "test_owner_backup.py" -v
python homelab_cli.py owner-backup validate --policy modules/phase5/owner-backup-policy.example.json
python tools/validate_phase5.py
python tools/validate_repository.py
python -m unittest discover -s tests -v
```

## Remaining production gates

Owner-selected media, actual free-space checks, repository initialization, replica transport, protected key generation, task registration, notification delivery, missed-window detection, reboot recovery and representative production-data restore evidence are not part of this candidate.
