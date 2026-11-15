# Phase 6 closure validation

Validation date: 2026-11-15

## Result

Pass for the bounded public Phase 6 toolkit. The result combines previously certified Immich/Jellyfin recovery contracts with new media-management recovery and native Jellyfin acceleration evidence. It does not claim production-media adoption.

## Recovery evidence

- Immich's unchanged encrypted off-host workflow previously passed on two clean runners with an exact original restored through the application. The successful workflow remains [run 41583860157](https://github.com/RahulSinghParmar/HomeLab-SelfHosting/actions/runs/41583860157).
- Retained Jellyfin application and encrypted off-host evidence revalidated with the current strict contracts. Exact synthetic direct play passed after application restore and restart; the separately protected media replica was restored without source-machine state.
- Two disposable media-management rehearsals covered all eight selectable integrations. Both used internal networks and generated state only, stopped every selected application before copying configuration, restored into unrelated roots and reached healthy state again. Twenty-four SQLite checks, shared `/data` hardlink/atomic-move checks and restored content hashes passed. The measured groups used 816.9 MiB and 445.17 MiB at their sampled idle points.

## Acceleration evidence

The bundled Jellyfin FFmpeg completed a generated 10-second 1080p fixture through CPU and Intel QSV paths. QSV H.264 measured 13.3x for one stream and 8.63x/8.64x for two concurrent streams; QSV HEVC measured 6.11x. Every output had the expected 300 frames, duration and 1280x720 dimensions, with SSIM at or above 0.990889.

The Intel QSV proof retained CPU fallback and changed no Jellyfin setting. The reference GeForce GT 730 remained blocked because driver 391.35 is below Jellyfin's current Windows NVENC requirement. HDR, low-power encoding and four-stream concurrency were not inferred from this result.

## Isolation and cleanup

Before and after the new trials, native Jellyfin was `Running` with `Automatic` startup and all eight existing media-management containers were running. No production path, credential, media file, external provider or automatic action was used. Trial containers and networks were removed; sanitized evidence stayed outside Git.

## Release gate

The exact release commit must pass repository, Phase 4, Phase 5, Phase 5 closure, Phase 6, Phase 6 closure, publication, full unit, planning and platform-entry validation on Windows, Linux and macOS with Python 3.12 and 3.14. The tag is created only after those six jobs succeed.
