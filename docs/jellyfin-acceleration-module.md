# Native Jellyfin acceleration module

Phase 6 treats media acceleration as application-specific. The existing Immich capability decision remains CPU because the reference NVIDIA hardware does not meet Immich CUDA requirements. Jellyfin on the same Windows host has a separate candidate: Intel Quick Sync Video through the existing native installation and bundled Jellyfin FFmpeg.

This module audits and measures that path. It does not change Jellyfin settings, install a driver, expose a device to Docker or read a production library.

## Reference-host decision

| Backend | Observed prerequisite | Decision before full synthetic proof |
| --- | --- | --- |
| CPU | Intel Core i5-12400, Jellyfin FFmpeg available | Supported fallback |
| Intel QSV | Intel UHD 730, driver 32.0.101.7092; QSV/oneVPL present in Jellyfin FFmpeg | Synthetic proof passed; CPU fallback retained |
| NVIDIA NVENC/NVDEC | GeForce GT 730, Windows driver 391.35 | Blocked; current Jellyfin requires driver 522.25 or newer |

The FFmpeg binary advertised QSV, NVENC/NVDEC, CUDA, D3D11/D3D12 and AMF capabilities. Capability names alone are not proof that the installed hardware and driver can complete a transcode.

Read-only initialization probes showed:

- Intel QSV initialized through oneVPL 2.15 on PCI device `8086:4682`;
- a one-frame QSV H.264 encode completed in approximately 513 ms;
- a one-frame QSV HEVC encode completed in approximately 614 ms; and
- an NVENC H.264 probe failed immediately because the installed NVIDIA driver could not provide the required API.

Those bounded probes establish eligibility, not real playback or performance. Recent filtered Jellyfin logs showed QSV device initialization but did not contain enough encoder evidence to certify a production transcode.

## Non-mutating audit

The audit records only sanitized host, adapter, driver and Jellyfin FFmpeg facts:

```powershell
python -m homelab jellyfin-acceleration audit `
  --ffmpeg "C:\Program Files\Jellyfin\Server\ffmpeg.exe"
```

The output must not contain the Windows account, host name, Jellyfin server name, library names, paths to personal media, access tokens or authenticated API output.

## Synthetic performance proof

The trial generates its own short 1080p fixture and never reads the Jellyfin library. It compares:

1. CPU decode/scale to 720p/libx264 encode;
2. one Intel QSV 720p H.264 stream;
3. two concurrent Intel QSV 720p H.264 streams; and
4. an optional bounded QSV HEVC encode probe.

The first certificate deliberately excludes HDR tone mapping and Intel low-power encoding modes. Those require separate codec/driver-specific proofs and must not be enabled by inference.

```powershell
python tools\jellyfin_acceleration_trial.py `
  --ffmpeg "C:\Program Files\Jellyfin\Server\ffmpeg.exe" `
  --include-hevc `
  --confirm RUN-SYNTHETIC-JELLYFIN-QSV `
  --evidence ..\private\jellyfin-acceleration-evidence.json
```

A valid result checks decoded duration, dimensions and frame count; records output size and hashes; measures elapsed time, FFmpeg speed, process CPU time and peak working set where the platform exposes them; and proves that one- and two-stream QSV complete at or above the reviewed real-time threshold. Optional Windows GPU Engine counters strengthen device-use evidence but do not replace successful output validation.

The trial must clean its fixture and outputs after evidence is written. Four-stream, HDR and production-media testing remain out of scope until the bounded two-stream result preserves host headroom.

## Activation boundary

The module never rewrites Jellyfin's encoding configuration. The owner may retain an existing QSV setting only after the synthetic certificate passes and the native service remains healthy. CPU remains the documented fallback if any of these fail:

- QSV initialization or encode;
- decoded output validation;
- the one- or two-stream real-time threshold;
- resource-headroom policy;
- post-trial Jellyfin service health; or
- the recovery/restart validation that accompanies Phase 6 closure.

NVENC stays blocked on the reference host. Installing a newer driver alone would not prove that the GT 730 variant supports the codec/profile required by a workload; a fresh audit and synthetic test would still be required.

## Recovery interaction

Acceleration is not part of the Jellyfin backup. After an independent same-version Jellyfin recovery, the trial must be repeatable against the host capability without editing the restored database. Application recovery, encrypted off-host application backup and owner-managed media backup remain the authoritative protection paths described in the Jellyfin recovery guides.

## Upstream guidance

- [Jellyfin hardware acceleration](https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/) supports Intel QSV on Windows and recommends the bundled Jellyfin FFmpeg.
- [Jellyfin hardware-acceleration known issues](https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/known-issues/) documents Intel driver requirements and codec-specific limitations.
- [Jellyfin NVIDIA acceleration](https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/nvidia/) documents the Windows driver floor used by the NVENC decision.
- [Intel Quick Sync support](https://www.intel.com/content/www/us/en/support/articles/000057555/graphics.html) identifies UHD 730 as Quick Sync capable.
