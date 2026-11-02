# Phase 5 encrypted recovery closure

Date: 2026-11-02

Release: **0.6.0**

## Decision contract

Phase 5 can close only when the exact release commit passes both:

1. the six-job Windows/Linux/macOS repository validation matrix; and
2. the manual integrated recovery workflow containing six encrypted-repository preparation jobs and six independent clean-runner application recovery jobs.

The release is a stable contract for the bounded synthetic recovery toolkit. It is not approval to adopt production data or replace an owner's existing backup process.

## Closure assertions

- All six modules create nonempty synthetic application content before backup.
- Every backup uses an application-specific consistency method rather than copying a live database directory.
- Every backup is stored in a separately keyed encrypted Restic repository.
- A complete Restic data check is required before portable recovery evidence is accepted.
- The recovery runner receives the key separately from the encrypted transport artifact.
- Recovery occurs without source-machine state.
- Restored content is checked through the application or rendered browser, including exact bytes/checksums where appropriate.
- Restored state is checked after restart.
- Retention remains `7 daily / 4 weekly / 3 monthly` and apply is restore-gated.
- Hosted fixtures contain no production data.

## Machine-readable evidence

- `modules/phase5/recovery.json` binds workflows, secrets, Restic manifests, trials and evidence paths.
- `modules/phase5/closure.json` binds each consistency method, authoritative recovery material, nonempty fixture and semantic proof fields.
- `tools/validate_phase5_closure.py` checks the final contract and refuses missing fixture, proof, encryption, retention or workflow coverage.

## Production boundary

Owner repositories, replica transfer, real offline keys, task installation, failure-notification delivery and representative personal-data restore drills remain private operational adoption work. They are not silently inferred from synthetic hosted recovery.
