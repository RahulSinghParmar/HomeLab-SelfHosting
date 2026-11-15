"""Disposable stopped-backup and independent-restore media-management trial."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homelab.config import ConfigError, canonical, need
from homelab import media_management as media


CONFIRM = "RUN-ISOLATED-MEDIA-MANAGEMENT-TRIAL"


def run(arguments: list[str], *, timeout: int = 120, check: bool = True) -> str:
    result = subprocess.run(
        arguments, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, check=False,
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )
    if check and result.returncode != 0:
        # Do not include application logs: they can contain generated credentials.
        raise ConfigError(f"Isolated Docker command failed with exit code {result.returncode}")
    return result.stdout.strip()


def free_ports() -> dict[str, int]:
    values = {}
    held = []
    try:
        for name in media.PUBLISHED:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 0))
            held.append(sock)
            values[name] = sock.getsockname()[1]
        return values
    finally:
        for sock in held:
            sock.close()


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def tree_manifest(root: Path) -> dict[str, dict[str, int | str]]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ConfigError("Synthetic recovery tree contains an unexpected symbolic link")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            result[relative] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    return result


def sqlite_quick_check(root: Path) -> int:
    files = []
    for suffix in ("*.db", "*.sqlite", "*.sqlite3"):
        files.extend(root.rglob(suffix))
    checked = 0
    for path in sorted(set(files)):
        encoded = urllib.parse.quote(str(path.resolve()).replace("\\", "/"), safe="/:")
        database = None
        try:
            database = sqlite3.connect(f"file:{encoded}?mode=ro", uri=True, timeout=10)
            row = database.execute("PRAGMA quick_check").fetchone()
        except sqlite3.DatabaseError as error:
            raise ConfigError("A stopped synthetic application database failed SQLite validation") from error
        finally:
            if database is not None:
                database.close()
        need(row == ("ok",), "A stopped synthetic application database failed SQLite quick_check")
        checked += 1
    return checked


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def selection(root: Path, selected: list[str], ports: dict[str, int]) -> dict:
    target = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(
        platform.system())
    need(target is not None, "Unsupported synthetic trial platform")
    return {
        "kind": "homelab-media-management-selection",
        "contract": media.CONTRACT,
        "target_platform": target,
        "selected": selected,
        "config_root": str((root / "config").resolve()),
        "data_root": str((root / "data").resolve()),
        "timezone": "Etc/UTC",
        "uid": 1000,
        "gid": 1000,
        "ports": ports,
        "automatic_actions": dict(media.AUTOMATIC_ACTIONS),
    }


def prepare_roots(plan: dict) -> None:
    Path(plan["roots"]["config"]).mkdir(parents=True, exist_ok=False)
    Path(plan["roots"]["data"]).mkdir(parents=True, exist_ok=False)
    for name in sorted(set(plan["selected"]) & set(media.CONFIG_TARGETS)):
        root = Path(plan["roots"]["config"]) / name
        root.mkdir()
        (root / "homelab-recovery-sentinel.txt").write_text(
            f"{plan['plan_id']}:{name}\n", encoding="utf-8")


def shared_storage_exercise(data: Path) -> dict:
    source = data / "downloads" / "phase6" / "fixture.bin"
    linked = data / "library" / "phase6" / "fixture.bin"
    moved = source.with_name("fixture.moved.bin")
    source.parent.mkdir(parents=True, exist_ok=True)
    linked.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes((b"homelab-media-management-trial\n" * 2048))
    os.link(source, linked)
    hardlink = os.stat(source).st_ino == os.stat(linked).st_ino
    expected = sha256(source)
    os.replace(source, moved)
    atomic_move = not source.exists() and moved.is_file() and sha256(moved) == expected
    need(hardlink and atomic_move and sha256(linked) == expected,
         "Synthetic shared /data hardlink or atomic move failed")
    return {"sha256": expected, "relative": linked.relative_to(data).as_posix()}


def compose_command(file: Path, project: str, *arguments: str) -> list[str]:
    return ["docker", "compose", "-f", str(file), "-p", project, *arguments]


def container_id(file: Path, project: str, service: str) -> str:
    value = run(compose_command(file, project, "ps", "--all", "-q", service), timeout=30)
    need(value and len(value.splitlines()) == 1, "Isolated service container identity is ambiguous")
    return value


def wait_healthy(file: Path, project: str, selected: list[str], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    pending = set(selected)
    while pending and time.monotonic() < deadline:
        for name in tuple(pending):
            identifier = container_id(file, project, name)
            raw = run(["docker", "inspect", "--format", "{{json .State}}", identifier], timeout=30)
            state = json.loads(raw)
            need(state.get("Running") is True,
                 "An isolated media-management service exited before validation")
            if (state.get("Health") or {}).get("Status") == "healthy":
                pending.remove(name)
        if pending:
            time.sleep(2)
    need(not pending, "Isolated media-management services did not become healthy in time")


def ensure_stopped(file: Path, project: str, selected: list[str]) -> None:
    for name in selected:
        identifier = container_id(file, project, name)
        raw = run(["docker", "inspect", "--format", "{{json .State}}", identifier], timeout=30)
        state = json.loads(raw)
        need(state.get("Running") is False and state.get("Paused") is False,
             "Application-consistent backup requires every selected service to be stopped")


def ensure_removed(file: Path, project: str) -> None:
    identifiers = run(compose_command(file, project, "ps", "--all", "-q"), timeout=30)
    need(not identifiers, "Synthetic media-management containers remained after cleanup")


def parse_size(value: str) -> float:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)\s*", value)
    need(match is not None, "Docker returned an unsupported memory value")
    amount = float(match.group(1))
    unit = match.group(2)
    factors = {"B": 1 / 1024**2, "KiB": 1 / 1024, "MiB": 1,
               "GiB": 1024, "kB": 1 / 1000, "MB": 1, "GB": 1000}
    need(unit in factors, "Docker returned an unsupported memory unit")
    return round(amount * factors[unit], 3)


def measurements(file: Path, project: str, selected: list[str]) -> dict:
    memory = {}
    cpu = {}
    for name in selected:
        identifier = container_id(file, project, name)
        raw = run(["docker", "stats", "--no-stream", "--format", "{{json .}}", identifier],
                  timeout=60)
        row = json.loads(raw)
        memory[name] = parse_size(row["MemUsage"].split("/")[0].strip())
        cpu[name] = float(row["CPUPerc"].rstrip("%"))
    return {"memory_mib": memory, "peak_cpu_percent": cpu,
            "total_memory_mib": round(sum(memory.values()), 3)}


def validate_sentinels(root: Path, selected: list[str], expected_plan_id: str) -> None:
    for name in sorted(set(selected) & set(media.CONFIG_TARGETS)):
        path = root / name / "homelab-recovery-sentinel.txt"
        need(path.read_text(encoding="utf-8") == f"{expected_plan_id}:{name}\n",
             "Synthetic configuration sentinel did not survive recovery")


def render_trial(plan: dict, destination: Path) -> None:
    spec = media.compose(plan, trial_internal_network=True)
    for service in spec["services"].values():
        service["restart"] = "no"
    write_json(destination, spec)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--components", required=True,
                        help="Comma-separated explicit component selection")
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=420)
    args = parser.parse_args()
    need(args.confirm == CONFIRM, f"Confirmation must be exactly {CONFIRM}")
    need(60 <= args.timeout <= 1800, "Trial timeout must be between 60 and 1800 seconds")
    selected = sorted({item.strip() for item in args.components.split(",") if item.strip()})
    need(len(selected) == len([item for item in args.components.split(",") if item.strip()]),
         "Component selection contains duplicates")
    output = args.output.resolve()
    need(output.parent.is_dir() and not output.exists(), "Choose a new evidence file in an existing directory")
    run(["docker", "version", "--format", "{{.Server.Version}}"], timeout=30)
    run(["docker", "compose", "version", "--short"], timeout=30)
    plan = None
    result = None
    with tempfile.TemporaryDirectory(prefix="homelab-media-management-") as temporary:
        trial = Path(temporary).resolve()
        original = trial / "original"
        restored = trial / "restored"
        plan = media.make_plan(selection(original, selected, free_ports()))
        for name in selected:
            run(["docker", "image", "inspect", plan["images"][name]["image"]], timeout=30)
        prepare_roots(plan)
        shared = (shared_storage_exercise(Path(plan["roots"]["data"]))
                  if plan["shared_data"] else None)
        original_compose = original / "compose.json"
        render_trial(plan, original_compose)
        original_project = "hl-media-original-" + plan["plan_id"][:10]
        restore_project = "hl-media-restore-" + plan["plan_id"][:10]
        original_down = False
        restore_down = False
        try:
            run(compose_command(original_compose, original_project, "up", "-d",
                                "--no-build", "--pull", "never"), timeout=args.timeout)
            wait_healthy(original_compose, original_project, plan["selected"], args.timeout)
            first_resources = measurements(original_compose, original_project, plan["selected"])
            run(compose_command(original_compose, original_project, "stop", "-t", "60"),
                timeout=120)
            ensure_stopped(original_compose, original_project, plan["selected"])
            sqlite_before = sqlite_quick_check(Path(plan["roots"]["config"]))
            snapshot = trial / "snapshot"
            shutil.copytree(Path(plan["roots"]["config"]), snapshot / "config")
            shutil.copytree(Path(plan["roots"]["data"]), snapshot / "data")
            manifest = {"config": tree_manifest(snapshot / "config"),
                        "data": tree_manifest(snapshot / "data")}
            manifest_hash = hashlib.sha256(canonical(manifest).encode("ascii")).hexdigest()
            run(compose_command(original_compose, original_project, "down", "--remove-orphans"),
                timeout=120)
            ensure_removed(original_compose, original_project)
            original_down = True

            restore_selection = selection(restored, selected, free_ports())
            restore_plan = media.make_plan(restore_selection)
            need(restore_plan["selected"] == plan["selected"], "Restore selection changed")
            (restored / "config").parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(snapshot / "config", restored / "config")
            shutil.copytree(snapshot / "data", restored / "data")
            need(tree_manifest(snapshot / "config") == tree_manifest(restored / "config")
                 and tree_manifest(snapshot / "data") == tree_manifest(restored / "data"),
                 "Independent restore did not reproduce the stopped backup manifest")
            restore_compose = restored / "compose.json"
            render_trial(restore_plan, restore_compose)
            run(compose_command(restore_compose, restore_project, "up", "-d",
                                "--no-build", "--pull", "never"), timeout=args.timeout)
            wait_healthy(restore_compose, restore_project, restore_plan["selected"], args.timeout)
            second_resources = measurements(restore_compose, restore_project, restore_plan["selected"])
            validate_sentinels(restored / "config", restore_plan["selected"], plan["plan_id"])
            sqlite_after = sqlite_quick_check(restored / "config")
            if shared is not None:
                restored_file = restored / "data" / Path(shared["relative"])
                need(restored_file.is_file() and sha256(restored_file) == shared["sha256"],
                     "Synthetic shared /data content did not survive recovery")
            run(compose_command(restore_compose, restore_project, "stop", "-t", "60"),
                timeout=120)
            ensure_stopped(restore_compose, restore_project, restore_plan["selected"])
            run(compose_command(restore_compose, restore_project, "down", "--remove-orphans"),
                timeout=120)
            ensure_removed(restore_compose, restore_project)
            restore_down = True
            memory = {name: max(first_resources["memory_mib"][name],
                                second_resources["memory_mib"][name]) for name in selected}
            cpu = {name: max(first_resources["peak_cpu_percent"][name],
                             second_resources["peak_cpu_percent"][name]) for name in selected}
            result = {
                "kind": "homelab-media-management-recovery-evidence",
                "contract": media.CONTRACT,
                "plan_id": plan["plan_id"],
                "selected": plan["selected"],
                "backup": {"services_stopped": True,
                           "config_components": sorted(set(selected) & set(media.CONFIG_TARGETS)),
                           "manifest_sha256": manifest_hash},
                "sqlite": {"checked": sqlite_before + sqlite_after, "all_ok": True},
                "shared_storage": {"applicable": bool(plan["shared_data"]),
                                   "hardlink": shared is not None,
                                   "atomic_move": shared is not None,
                                   "content_restored": True},
                "restore": {"independent_root": True, "started": plan["selected"],
                            "healthy": plan["selected"], "sentinel_match": True},
                "resources": {"memory_mib": memory, "peak_cpu_percent": cpu,
                              "total_memory_mib": round(sum(memory.values()), 3)},
                "safety": {"production_paths_used": False,
                           "production_credentials_used": False,
                           "external_requests_enabled": False,
                           "automatic_actions_enabled": False,
                           "cleanup_completed": True},
            }
        finally:
            if not restore_down and (restored / "compose.json").is_file():
                run(compose_command(restored / "compose.json", restore_project,
                                    "down", "--remove-orphans"), timeout=120, check=False)
            if not original_down and original_compose.is_file():
                run(compose_command(original_compose, original_project,
                                    "down", "--remove-orphans"), timeout=120, check=False)
    need(plan is not None and result is not None, "Synthetic media-management recovery did not complete")
    media.validate_recovery_evidence(result, plan)
    write_json(output, result)
    print(json.dumps({"status": "passed", "evidence": str(output),
                      "selected": result["selected"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ConfigError, OSError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
