# Phase 6 media foundation validation

Validated on 2026-11-02 against the public 0.7.0-alpha.1 source and the reference Windows Docker Desktop host.

## Evidence

- The host capability audit was read-only and reported Docker context `desktop-linux`, a Linux/amd64 WSL2 engine and an available NVIDIA container runtime.
- `nvidia-smi` identified a GeForce GT 730 with driver 391.35. No serial number, host name, account, media path or credential was recorded.
- NVIDIA's legacy table places GT 730 variants at compute capability 2.1 or 3.5. Both are below Immich's documented CUDA minimum of 5.2, and driver 391.35 is below the documented minimum of 545.
- The resulting decision is CPU mode with `compute-capability-below-5.2` and `nvidia-driver-below-545` blockers. No synthetic GPU container was justified or run after the prerequisite failure.
- The four candidate Immich image references were resolved from official registries to immutable multi-platform SHA-256 indexes. Images were queried, not pulled or started.
- Focused tests reject automatic heavy jobs, originals reclassification, excessive memory, foreign audits and unsupported GPU/runtime combinations.

## Safety result

No production container, native service, media file, database, Docker setting or GPU setting was changed. The public policy remains `disabled-review-only`; it cannot deploy Immich or enable acceleration.

## Support decision

This host is **not supported for Immich CUDA machine learning** with the installed GT 730 and driver. CPU mode is the reviewed baseline. The presence of an NVIDIA runtime alone is not evidence that the application can use the GPU.

Hardware transcoding is also not enabled by this result. It needs a separate codec-capability and synthetic-video test in the relevant application adapter.

## Remaining gates

The Immich milestone must still prove upload, browsing, exact download, restart, application-consistent database/original recovery, derived-file policy and measured ML concurrency. Optional media-management and Jellyfin work remain separate choices.
