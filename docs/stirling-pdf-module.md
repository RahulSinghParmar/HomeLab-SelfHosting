# Experimental Stirling-PDF module

This bounded Phase 4 module creates a **new, isolated Stirling-PDF 2.14.2 project** for synthetic document processing and recovery tests. It never discovers, adopts, restarts or changes an existing Stirling-PDF deployment. See the [Windows Docker Desktop validation record](validation/stirling-pdf.md) for the evidence and remaining gates.

## Security and resource boundary

- The reviewed Linux amd64 image is pinned by digest in `modules/stirling-pdf/image.json`; execution uses `pull_policy: never` and does not update it.
- The UI is published only on `127.0.0.1` on the reviewed port. The dedicated bridge allows outbound access, but there is no Docker socket, host path, device, GPU, host namespace or public tunnel.
- The root filesystem is read-only, all capabilities are dropped, and only `CHOWN`, `SETGID` and `SETUID` are added back. Those three capabilities are required by the pinned image entrypoint to initialize owned volumes and switch to its unprivileged runtime account. Docker-normalized capability names, tmpfs paths, health check, mounts, limits, labels and foreign attachments are checked before lifecycle actions.
- Writable temporary work is bounded to tmpfs mounts. Persistent named volumes cover `/configs`, `/customFiles`, `/logs`, `/pipeline` and `/usr/share/tesseract-ocr/5/tessdata`.
- The ceiling is 1.5 GiB RAM, 2 CPUs and 512 processes. Java is bounded to 768 MiB heap, 192 MiB metaspace and a 128 MiB initial heap. The upload setting is 50 MiB. These are trial limits, not a promise that every Stirling operation fits.
- Analytics, Google visibility, alpha functionality, Swagger and API documentation are disabled.

Authentication is deliberately disabled **only for this loopback synthetic trial**. Loopback does not protect against other local users or Docker administrators. Do not publish this project, bind it to all interfaces or place it behind a tunnel. A future public or household deployment requires its own login bootstrap, secrets, authorization, proxy and recovery design.

## Reviewed lifecycle

Run from the repository root. The parent directory must already exist; the installation, plan and backup destinations must be absent. Keep generated plans and snapshots outside Git.

```sh
python -m homelab stirling plan --root D:/HomeLab-Trials/stirling --port 19000 --output D:/HomeLab-Trials/stirling-plan.json
python -m homelab stirling up --plan D:/HomeLab-Trials/stirling-plan.json --confirm FULL_PLAN_ID
python -m homelab stirling status --plan D:/HomeLab-Trials/stirling-plan.json
python -m homelab stirling exercise --plan D:/HomeLab-Trials/stirling-plan.json --confirm FULL_PLAN_ID
```

`plan` is read-only except for creating the private plan file. The full plan hash binds the root, port, local engine identity, pinned image and resource/security policy. `up` creates only the owned project and is retry-safe when the recorded resources still match. Existing directories, ports, images, projects and unowned resources are refused instead of adopted.

`exercise` sends a generated 606-byte, one-page PDF directly from memory to the pinned `/api/v1/general/rotate-pdf` endpoint. It requires an HTTP 200 PDF response, bounded size, PDF header/trailer and a verified 90-degree page rotation, including bounded inspection of Flate-compressed PDF object syntax. It stores no input or output document. This certifies that operation only; it is not broad feature or output-fidelity testing.

```sh
python -m homelab stirling stop --plan D:/HomeLab-Trials/stirling-plan.json --confirm FULL_PLAN_ID
python -m homelab stirling up --plan D:/HomeLab-Trials/stirling-plan.json --confirm FULL_PLAN_ID
python -m homelab stirling remove --plan D:/HomeLab-Trials/stirling-plan.json --confirm FULL_PLAN_ID
```

`stop` preserves all volumes. `remove` requires a stopped service and removes only the exact owned container and network; it deliberately retains data volumes, private state and snapshots. There is no module command that deletes persistent data.

## Backup and fresh recovery

Only a stopped owned service can be backed up:

```sh
python -m homelab stirling stop --plan D:/HomeLab-Trials/stirling-plan.json --confirm FULL_PLAN_ID
python -m homelab stirling backup --plan D:/HomeLab-Trials/stirling-plan.json --confirm FULL_PLAN_ID --output D:/HomeLab-Trials/stirling-snapshot
```

The snapshot copies and hashes all five persistent trees. Validation requires generated `settings.yml` and nonempty OCR language data, records per-area file/byte counts and binds the pinned image. Hard links, unexpected file types, changed content and missing required evidence are refused.

**The snapshot is unencrypted and may contain authentication settings, accounts, custom files, pipeline definitions and document-related logs.** Owner-private permissions do not protect it from the owner, Docker administrators or privileged malware. Never commit, publish or attach it to an issue. Store a separately encrypted off-host copy for real disaster recovery.

Recovery always uses a fresh root, port, Compose project and volumes:

```sh
python -m homelab stirling plan --root D:/HomeLab-Trials/stirling-restored --port 19001 --restore-backup D:/HomeLab-Trials/stirling-snapshot --output D:/HomeLab-Trials/stirling-restore-plan.json
python -m homelab stirling up --plan D:/HomeLab-Trials/stirling-restore-plan.json --confirm RESTORE_PLAN_ID
python -m homelab stirling exercise --plan D:/HomeLab-Trials/stirling-restore-plan.json --confirm RESTORE_PLAN_ID
```

The snapshot manifest is revalidated before every recovery-plan action. Data is copied only into never-started owned volumes; an interrupted copy remains `restore-copying` and is not silently replayed. A backup result remains `recovery_verified: false` until a separate restored project becomes healthy and passes an application operation.

## Certified and uncertified scope

Certified on the recorded Windows Docker Desktop/Linux amd64 trial: fresh start, health endpoint, local rendered UI response, synthetic 90-degree rotation, stopped snapshot integrity and independent functional restore. The existing production container remained untouched.

Not certified: public exposure, authentication/account restore, SMTP/OAuth, OCR quality, LibreOffice conversions, HTML/URL conversion, browser automation, pipelines, batch jobs, very large files, concurrent load, GPU, ARM64, native Linux/macOS runtime, update/migration/rollback or clean-machine disaster recovery. Digest pinning provides reproducibility, not vulnerability certification.

Upstream reference: [Stirling-PDF v2.14.2](https://github.com/Stirling-Tools/Stirling-PDF/tree/v2.14.2). No upstream source is copied into this repository.
