"""Disposable Jellyfin 12 native backup, restore, and direct-play trial."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homelab.config import ConfigError, need
from homelab.jellyfin import RECOVERY_CONTRACT, validate_recovery_evidence


CONTRACT = RECOVERY_CONTRACT
CONFIRM = "RUN-ISOLATED-JELLYFIN-TRIAL"
FIXTURE_NAME = "phase6-jellyfin-direct-play.mp4"
USERNAME = "phase6-jellyfin-admin"
DEVICE_ID = "phase6-jellyfin-native-trial"
CLIENT_VERSION = "0.7.0-alpha.6"


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def network_xml(path: Path, port: int) -> None:
    root = ElementTree.Element("NetworkConfiguration")
    values = (
        ("BaseUrl", ""), ("EnableHttps", "false"), ("RequireHttps", "false"),
        ("CertificatePath", ""), ("CertificatePassword", ""),
        ("InternalHttpPort", str(port)), ("InternalHttpsPort", "18920"),
        ("PublicHttpPort", str(port)), ("PublicHttpsPort", "18920"),
        ("AutoDiscovery", "false"), ("EnableIPv4", "true"),
        ("EnableIPv6", "false"), ("EnableRemoteAccess", "false"),
        ("IgnoreVirtualInterfaces", "true"),
        ("EnablePublishedServerUriByRequest", "false"),
        ("IsRemoteIPFilterBlacklist", "false"),
    )
    for name, text in values:
        ElementTree.SubElement(root, name).text = text
    for name in ("LocalNetworkSubnets", "KnownProxies", "VirtualInterfaceNames",
                 "PublishedServerUriBySubnet", "RemoteIPFilter"):
        ElementTree.SubElement(root, name)
    addresses = ElementTree.SubElement(root, "LocalNetworkAddresses")
    ElementTree.SubElement(addresses, "string").text = "127.0.0.1"
    path.parent.mkdir(parents=True, exist_ok=True)
    ElementTree.ElementTree(root).write(
        path, encoding="utf-8", xml_declaration=True, short_empty_elements=True)


def auth_header(token: str | None = None) -> str:
    fields = [
        'MediaBrowser Client="HomeLab-SelfHosting"',
        'Device="Native Recovery Trial"',
        f'DeviceId="{DEVICE_ID}"',
        f'Version="{CLIENT_VERSION}"',
    ]
    if token:
        fields.append(f'Token="{token}"')
    return ", ".join(fields)


def request(base: str, method: str, route: str, *, body: object | None = None,
            token: str | None = None, timeout: int = 30,
            binary: bool = False):
    data = None
    headers = {"Authorization": auth_header(token)}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    value = urllib.request.Request(base + route, data=data, headers=headers,
                                   method=method)
    try:
        with urllib.request.urlopen(value, timeout=timeout) as response:
            payload = response.read()
            content_type = response.headers.get_content_type()
            status = response.status
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise ConfigError(
            f"Jellyfin {method} {route} returned {error.code}: {detail}") from error
    if binary:
        return status, content_type, payload
    if not payload:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigError(f"Jellyfin {method} {route} returned invalid JSON") from error


def process_arguments(binary: Path, state: Path, web: Path, ffmpeg: Path,
                      restore: Path | None = None) -> list[str]:
    values = [
        str(binary), "--datadir", str(state / "data"),
        "--cachedir", str(state / "cache"),
        "--configdir", str(state / "config"),
        "--logdir", str(state / "log"),
        "--webdir", str(web), "--ffmpeg", str(ffmpeg), "--nonetchange",
    ]
    if restore is not None:
        values.extend(["--restore-archive", str(restore)])
    return values


def start(binary: Path, state: Path, web: Path, ffmpeg: Path,
          restore: Path | None = None) -> subprocess.Popen:
    for name in ("data", "cache", "config", "log"):
        (state / name).mkdir(parents=True, exist_ok=True)
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(
        process_arguments(binary, state, web, ffmpeg, restore),
        cwd=binary.parent, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=creationflags)


def wait_ready(base: str, process: subprocess.Popen, timeout: int = 150) -> dict:
    deadline = time.monotonic() + timeout
    last = "not reachable"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ConfigError(
                f"Isolated Jellyfin exited before readiness with code {process.returncode}")
        try:
            info = request(base, "GET", "/System/Info/Public", timeout=5)
            if info and info.get("Version"):
                return info
        except (ConfigError, OSError) as error:
            last = str(error)
        time.sleep(1)
    raise ConfigError(f"Isolated Jellyfin did not become ready: {last}")


def stop(base: str, process: subprocess.Popen, token: str | None) -> None:
    if process.poll() is not None:
        return
    if token:
        try:
            request(base, "POST", "/System/Shutdown", token=token, timeout=10)
        except (ConfigError, OSError):
            pass
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)


def make_fixture(ffmpeg: Path, destination: Path) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0x204060:s=320x180:r=24:d=1",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        "-c:a", "aac", "-b:a", "64k", "-shortest", str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90,
                            check=False, creationflags=(
                                subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
    need(result.returncode == 0 and destination.is_file()
         and destination.stat().st_size > 1024,
         "Bundled Jellyfin FFmpeg could not create the synthetic MP4")
    return {"name": destination.name, "bytes": destination.stat().st_size,
            "sha256": sha256(destination)}


def setup(base: str, password: str) -> dict:
    request(base, "POST", "/Startup/Configuration", body={
        "ServerName": "Phase 6 Jellyfin Recovery Trial",
        "UICulture": "en-US", "MetadataCountryCode": "US",
        "PreferredMetadataLanguage": "en",
    })
    # Jellyfin 12 initializes the first startup user when the wizard opens the
    # user step. Match the installed web client's GET-then-POST sequence.
    request(base, "GET", "/Startup/User")
    request(base, "POST", "/Startup/User",
            body={"Name": USERNAME, "Password": password})
    request(base, "POST", "/Startup/RemoteAccess",
            body={"EnableRemoteAccess": False})
    request(base, "POST", "/Startup/Complete")
    return login(base, password)


def login(base: str, password: str) -> dict:
    value = request(base, "POST", "/Users/AuthenticateByName",
                    body={"Username": USERNAME, "Pw": password})
    need(isinstance(value, dict) and value.get("AccessToken")
         and (value.get("User") or {}).get("Id"),
         "Synthetic Jellyfin login did not return a token and user")
    return {"token": value["AccessToken"], "user_id": value["User"]["Id"]}


def add_library(base: str, token: str, media: Path) -> None:
    query = urllib.parse.urlencode([
        ("name", "Phase 6 Synthetic Video"), ("collectionType", "movies"),
        ("paths", str(media)), ("refreshLibrary", "false"),
    ])
    request(base, "POST", "/Library/VirtualFolders?" + query,
            body={}, token=token, timeout=30)
    request(base, "POST", "/Library/Refresh", token=token, timeout=30)


def wait_library_idle(base: str, token: str, timeout: int = 150) -> None:
    deadline = time.monotonic() + timeout
    quiet_since = None
    while time.monotonic() < deadline:
        tasks = request(base, "GET", "/ScheduledTasks", token=token)
        scan_running = any(
            str(task.get("State", "")).casefold() == "running"
            and "scan media library" in str(task.get("Name", "")).casefold()
            for task in (tasks if isinstance(tasks, list) else [])
        )
        if scan_running:
            quiet_since = None
        elif quiet_since is None:
            quiet_since = time.monotonic()
        elif time.monotonic() - quiet_since >= 5:
            return
        time.sleep(1)
    raise ConfigError("Synthetic Jellyfin library scan did not become idle")


def find_fixture(base: str, token: str, timeout: int = 150) -> dict:
    query = urllib.parse.urlencode({
        "Recursive": "true", "IncludeItemTypes": "Movie",
        "SearchTerm": Path(FIXTURE_NAME).stem, "Fields": "Path,MediaSources",
        "Limit": "10",
    })
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = request(base, "GET", "/Items?" + query, token=token)
        items = value.get("Items", []) if isinstance(value, dict) else []
        for item in items:
            if Path(str(item.get("Path", ""))).name.casefold() == FIXTURE_NAME.casefold():
                return item
        time.sleep(2)
    raise ConfigError("Synthetic Jellyfin library item was not indexed")


def direct_play(base: str, token: str, item: dict, fixture: Path) -> dict:
    sources = item.get("MediaSources") or []
    source_id = sources[0].get("Id") if sources else None
    need(item.get("Id") and source_id, "Synthetic Jellyfin item lacks a media source")
    query = urllib.parse.urlencode({"Static": "true", "MediaSourceId": source_id})
    status, content_type, payload = request(
        base, "GET", f'/Videos/{item["Id"]}/stream.mp4?' + query,
        token=token, timeout=60, binary=True)
    expected = sha256(fixture)
    actual = hashlib.sha256(payload).hexdigest()
    need(status == 200 and actual == expected and len(payload) == fixture.stat().st_size,
         "Synthetic Jellyfin direct-play bytes changed")
    return {"item_id": item["Id"], "media_source_id": source_id,
            "status": status, "content_type": content_type,
            "bytes": len(payload), "sha256": actual, "exact": True}


def create_backup(base: str, token: str, state: Path,
                  destination: Path) -> dict:
    manifest = request(base, "POST", "/Backup/Create", token=token, timeout=180,
                       body={"Database": True, "Metadata": True,
                             "Subtitles": True, "Trickplay": True})
    need(isinstance(manifest, dict) and manifest.get("Path")
         and manifest.get("ServerVersion"),
         "Jellyfin backup did not return a manifest")
    source = Path(manifest["Path"])
    if not source.is_absolute():
        source = state / "data" / "backups" / source
    need(source.is_file(), "Jellyfin backup archive is missing")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    with zipfile.ZipFile(destination, "r") as archive:
        names = archive.namelist()
        bad = archive.testzip()
    need(bad is None and names, "Jellyfin backup archive failed ZIP validation")
    folded = {name.replace("\\", "/").casefold() for name in names}
    required_database_exports = {
        "database/users.json",
        "database/baseitems.json",
        "database/userdata.json",
    }
    need(required_database_exports.issubset(folded),
         "Jellyfin backup archive lacks required database exports")
    need("manifest.json" in folded and "config/system.xml" in folded,
         "Jellyfin backup archive lacks its manifest or system configuration")
    return {"server_version": manifest["ServerVersion"],
            "backup_engine_version": manifest.get("BackupEngineVersion"),
            "date_created": manifest.get("DateCreated"),
            "options": manifest.get("Options"), "bytes": destination.stat().st_size,
            "sha256": sha256(destination), "zip_entries": len(names),
            "zip_integrity": True, "database_present": True,
            "database_format": "json-table-export"}


def validate_runtime(binary: Path, web: Path, ffmpeg: Path, root: Path,
                     output: Path, port: int) -> None:
    need(os.name == "nt", "The native trial currently requires Windows")
    need(binary.is_file() and web.is_dir() and ffmpeg.is_file(),
         "Choose the matching installed Jellyfin binary, web and FFmpeg paths")
    need(1024 <= port <= 65535 and port != 8096,
         "Choose a non-production unprivileged Jellyfin port")
    need(root.is_absolute() and output.is_absolute(), "Trial paths must be absolute")
    need(not root.exists(), "Trial root must be absent")
    need(not output.is_relative_to(root) and not root.is_relative_to(output),
         "Trial evidence output must not overlap disposable state")


def run(root: Path, output: Path, binary: Path, web: Path, ffmpeg: Path,
        port: int, keep: bool = False) -> dict:
    validate_runtime(binary, web, ffmpeg, root, output, port)
    base = f"http://127.0.0.1:{port}"
    source = root / "source-state"
    restored = root / "restored-state"
    media = root / "media"
    recovery = root / "recovery" / "jellyfin-backup.zip"
    fixture_path = media / FIXTURE_NAME
    password = secrets.token_urlsafe(48)
    source_process = None
    restored_process = None
    success = False
    evidence = None
    root.mkdir(parents=True)
    try:
        fixture = make_fixture(ffmpeg, fixture_path)
        network_xml(source / "config" / "network.xml", port)
        source_process = start(binary, source, web, ffmpeg)
        source_info = wait_ready(base, source_process)
        need(source_info.get("StartupWizardCompleted") is False,
             "Disposable source was not a fresh Jellyfin instance")
        source_auth = setup(base, password)
        add_library(base, source_auth["token"], media)
        source_item = find_fixture(base, source_auth["token"])
        wait_library_idle(base, source_auth["token"])
        source_direct = direct_play(
            base, source_auth["token"], source_item, fixture_path)
        backup = create_backup(
            base, source_auth["token"], source, recovery)
        need(str(backup["server_version"]).startswith("12.4"),
             "The trial backup was not created by Jellyfin 12.4")
        stop(base, source_process, source_auth["token"])
        source_process = None
        shutil.rmtree(source)
        need(not source.exists(), "Source state remained before independent recovery")

        network_xml(restored / "config" / "network.xml", port)
        restored_process = start(binary, restored, web, ffmpeg)
        target_info = wait_ready(base, restored_process)
        need(target_info.get("StartupWizardCompleted") is False
             and target_info.get("Version") == source_info.get("Version"),
             "Restore target was not a fresh matching Jellyfin instance")
        target_auth = setup(base, secrets.token_urlsafe(48))
        stop(base, restored_process, target_auth["token"])
        restored_process = None

        restored_process = start(binary, restored, web, ffmpeg, recovery)
        try:
            restored_info = wait_ready(base, restored_process)
        except ConfigError:
            if restored_process.poll() == 0:
                restored_process = start(binary, restored, web, ffmpeg)
                restored_info = wait_ready(base, restored_process)
            else:
                raise
        need(str(restored_info.get("Version", "")).startswith("12.4"),
             "Recovered Jellyfin version does not match the backup")
        restored_auth = login(base, password)
        restored_item = find_fixture(base, restored_auth["token"])
        restored_direct = direct_play(
            base, restored_auth["token"], restored_item, fixture_path)
        stop(base, restored_process, restored_auth["token"])
        restored_process = None

        restored_process = start(binary, restored, web, ffmpeg)
        restart_info = wait_ready(base, restored_process)
        restart_auth = login(base, password)
        restart_item = find_fixture(base, restart_auth["token"])
        restart_direct = direct_play(
            base, restart_auth["token"], restart_item, fixture_path)
        stop(base, restored_process, restart_auth["token"])
        restored_process = None
        evidence = {
            "kind": "homelab-jellyfin-native-recovery-evidence",
            "contract": CONTRACT,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "jellyfin_version": source_info["Version"],
            "deployment": "native-windows-isolated",
            "fixture": fixture,
            "source_direct_play": source_direct,
            "backup": backup,
            "source_state_removed_before_restore": True,
            "restore_target_initialized_same_version": True,
            "restore_same_version": True,
            "restored_direct_play": restored_direct,
            "restart_direct_play": restart_direct,
            "restart_persistence_verified": True,
            "production_service_changed": False,
            "production_media_used": False,
            "production_credentials_used": False,
            "synthetic_credentials_retained": False,
            "gpu_used": False,
            "transcode_requested": False,
            "direct_play_exact": all(item["exact"] for item in (
                source_direct, restored_direct, restart_direct)),
            "trial_id": str(uuid.uuid4()),
        }
        evidence = validate_recovery_evidence(evidence)
        atomic_json(output, evidence)
        success = True
        return evidence
    finally:
        if source_process is not None:
            stop(base, source_process, None)
        if restored_process is not None:
            stop(base, restored_process, None)
        if success and not keep:
            shutil.rmtree(root, ignore_errors=False)


def main(arguments=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--web", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18096)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(arguments)
    try:
        need(args.confirm == CONFIRM, f"Confirmation must equal {CONFIRM}")
        evidence = run(args.root.resolve(), args.output.resolve(),
                       args.binary.resolve(), args.web.resolve(),
                       args.ffmpeg.resolve(), args.port, args.keep)
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0
    except (ConfigError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
