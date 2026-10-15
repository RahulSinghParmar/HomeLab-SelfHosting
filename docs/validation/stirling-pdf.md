# Stirling-PDF isolated trial

Bounded Phase 4 candidate evidence collected **2026-10-15** on Windows Docker Desktop with a local Linux amd64 engine. All trial resources used synthetic content, private roots under `C:\Docker\HomeLab-Trials` and loopback-only ports. The separately existing `stirling-pdf` container on port 9000 was inspected read-only and never restarted or reconfigured.

## Completed evidence

- Pinned `stirlingtools/stirling-pdf:2.14.2` by digest `sha256:7ed4d9681d18e4fbc3aa6a63647c4b5c2bcc4b75841df7c05d7e3d2320f5c9a1`; cached image was Linux amd64.
- A first disposable hardening attempt correctly failed closed: dropping every capability prevented the pinned entrypoint from changing volume ownership and switching user. That failed project was removed. The reviewed contract now adds back only `CHOWN`, `SETGID` and `SETUID`, keeps the application process unprivileged, and validates Docker's normalized `CAP_*` representation.
- The final source trial used port 19000, a read-only root, four bounded tmpfs mounts, five named data volumes, no host mount/socket/device/GPU, no-new-privileges, bounded logs and a dedicated bridge.
- Container health became `healthy`; the local UI returned HTTP 200 HTML. The in-memory synthetic PDF endpoint returned an application/pdf result with verified 90-degree page rotation. Input was 606 bytes and output was 860 bytes; no document was retained.
- Settled source sample after the exercise: **944.1 MiB / 1.5 GiB**, **0.87% CPU**, **54 processes**. An earlier sample was 957 MiB and 57 processes. These are point-in-time measurements, not a load benchmark or guarantee for other conversions.
- The stopped backup contained **45 files / 21,930,451 bytes**: configs 6/130,928 bytes, custom files 0/0, logs 2/8,970, pipeline 4/3,972 and tessdata 32/21,786,581. Generated settings and OCR language evidence were present. Its content fingerprint was `ad45098a06da625a7068e2baa7d317ba0571b5c2c71931a358c2af219f986f8d`.
- A fresh recovery plan used a new root, project, five new volumes and port 19001. It revalidated the unchanged snapshot, became healthy and independently passed the same rotation exercise (861-byte output). Immediate post-exercise sample: **1.093 GiB / 1.5 GiB**, **0.38% CPU**, **57 processes**.
- The module's ownership and drift checks cover image, capabilities, read-only root, devices, tmpfs, health check, process/memory/CPU limits, logging, loopback port, bridge, persistent mounts, required environment, labels and foreign container/volume attachments.
- All **18 focused regression tests passed**. Coverage includes deterministic planning, unsafe/tampered inputs, exact Compose policy, Docker normalization, drift and ownership refusal, lifecycle interruptions, synthetic PDF structure including compressed object streams, sanitized HTTP failures, stopped backup integrity and recovery planning.
- The final local repository suite passed **274 tests with two expected platform skips** in 542.833 seconds. Repository/document validation, whitespace checks, the six-file candidate publication scan and the index publication guard also passed. Exact-commit CI and manual publication review remain separate release gates.
- Both trial containers and networks were removed through the ownership-checked module. After confirming that exactly ten detached labelled trial volumes remained, those volumes and the five exact private trial/plan/snapshot paths were permanently deleted. The separate production `stirling-pdf` container was rechecked as running and healthy on 2.14.2.

## Interpretation and remaining gates

This evidence supports an isolated **candidate module**, not migration of the existing household service and not a production-ready public deployment. Rotation exercises prove one real endpoint and recovery path; they do not certify every feature included in the large full image.

- Authentication was intentionally disabled for loopback-only synthetic testing. No account, login, SMTP, OAuth or public proxy behavior was tested.
- OCR assets were copied and hashed, but OCR accuracy and compute behavior were not exercised. LibreOffice, HTML/browser conversion, pipelines, batch/concurrent work and large documents remain untested.
- Memory consumption near 1 GiB is expected for this full image and materially exceeds lightweight utility services. The 1.5 GiB ceiling passed the tested rotation; reducing it further or changing Java limits requires representative job tests.
- The backup is plaintext and conservatively classified as containing authentication-sensitive state. Encrypted off-host backup, clean-machine restore and credential recovery remain required for real production recovery.
- Cross-platform runtime/architecture, update migration, rollback and release-commit CI remain pending. Existing production configuration and private data were not imported.

See the [module guide](../stirling-pdf-module.md) for commands and operating boundaries.
