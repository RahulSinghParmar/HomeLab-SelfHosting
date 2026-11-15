#!/usr/bin/env python3
"""Run a bounded synthetic CPU/Intel-QSV Jellyfin acceleration proof.

No Jellyfin API, configuration, database or media path is accepted.  All video
is generated inside a new temporary directory and removed before a successful
proof is emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homelab.config import ConfigError, canonical, need  # noqa: E402
from homelab.jellyfin_acceleration import audit, make_proof  # noqa: E402


CONFIRMATION = "RUN-SYNTHETIC-JELLYFIN-QSV"
FIXTURE = {
    "synthetic": True,
    "duration_seconds": 10,
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "source_codec": "h264",
}


def locate_ffmpeg(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if sys.platform == "win32":
        candidates.extend([
            Path(r"C:\Program Files\Jellyfin\Server\ffmpeg.exe"),
            Path(r"C:\Program Files\Jellyfin\Server\jellyfin-ffmpeg\ffmpeg.exe"),
        ])
    found = shutil.which("ffmpeg")
    if found:
        candidates.append(Path(found))
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise ConfigError("Jellyfin FFmpeg was not found; pass --ffmpeg explicitly")


def locate_ffprobe(ffmpeg: Path) -> Path:
    sibling = ffmpeg.with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
    if sibling.is_file():
        return sibling
    found = shutil.which("ffprobe")
    need(found is not None, "FFprobe was not found next to FFmpeg or on PATH")
    return Path(found).resolve()


def command(arguments: list[str], *, timeout: int = 180) -> tuple[int, str, float]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            arguments, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ConfigError("A bounded synthetic FFmpeg command timed out") from error
    return result.returncode, result.stderr, time.perf_counter() - started


def generate_fixture(ffmpeg: Path, target: Path) -> None:
    arguments = [
        str(ffmpeg), "-hide_banner", "-nostdin", "-y",
        "-f", "lavfi", "-i",
        f"testsrc2=size={FIXTURE['width']}x{FIXTURE['height']}:rate={FIXTURE['fps']}",
        "-t", str(FIXTURE["duration_seconds"]), "-an",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(target),
    ]
    code, _, _ = command(arguments)
    need(code == 0 and target.is_file() and target.stat().st_size > 1024,
         "Failed to generate the bounded synthetic H.264 fixture")


def transcode_arguments(ffmpeg: Path, source: Path, target: Path,
                        backend: str, codec: str = "h264") -> list[str]:
    common = [str(ffmpeg), "-hide_banner", "-nostdin", "-y", "-benchmark"]
    if backend == "cpu":
        return [
            *common, "-i", str(source), "-vf", "scale=1280:720",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            str(target),
        ]
    need(backend == "qsv", "Unsupported synthetic transcode backend")
    encoder = "hevc_qsv" if codec == "hevc" else "h264_qsv"
    return [
        *common, "-init_hw_device", "qsv=hw", "-filter_hw_device", "hw",
        "-hwaccel", "qsv", "-hwaccel_output_format", "qsv",
        "-i", str(source), "-vf", "vpp_qsv=w=1280:h=720",
        "-an", "-c:v", encoder, "-global_quality", "24", "-look_ahead", "0",
        str(target),
    ]


def parse_metrics(stderr: str, elapsed: float, duration: int) -> tuple[float, dict, float]:
    speeds = re.findall(r"speed=\s*([0-9]+(?:\.[0-9]+)?)x", stderr)
    speed = float(speeds[-1]) if speeds else duration / elapsed
    timing = re.findall(
        r"bench:\s+utime=([0-9.]+)s\s+stime=([0-9.]+)s\s+rtime=([0-9.]+)s",
        stderr,
    )
    memory = re.findall(r"bench:\s+maxrss=([0-9]+)KiB", stderr)
    metrics = {
        "user_seconds": float(timing[-1][0]) if timing else None,
        "system_seconds": float(timing[-1][1]) if timing else None,
        "max_rss_kib": int(memory[-1]) if memory else None,
    }
    measured_elapsed = float(timing[-1][2]) if timing else elapsed
    return round(speed, 3), metrics, measured_elapsed


def probe_output(ffprobe: Path, ffmpeg: Path, source: Path, output: Path) -> dict:
    arguments = [
        str(ffprobe), "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,nb_read_frames:format=duration,size",
        "-of", "json", str(output),
    ]
    result = subprocess.run(arguments, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30,
                            check=False)
    need(result.returncode == 0, "FFprobe could not validate a synthetic output")
    try:
        value = json.loads(result.stdout)
        stream = value["streams"][0]
        container = value["format"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise ConfigError("FFprobe returned an invalid synthetic-output record") from error

    quality_args = [
        str(ffmpeg), "-hide_banner", "-nostdin", "-i", str(source),
        "-i", str(output), "-lavfi", "[0:v]scale=1280:720[ref];[ref][1:v]ssim",
        "-f", "null", "-",
    ]
    quality_code, quality_text, _ = command(quality_args, timeout=120)
    matches = re.findall(r"All:([0-9]+(?:\.[0-9]+)?)", quality_text)
    need(quality_code == 0 and matches,
         "Synthetic output quality comparison failed")
    quality = float(matches[-1])
    need(quality >= 0.85, "Synthetic output quality fell below the reviewed tolerance")

    hasher = hashlib.sha256()
    with output.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return {
        "duration_seconds": round(float(container["duration"]), 3),
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "frames": int(stream["nb_read_frames"]),
        "size_bytes": int(container["size"]),
        "sha256": hasher.hexdigest(),
        "ssim": round(quality, 6),
    }


def finish_run(role: str, backend: str, codec: str, concurrency: int,
               code: int, stderr: str, elapsed: float, output: Path,
               ffprobe: Path, ffmpeg: Path, source: Path) -> dict:
    need(code == 0 and output.is_file(),
         f"The {role} synthetic transcode failed; CPU fallback remains selected")
    speed, metrics, measured_elapsed = parse_metrics(
        stderr, elapsed, FIXTURE["duration_seconds"])
    return {
        "role": role,
        "backend": backend,
        "codec": codec,
        "status": "passed",
        "concurrency": concurrency,
        "elapsed_seconds": round(measured_elapsed, 3),
        "speed": speed,
        "metrics": metrics,
        "output": probe_output(ffprobe, ffmpeg, source, output),
    }


def run_one(role: str, backend: str, codec: str, source: Path, output: Path,
            ffmpeg: Path, ffprobe: Path) -> dict:
    code, stderr, elapsed = command(
        transcode_arguments(ffmpeg, source, output, backend, codec))
    return finish_run(role, backend, codec, 1, code, stderr, elapsed, output,
                      ffprobe, ffmpeg, source)


def run_pair(source: Path, directory: Path, ffmpeg: Path, ffprobe: Path) -> list[dict]:
    outputs = [directory / "qsv-concurrent-a.mp4",
               directory / "qsv-concurrent-b.mp4"]
    processes = []
    starts = []
    for output in outputs:
        starts.append(time.perf_counter())
        processes.append(subprocess.Popen(
            transcode_arguments(ffmpeg, source, output, "qsv"),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace",
        ))
    completed = []
    try:
        for index, process in enumerate(processes):
            _, stderr = process.communicate(timeout=180)
            completed.append((process.returncode, stderr,
                              time.perf_counter() - starts[index]))
    except subprocess.TimeoutExpired as error:
        for process in processes:
            if process.poll() is None:
                process.kill()
        for process in processes:
            process.communicate()
        raise ConfigError("Concurrent QSV proof timed out") from error
    results = []
    for index, (code, stderr, elapsed) in enumerate(completed):
        role = "qsv-concurrent-a" if index == 0 else "qsv-concurrent-b"
        results.append(finish_run(
            role, "qsv", "h264", 2, code, stderr, elapsed,
            outputs[index], ffprobe, ffmpeg, source,
        ))
    return results


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
    except FileExistsError as error:
        raise ConfigError("Evidence output already exists; refusing overwrite") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", help="Path to Jellyfin FFmpeg")
    parser.add_argument("--confirm", help=f"Required phrase: {CONFIRMATION}")
    parser.add_argument("--include-hevc", action="store_true",
                        help="Add a non-required synthetic QSV HEVC encode")
    parser.add_argument("--evidence", type=Path,
                        help="Create a sanitized proof JSON file (never overwrite)")
    parser.add_argument("--audit-only", action="store_true",
                        help="Print sanitized capability evidence without a trial")
    arguments = parser.parse_args()
    try:
        ffmpeg = locate_ffmpeg(arguments.ffmpeg)
        capability = audit(ffmpeg)
        if arguments.audit_only:
            print(json.dumps(capability, indent=2, sort_keys=True))
            return 0
        need(arguments.confirm == CONFIRMATION,
             f"Synthetic execution requires --confirm {CONFIRMATION}")
        need(capability["decision"]["qsv"]["status"] ==
             "eligible-for-synthetic-test",
             "Intel QSV is not eligible; CPU fallback remains selected")
        ffprobe = locate_ffprobe(ffmpeg)
        runs = []
        with tempfile.TemporaryDirectory(prefix="homelab-jellyfin-qsv-") as temporary:
            directory = Path(temporary)
            source = directory / "synthetic-source.mp4"
            generate_fixture(ffmpeg, source)
            runs.append(run_one("cpu-baseline", "cpu", "h264", source,
                                directory / "cpu-baseline.mp4", ffmpeg, ffprobe))
            runs.append(run_one("qsv-single", "qsv", "h264", source,
                                directory / "qsv-single.mp4", ffmpeg, ffprobe))
            runs.extend(run_pair(source, directory, ffmpeg, ffprobe))
            if arguments.include_hevc:
                runs.append(run_one("qsv-hevc", "qsv", "hevc", source,
                                    directory / "qsv-hevc.mp4", ffmpeg, ffprobe))
        proof = make_proof(capability, FIXTURE, runs,
                           temporary_outputs_removed=True)
        if arguments.evidence:
            write_new(arguments.evidence.resolve(), proof)
        print(json.dumps(proof, indent=2, sort_keys=True))
        return 0
    except (ConfigError, OSError, subprocess.SubprocessError) as error:
        print(f"Jellyfin acceleration trial refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
