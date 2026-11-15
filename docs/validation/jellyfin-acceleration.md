# Jellyfin acceleration validation record

This record separates the 2026-11-15 read-only capability baseline from the full synthetic performance certificate required to finish Phase 6. It authorizes no production setting change.

## Read-only baseline

- Host CPU: Intel Core i5-12400, 6 cores and 12 logical processors.
- Intel adapter: UHD Graphics 730, driver 32.0.101.7092.
- NVIDIA adapter: GeForce GT 730, driver 391.35, 4 GiB.
- Jellyfin FFmpeg: 8.1.3-Jellyfin with QSV/oneVPL, NVENC/NVDEC, CUDA, D3D11/D3D12 and AMF compiled in.
- Existing Jellyfin selection: QSV with hardware encoding enabled; Intel low-power H.264/HEVC modes disabled.

The audit did not enumerate production libraries, read a personal media file, authenticate to Jellyfin or modify the native service.

## Bounded prerequisite probes

- Intel QSV zero-frame initialization succeeded on PCI device `8086:4682` through oneVPL 2.15.
- One-frame QSV H.264 encode succeeded in approximately 513 ms.
- One-frame QSV HEVC encode succeeded in approximately 614 ms.
- One-frame NVIDIA H.264 NVENC initialization failed immediately because driver 391.35 is below Jellyfin's current 522.25 Windows minimum.
- After the probes, the native Jellyfin service remained running, automatic and locally healthy, with no leftover FFmpeg process.

This evidence supports `qsv=candidate`, `nvenc=blocked` and `cpu=fallback`. A one-frame encode is not a performance or playback certificate.

## Full synthetic certificate requirements

The disposable trial must:

1. generate a short, non-personal 1080p fixture;
2. create a CPU 720p H.264 baseline with Jellyfin FFmpeg;
3. create and validate one QSV 720p H.264 output;
4. create and validate two concurrent QSV outputs;
5. optionally create and validate one QSV HEVC output;
6. compare decoded duration, dimensions and frame count with tolerances defined in the evidence contract;
7. record hashes and output byte counts;
8. record wall time, FFmpeg speed, CPU time and peak working set when available;
9. confirm the native Jellyfin service is healthy after the trial; and
10. clean the synthetic workspace after writing sanitized evidence.

The trial must not use HDR, low-power encode modes, production media, a Jellyfin access token, an authenticated API or a production transcode directory. GPU counters may corroborate the result, but valid decoded output and bounded performance are mandatory.

## Recovery closure requirement

The acceleration result is accepted for Phase 6 only alongside the already established Jellyfin application/media recovery contract:

- a same-version application recovery restores actual synthetic application content;
- encrypted off-host application recovery remains independently decryptable and restorable;
- owner-managed media backup evidence protects the originals separately; and
- direct-play and post-recovery service health remain valid.

The acceleration trial must be repeatable after the recovery rehearsal. No database or encoding-setting mutation is required for that repeat.

## Completed synthetic proof

A generated 10-second, 1920x1080 H.264 fixture was decoded, scaled to 1280x720 and encoded through each required path. Every output contained 300 frames, matched the expected duration and dimensions, had a nonempty SHA-256 identity and passed SSIM quality validation.

| Run | Measured speed | Peak working set | SSIM |
| --- | ---: | ---: | ---: |
| CPU/libx264 baseline | 17.9x | 404.9 MiB | 0.993100 |
| QSV H.264, one stream | 13.3x | 166.4 MiB | 0.990889 |
| QSV H.264, two concurrent streams | 8.63x and 8.64x | 166.2 MiB each | 0.990889 |
| QSV HEVC, one stream | 6.11x | 220.0 MiB | 0.992656 |

The QSV single and dual runs remained well above real time. Temporary input/output files were removed, production media was not read, and Jellyfin configuration was not changed. After the proof, the native service remained `Running`, `Automatic` and locally healthy.

The retained Jellyfin application-recovery and encrypted off-host media-recovery evidence was revalidated with the current contracts. Exact synthetic direct play still passed after restore and restart; the media replica was restored without source-machine state.

## Result

Pass for Intel QSV H.264/HEVC synthetic transcoding with a documented CPU fallback and a two-stream concurrency ceiling for this release. NVENC remains blocked. HDR tone mapping, Intel low-power modes, four-stream concurrency and production-media transcoding remain unapproved.
