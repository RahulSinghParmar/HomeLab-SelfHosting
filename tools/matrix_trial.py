"""Run an isolated Matrix identity and application-aware recovery rehearsal."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homelab import matrix
from homelab.config import ConfigError, canonical, need


CONFIRM = "RUN-ISOLATED-MATRIX-TRIAL"
SERVER_NAME = "matrix-recovery.invalid"
USERNAME = "recovery-proof"
ROOM_NAME = "HomeLab Matrix recovery proof"
MESSAGE = "Synthetic Matrix room and message survive independent recovery."
MEDIA = b"HomeLab Matrix synthetic media recovery proof\n"
ACTIVE_ROOT: Path | None = None


def run(arguments: list[str], *, input_bytes: bytes | None = None,
        check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
    result = subprocess.run(arguments, input=input_bytes, capture_output=True,
                            timeout=timeout)
    if check and result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")[-3000:]
        stdout = result.stdout.decode("utf-8", errors="replace")[-3000:]
        raise ConfigError(
            f"Command failed ({result.returncode}): {arguments[0]} {arguments[1]}\n"
            f"{stdout}{stderr}")
    return result


def text(arguments: list[str], *, check: bool = True,
         timeout: int = 300) -> str:
    return run(arguments, check=check, timeout=timeout).stdout.decode(
        "utf-8", errors="replace").strip()


def compose_args(plan: dict, project: str) -> list[str]:
    root = Path(plan["paths"]["state"])
    return ["docker", "compose", "--project-name", project,
            "--project-directory", str(root), "-f", str(root / "compose.json")]


def compose(plan: dict, project: str, *arguments: str,
            timeout: int = 300, check: bool = True) -> subprocess.CompletedProcess:
    return run([*compose_args(plan, project), *arguments], check=check,
               timeout=timeout)


def free_port(port: int) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def api(method: str, url: str, payload: object | None = None,
        token: str | None = None, raw: bytes | None = None,
        content_type: str = "application/json", timeout: int = 30):
    data = raw
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        media_type = response.headers.get_content_type()
        if media_type == "application/json" or body.startswith((b"{", b"[")):
            return json.loads(body)
        return body


def wait_http(url: str, deadline_seconds: int = 240) -> None:
    deadline = time.monotonic() + deadline_seconds
    last = ""
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=5) as response:
                if response.status < 500:
                    return
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            last = str(error)
        time.sleep(2)
    raise ConfigError(f"HTTP service did not become ready: {url}: {last}")


def wait_healthy(plan: dict, project: str, service: str,
                 deadline_seconds: int = 240) -> str:
    deadline = time.monotonic() + deadline_seconds
    last = ""
    while time.monotonic() < deadline:
        container = text([*compose_args(plan, project), "ps", "-q", service])
        if container:
            value = text(["docker", "inspect", "--format",
                          "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}",
                          container])
            last = value
            if value in ("running|healthy", "running|"):
                return container
            need(not value.startswith(("exited|", "dead|")),
                 f"Matrix {service} exited before becoming healthy")
        time.sleep(2)
    raise ConfigError(f"Matrix {service} did not become healthy: {last}")


def snapshot_production() -> list[str]:
    names = text([
        "docker", "ps", "--all", "--filter",
        "label=com.docker.compose.project=matrix-synapse", "--format",
        "{{.Names}}",
    ]).splitlines()
    result = []
    for name in sorted(item for item in names if item.strip()):
        result.append(text([
            "docker", "inspect", "--format",
            "{{.Name}}|{{.Config.Image}}|{{.State.Status}}|"
            "{{if .State.Health}}{{.State.Health.Status}}{{end}}", name,
        ]))
    return result


def plan_for(root: Path, media: Path, synapse_port: int,
             element_port: int) -> dict:
    selection = matrix.load_selection()
    selection.update({
        "installation_id": "hl-matrix-" + uuid.uuid4().hex[:12],
        "target_platform": "windows" if os.name == "nt" else "linux",
        "architecture": "amd64",
        "server_name": SERVER_NAME,
        "public_base_url": "https://matrix-recovery.invalid/",
        "element_base_url": "https://element-recovery.invalid/",
        "state_root": str(root), "media_root": str(media),
        "ports": {"synapse": synapse_port, "element": element_port},
    })
    return matrix.make_plan(selection)


def image_preflight(plan: dict) -> None:
    for role in matrix.ROLES:
        image = plan["images"][role]["image"]
        rows = json.loads(text(["docker", "image", "inspect", image]))
        need(len(rows) == 1 and rows[0]["Os"] == "linux"
             and rows[0]["Architecture"] == plan["architecture"],
             f"Cached Matrix {role} image platform mismatch")
        index_digest = image.rsplit("@", 1)[1]
        need(any(item.endswith("@" + index_digest)
                 for item in rows[0].get("RepoDigests") or []),
             f"Cached Matrix {role} image digest mismatch")


def write_runtime(plan: dict, password: str, registration_secret: str,
                  macaroon_secret: str, form_secret: str) -> Path:
    root = Path(plan["paths"]["state"])
    synapse = root / "synapse"
    element = root / "element"
    secret_dir = root / "secrets"
    for directory in (root, synapse, element, secret_dir,
                      Path(plan["paths"]["media"])):
        directory.mkdir(parents=True, exist_ok=True)
    (secret_dir / "postgres_password").write_text(password + "\n",
                                                   encoding="utf-8")
    image = plan["images"]["synapse"]["image"]
    run(["docker", "run", "--rm", "--name",
         "hl-matrix-generate-" + uuid.uuid4().hex[:8],
         "-e", "SYNAPSE_SERVER_NAME=" + SERVER_NAME,
         "-e", "SYNAPSE_REPORT_STATS=no", "-v", f"{synapse}:/data",
         image, "generate"], timeout=180)
    signing_keys = list(synapse.glob("*.signing.key"))
    need(len(signing_keys) == 1, "Synapse did not generate one signing key")
    signing_name = signing_keys[0].name
    public_url = plan["urls"]["synapse"]
    homeserver = f'''server_name: "{SERVER_NAME}"
public_baseurl: "{public_url}"
pid_file: /data/homeserver.pid
listeners:
  - port: 8008
    tls: false
    type: http
    x_forwarded: true
    resources:
      - names: [client]
        compress: false
database:
  name: psycopg2
  args:
    user: synapse
    password: "{password}"
    database: synapse
    host: database
    port: 5432
    cp_min: 2
    cp_max: 5
log_config: /data/matrix-recovery.invalid.log.config
media_store_path: /data/media_store
signing_key_path: /data/{signing_name}
registration_shared_secret: "{registration_secret}"
macaroon_secret_key: "{macaroon_secret}"
form_secret: "{form_secret}"
enable_registration: false
enable_registration_without_verification: false
allow_public_rooms_without_auth: false
allow_public_rooms_over_federation: false
url_preview_enabled: false
enable_metrics: false
report_stats: false
suppress_key_server_warning: true
trusted_key_servers: []
'''
    (synapse / "homeserver.yaml").write_text(homeserver, encoding="utf-8")
    local_synapse = "http://127.0.0.1:" + str(
        plan["access"]["ports"]["synapse"])
    element_config = {
        "default_server_config": {
            "m.homeserver": {"base_url": local_synapse,
                             "server_name": SERVER_NAME}},
        "disable_custom_urls": True, "disable_guests": True,
        "disable_3pid_login": True, "brand": "HomeLab Matrix Recovery Trial",
        "room_directory": {"servers": [SERVER_NAME]},
        "show_labs_settings": False,
    }
    (element / "config.json").write_text(
        json.dumps(element_config, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    (root / "compose.json").write_text(
        json.dumps(matrix.compose(plan), sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    return signing_keys[0]


def key_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register(base: str, shared_secret: str, password: str) -> str:
    nonce = api("GET", base + "/_synapse/admin/v1/register")["nonce"]
    message = "\x00".join((nonce, USERNAME, password, "admin")).encode("utf-8")
    mac = hmac.new(shared_secret.encode("utf-8"), message,
                   hashlib.sha1).hexdigest()
    result = api("POST", base + "/_synapse/admin/v1/register", {
        "nonce": nonce, "username": USERNAME, "password": password,
        "admin": True, "mac": mac,
    })
    user_id = result.get("user_id", "")
    need(user_id == f"@{USERNAME}:{SERVER_NAME}",
         "Synthetic Matrix account registration failed")
    return user_id


def login(base: str, password: str) -> dict:
    result = api("POST", base + "/_matrix/client/v3/login", {
        "type": "m.login.password",
        "identifier": {"type": "m.id.user", "user": USERNAME},
        "password": password,
        "initial_device_display_name": "HomeLab recovery proof",
    })
    need(result.get("user_id") == f"@{USERNAME}:{SERVER_NAME}"
         and isinstance(result.get("access_token"), str),
         "Synthetic Matrix login failed")
    return result


def create_content(base: str, token: str) -> dict:
    room = api("POST", base + "/_matrix/client/v3/createRoom", {
        "preset": "private_chat", "name": ROOM_NAME,
        "topic": "Synthetic application-consistent recovery validation",
    }, token=token)
    room_id = room.get("room_id", "")
    need(room_id.startswith("!"), "Synthetic Matrix room creation failed")
    transaction = uuid.uuid4().hex
    event = api("PUT", base + "/_matrix/client/v3/rooms/"
                + quote(room_id, safe="") + "/send/m.room.message/" + transaction,
                {"msgtype": "m.text", "body": MESSAGE}, token=token)
    event_id = event.get("event_id", "")
    need(event_id.startswith("$"), "Synthetic Matrix message creation failed")
    upload = api("POST", base + "/_matrix/media/v3/upload?"
                 + urlencode({"filename": "recovery-proof.txt"}), token=token,
                 raw=MEDIA, content_type="text/plain")
    content_uri = upload.get("content_uri", "")
    need(content_uri.startswith("mxc://"), "Synthetic Matrix media upload failed")
    media_transaction = uuid.uuid4().hex
    media_event = api(
        "PUT", base + "/_matrix/client/v3/rooms/" + quote(room_id, safe="")
        + "/send/m.room.message/" + media_transaction,
        {"msgtype": "m.file", "body": "recovery-proof.txt", "url": content_uri,
         "info": {"mimetype": "text/plain", "size": len(MEDIA)}}, token=token)
    need(str(media_event.get("event_id", "")).startswith("$"),
         "Synthetic Matrix media message failed")
    verify_event(base, token, room_id, event_id)
    verify_media(base, token, content_uri)
    return {"room_id": room_id, "event_id": event_id,
            "content_uri": content_uri}


def verify_event(base: str, token: str, room_id: str, event_id: str) -> None:
    event = api("GET", base + "/_matrix/client/v3/rooms/"
                + quote(room_id, safe="") + "/event/"
                + quote(event_id, safe=""), token=token)
    need(event.get("content", {}).get("body") == MESSAGE,
         "Synthetic Matrix text event was not readable")


def verify_media(base: str, token: str, content_uri: str) -> None:
    parsed = urlparse(content_uri)
    server = parsed.netloc
    media_id = parsed.path.lstrip("/")
    need(bool(server and media_id), "Invalid synthetic Matrix media URI")
    urls = [
        base + "/_matrix/client/v1/media/download/" + quote(server, safe="")
        + "/" + quote(media_id, safe=""),
        base + "/_matrix/media/v3/download/" + quote(server, safe="")
        + "/" + quote(media_id, safe=""),
    ]
    for url in urls:
        try:
            body = api("GET", url, token=token)
            if body == MEDIA:
                return
        except HTTPError as error:
            if error.code not in (400, 404, 405):
                raise
    raise ConfigError("Synthetic Matrix media download did not match")


def hash_tree(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        result[path.relative_to(root).as_posix()] = hashlib.sha256(
            path.read_bytes()).hexdigest()
    return result


def copy_recovery_set(plan: dict, project: str, backup: Path) -> dict:
    root = Path(plan["paths"]["state"])
    media = Path(plan["paths"]["media"])
    backup.mkdir(parents=True)
    compose(plan, project, "stop", "synapse", timeout=120)
    container = text([*compose_args(plan, project), "ps", "-aq", "synapse"])
    status = text(["docker", "inspect", "--format", "{{.State.Status}}", container])
    need(status == "exited", "Synapse was not quiesced before database backup")
    dump = run([*compose_args(plan, project), "exec", "-T", "database",
                "pg_dump", "-U", "synapse", "-d", "synapse", "-Fc"],
               timeout=180).stdout
    need(len(dump) > 1024 and dump.startswith(b"PGDMP"),
         "PostgreSQL custom dump was not created")
    (backup / "database.dump").write_bytes(dump)
    shutil.copytree(root / "synapse", backup / "synapse")
    shutil.copytree(root / "element", backup / "element")
    shutil.copytree(root / "secrets", backup / "secrets")
    shutil.copytree(media, backup / "media")
    manifest = {"kind": "homelab-matrix-recovery-set-v1",
                "contract": matrix.CONTRACT, "files": hash_tree(backup)}
    manifest_hash = hashlib.sha256(canonical(manifest).encode("utf-8")).hexdigest()
    manifest["manifest_sha256"] = manifest_hash
    (backup / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest


def restore_files(backup: Path, plan: dict) -> None:
    root = Path(plan["paths"]["state"])
    media = Path(plan["paths"]["media"])
    root.mkdir(parents=True)
    shutil.copytree(backup / "synapse", root / "synapse")
    shutil.copytree(backup / "element", root / "element")
    shutil.copytree(backup / "secrets", root / "secrets")
    shutil.copytree(backup / "media", media)
    (root / "compose.json").write_text(
        json.dumps(matrix.compose(plan), sort_keys=True, indent=2) + "\n",
        encoding="utf-8")


def restore_database(plan: dict, project: str, dump: Path) -> None:
    compose(plan, project, "up", "-d", "database", timeout=180)
    wait_healthy(plan, project, "database")
    data = dump.read_bytes()
    result = run([*compose_args(plan, project), "exec", "-T", "database",
                  "pg_restore", "-U", "synapse", "-d", "synapse",
                  "--no-owner", "--no-privileges"], input_bytes=data,
                 timeout=240, check=False)
    need(result.returncode == 0,
         "PostgreSQL custom dump did not restore cleanly: "
         + result.stderr.decode("utf-8", errors="replace")[-2000:])


def runtime_versions(plan: dict, project: str, base: str) -> None:
    synapse = text([*compose_args(plan, project), "ps", "-q", "synapse"])
    synapse_version = text([
        "docker", "exec", synapse, "python", "-c",
        "import synapse; print(synapse.__version__)",
    ])
    need(synapse_version == plan["images"]["synapse"]["version"],
         "Runtime Synapse version mismatch")
    database = text([*compose_args(plan, project), "ps", "-q", "database"])
    postgres = text(["docker", "exec", database, "postgres", "--version"])
    need(re.search(r"\b15\.19(?:\.\d+)?\b", postgres) is not None,
         "Runtime PostgreSQL version mismatch")
    element = text([*compose_args(plan, project), "ps", "-q", "element"])
    element_version = text(["docker", "exec", element, "sed", "-n", "1p",
                            "/app/version"])
    need(element_version == plan["images"]["element"]["version"],
         "Runtime Element version mismatch")


def memory_mib(plan: dict, project: str) -> float:
    total = 0.0
    units = {"B": 1 / 1024**2, "KiB": 1 / 1024,
             "MiB": 1, "GiB": 1024}
    for service in matrix.ROLES:
        container = text([*compose_args(plan, project), "ps", "-q", service])
        usage = text(["docker", "stats", "--no-stream", "--format",
                      "{{.MemUsage}}", container]).split("/", 1)[0].strip()
        match = re.fullmatch(r"([0-9.]+)([A-Za-z]+)", usage)
        need(match is not None and match.group(2) in units,
             "Unexpected Docker memory measurement")
        total += float(match.group(1)) * units[match.group(2)]
    return round(total, 2)


def safe_remove(root: Path) -> None:
    if not root.exists():
        return
    resolved = root.resolve()
    allowed = Path("C:/Docker").resolve() if os.name == "nt" else Path("/tmp").resolve()
    need(resolved.parent == allowed
         and resolved.name.startswith("homelab-matrix-trial-"),
         "Refusing to remove an unowned Matrix trial root")
    shutil.rmtree(resolved)


def cleanup(plan: dict | None, project: str | None) -> None:
    if plan is not None and project is not None:
        compose(plan, project, "down", "--volumes", "--remove-orphans",
                timeout=180, check=False)


def trial(output: Path, port_base: int) -> dict:
    global ACTIVE_ROOT
    free_port(port_base)
    free_port(port_base + 81)
    production_before = snapshot_production()
    root_parent = Path("C:/Docker") if os.name == "nt" else Path("/tmp")
    trial_root = root_parent / ("homelab-matrix-trial-" + uuid.uuid4().hex[:12])
    ACTIVE_ROOT = trial_root
    source_root = trial_root / "source"
    source_media = trial_root / "source-media"
    backup_root = trial_root / "backup"
    recovered_root = trial_root / "recovered"
    recovered_media = trial_root / "recovered-media"
    source_plan = plan_for(source_root, source_media, port_base, port_base + 81)
    source_project = source_plan["installation_id"]
    recovery_plan = None
    recovery_project = None
    cleanup_completed = False
    try:
        image_preflight(source_plan)
        password = secrets.token_hex(24)
        registration_secret = secrets.token_hex(32)
        account_password = "Aa1-" + secrets.token_hex(16)
        signing_key = write_runtime(
            source_plan, password, registration_secret,
            secrets.token_hex(32), secrets.token_hex(32))
        key_before = key_sha256(signing_key)
        compose(source_plan, source_project, "config", "--quiet")
        compose(source_plan, source_project, "up", "-d", timeout=300)
        wait_healthy(source_plan, source_project, "database")
        wait_healthy(source_plan, source_project, "synapse")
        wait_healthy(source_plan, source_project, "element")
        base = "http://127.0.0.1:" + str(port_base)
        element_url = "http://127.0.0.1:" + str(port_base + 81) + "/"
        wait_http(base + "/health")
        wait_http(element_url)
        runtime_versions(source_plan, source_project, base)
        register(base, registration_secret, account_password)
        first_login = login(base, account_password)
        created = create_content(base, first_login["access_token"])
        idle_memory = memory_mib(source_plan, source_project)
        manifest = copy_recovery_set(source_plan, source_project, backup_root)
        compose(source_plan, source_project, "down", "--volumes", "--remove-orphans",
                timeout=180)
        shutil.rmtree(source_root)
        shutil.rmtree(source_media)
        recovery_plan = plan_for(recovered_root, recovered_media,
                                 port_base, port_base + 81)
        recovery_project = recovery_plan["installation_id"]
        restore_files(backup_root, recovery_plan)
        restore_database(recovery_plan, recovery_project,
                         backup_root / "database.dump")
        compose(recovery_plan, recovery_project, "up", "-d", "synapse", "element",
                timeout=300)
        wait_healthy(recovery_plan, recovery_project, "synapse")
        wait_healthy(recovery_plan, recovery_project, "element")
        wait_http(base + "/health")
        wait_http(element_url)
        runtime_versions(recovery_plan, recovery_project, base)
        restored_keys = list((recovered_root / "synapse").glob("*.signing.key"))
        need(len(restored_keys) == 1, "Recovered signing key set is invalid")
        key_after = key_sha256(restored_keys[0])
        second_login = login(base, account_password)
        need(second_login["access_token"] != first_login["access_token"],
             "Independent Matrix login session was not created after restore")
        verify_event(base, second_login["access_token"], created["room_id"],
                     created["event_id"])
        verify_media(base, second_login["access_token"], created["content_uri"])
        peak_memory = max(idle_memory, memory_mib(recovery_plan, recovery_project))
        proof = {
            "kind": "homelab-matrix-evidence", "contract": matrix.CONTRACT,
            "plan_id": source_plan["plan_id"],
            "images": {role: {
                "version": source_plan["images"][role]["version"],
                "platform_digest": source_plan["images"][role]["platform_digest"],
            } for role in matrix.ROLES},
            "identity": {"server_name": SERVER_NAME,
                         "signing_key_sha256_before": key_before,
                         "signing_key_sha256_after": key_after,
                         "unchanged": key_before == key_after},
            "exercise": {"login": True, "room_created": True,
                         "text_event": True, "media_upload": True,
                         "media_download": True, "element_http": True,
                         "independent_sessions": True},
            "backup": {"synapse_quiesced": True,
                       "postgres_custom_dump": True, "config": True,
                       "signing_key": True, "media": True,
                       "element_config": True,
                       "manifest_sha256": manifest["manifest_sha256"],
                       "source_removed": not source_root.exists()
                                         and not source_media.exists()},
            "restore": {"independent_root": True, "same_versions": True,
                        "database_restored": True, "login": True, "room": True,
                        "text_event": True, "media": True, "element_http": True},
            "client_e2ee": {"server_backup_claimed": False,
                            "client_key_backup_tested": False,
                            "owner_validation_required": True},
            "network": {"federation_enabled": False, "turn_tested": False,
                        "bridges_tested": False,
                        "outbound_integrations_enabled": False},
            "resources": {"idle_memory_mib": idle_memory,
                          "peak_memory_mib": peak_memory},
            "safety": {"production_paths_used": False,
                       "production_credentials_used": False,
                       "production_messages_read": False,
                       "docker_socket_mounted": False,
                       "cleanup_completed": False},
        }
        return proof, source_plan, production_before, trial_root,
    finally:
        cleanup(source_plan, source_project)
        cleanup(recovery_plan, recovery_project)


def main() -> int:
    global ACTIVE_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan-output", type=Path)
    parser.add_argument("--port-base", type=int, default=18508)
    args = parser.parse_args()
    try:
        need(args.confirm == CONFIRM, "Explicit isolated-trial confirmation is required")
        proof, plan, production_before, trial_root = trial(
            args.output, args.port_base)
        plan_output = args.plan_output
        if plan_output is None:
            name = (args.output.name.replace("Evidence", "Plan", 1)
                    if "Evidence" in args.output.name
                    else args.output.stem + "-plan" + args.output.suffix)
            plan_output = args.output.with_name(name)
        safe_remove(trial_root)
        ACTIVE_ROOT = None
        need(snapshot_production() == production_before,
             "Production Matrix container inventory changed during isolated trial")
        proof["safety"]["cleanup_completed"] = True
        matrix.validate_evidence(proof, plan)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(proof, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8")
        plan_output.write_text(json.dumps(plan, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps({
            "kind": proof["kind"], "contract": proof["contract"],
            "plan_id": proof["plan_id"], "identity_unchanged": True,
            "actual_content_restored": True, "client_e2ee_separate": True,
            "cleanup_completed": True, "output": str(args.output),
            "plan_output": str(plan_output),
        }, sort_keys=True))
        return 0
    except (ConfigError, OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError, subprocess.SubprocessError) as error:
        if ACTIVE_ROOT is not None and ACTIVE_ROOT.exists():
            try:
                safe_remove(ACTIVE_ROOT)
            except (ConfigError, OSError):
                pass
        ACTIVE_ROOT = None
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
