"""Run a destructive-only-to-owned-synthetic code-server recovery trial."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homelab import code_server
from homelab.config import need
from homelab.io import write_private


CONFIRM = "RUN-ISOLATED-CODE-SERVER-TRIAL"
MARKER = ".homelab-code-server-trial"


def run(arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(arguments, check=check, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def compose(path: Path, project: str, *arguments: str,
            check: bool = True) -> subprocess.CompletedProcess:
    return run(["docker", "compose", "-f", str(path), "-p", project, *arguments],
               check=check)


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def wait_healthy(compose_file: Path, project: str, timeout: int = 180) -> str:
    deadline = time.monotonic() + timeout
    last = "missing"
    while time.monotonic() < deadline:
        container = compose(compose_file, project, "ps", "-q", "code-server").stdout.strip()
        if container:
            state = run(["docker", "inspect", "--format",
                         "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}",
                         container]).stdout.strip()
            last = state
            if state == "running|healthy":
                return container
            if state.startswith("exited|") or state.startswith("dead|"):
                break
        time.sleep(2)
    raise RuntimeError(f"code-server did not become healthy: {last}")


def exec_in(container: str, *arguments: str) -> str:
    return run(["docker", "exec", container, *arguments]).stdout.strip()


def http_health(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=10) as response:
            return response.status == 200
    except OSError:
        return False


def memory_mib(value: str) -> float:
    match = re.match(r"([0-9.]+)([KMG]iB)", value.strip())
    if not match:
        raise RuntimeError(f"Unrecognized Docker memory value: {value}")
    amount = float(match.group(1))
    return amount * {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024}[match.group(2)]


def sample_resources(container: str) -> tuple[float, float]:
    value = json.loads(run([
        "docker", "stats", container, "--no-stream", "--format", "{{json .}}"
    ]).stdout)
    return memory_mib(value["MemUsage"].split("/")[0]), float(value["CPUPerc"].rstrip("%"))


def version_line(text: str) -> str:
    match = re.search(r"(?m)^([0-9]+(?:\.[0-9]+){2})\b", text)
    if not match:
        raise RuntimeError("Semantic version line not found")
    return match.group(1)


def image_labels(image: str) -> dict:
    raw = run(["docker", "image", "inspect", image, "--format",
               "{{json .Config.Labels}}"]).stdout
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


def helper(root: Path, image: str, script: str) -> str:
    return run([
        "docker", "run", "--rm", "--user", "0:0", "--entrypoint", "/bin/sh",
        "--mount", f"type=bind,source={root},target=/trial",
        image, "-ec", script,
    ]).stdout.strip()


def expected_extensions(plan: dict) -> list[str]:
    return [f"{item['id']}@{item['version']}" for item in plan["build"]["extensions"]]


def verify_runtime(container: str, plan: dict) -> tuple[str, str, list[str], str]:
    code_version = version_line(exec_in(container, "code-server", "--version"))
    node_version = exec_in(container, "node", "--version").removeprefix("v")
    extensions = sorted(line for line in exec_in(
        container, "code-server", "--user-data-dir",
        "/home/coder/.local/share/code-server", "--extensions-dir",
        "/home/coder/.local/share/code-server/extensions",
        "--list-extensions", "--show-versions").splitlines() if "@" in line)
    settings_hash = exec_in(
        container, "sha256sum",
        "/home/coder/.local/share/code-server/User/settings.json").split()[0]
    need(code_version == plan["build"]["code_server_version"],
         "Runtime code-server version mismatch")
    need(node_version == plan["build"]["node_version"],
         "Runtime Node version mismatch")
    need(set(expected_extensions(plan)) <= set(extensions),
         "Runtime extension seed is incomplete")
    return code_version, node_version, extensions, settings_hash


def replace_sources(spec: dict, source_state: Path, source_workspace: Path,
                    target_state: Path, target_workspace: Path) -> dict:
    result = copy.deepcopy(spec)
    for mount in result["services"]["code-server"]["volumes"]:
        source = Path(mount["source"])
        if source == source_workspace:
            mount["source"] = str(target_workspace)
        elif source.is_relative_to(source_state):
            mount["source"] = str(target_state / source.relative_to(source_state))
    result["name"] = "hl-code-recovered"
    return result


def safe_remove(root: Path, plan_id: str, image: str) -> None:
    marker = root / MARKER
    need(root.name.startswith("homelab-code-server-trial-"),
         "Trial cleanup root name is not owned")
    need(marker.is_file() and marker.read_text(encoding="utf-8").strip() == plan_id,
         "Trial cleanup marker is missing or changed")
    helper(root, image,
           "rm -rf /trial/source-state /trial/source-workspace "
           "/trial/restored-state /trial/restored-workspace "
           "/trial/stopped-backup /trial/source-compose.json "
           "/trial/restored-compose.json /trial/.homelab-code-server-trial")
    root.rmdir()


def trial(root: Path, port: int, plan_output: Path, evidence_output: Path) -> dict:
    root = root.resolve()
    need(root.parent.is_dir() and not root.exists(),
         "Trial root must be a new child of an existing directory")
    need(not root.is_relative_to(ROOT), "Trial root must stay outside Git")
    need(root.name.startswith("homelab-code-server-trial-"),
         "Trial root name must start with homelab-code-server-trial-")

    selection = code_server.load_selection()
    selection.update({
        "installation_id": "hl-code-trial",
        "target_platform": "windows" if os.name == "nt" else "linux",
        "architecture": "amd64",
        "state_root": str(root / "source-state"),
        "workspace_root": str(root / "source-workspace"),
        "port": port,
    })
    plan = code_server.make_plan(selection)
    spec = code_server.compose(plan)
    image = plan["build"]["image"]
    labels = image_labels(image)
    need(labels.get("org.homelab.code-server.version") ==
         plan["build"]["code_server_version"], "Candidate image version label mismatch")
    need(labels.get("org.homelab.code-server.platform-digest") ==
         plan["build"]["platform_digest"], "Candidate platform digest label mismatch")
    need(labels.get("org.homelab.node.archive-sha256") ==
         plan["build"]["node_archive"]["sha256"], "Candidate Node checksum label mismatch")

    state = Path(plan["paths"]["state"])
    workspace = Path(plan["paths"]["workspace"])
    restored_state = root / "restored-state"
    restored_workspace = root / "restored-workspace"
    backup = root / "stopped-backup"
    compose_file = root / "source-compose.json"
    restored_compose = root / "restored-compose.json"
    source_project = "hl-code-source"
    restored_project = "hl-code-recovered"
    source_container = None
    restored_container = None
    succeeded = False
    root.mkdir()
    (root / MARKER).write_text(plan["plan_id"] + "\n", encoding="utf-8")
    try:
        for directory in (state / "config" / "code-server", state / "local",
                          state / "secure", workspace):
            directory.mkdir(parents=True, exist_ok=True)
        password = secrets.token_urlsafe(32)
        (state / "config" / "code-server" / "config.yaml").write_text(
            "bind-addr: 0.0.0.0:8080\nauth: password\n"
            f"password: {password}\ncert: false\n", encoding="utf-8")
        source = workspace / "main.c"
        source.write_text(
            "#include <stdio.h>\n"
            "static unsigned long long fib(unsigned n){return n<2?n:fib(n-1)+fib(n-2);}\n"
            "int main(void){printf(\"%llu\\n\", fib(32)); return 0;}\n",
            encoding="utf-8")
        source_hash = sha256(source)
        save(compose_file, spec)
        compose(compose_file, source_project, "config", "--quiet")
        compose(compose_file, source_project, "up", "-d", "--no-build")
        source_container = wait_healthy(compose_file, source_project)
        code_version, node_version, extensions, settings_hash = verify_runtime(
            source_container, plan)
        idle_memory, _ = sample_resources(source_container)
        compile_process = subprocess.Popen([
            "docker", "exec", source_container, "sh", "-lc",
            "for n in 1 2 3 4 5 6 7 8; do "
            "gcc -O2 /home/coder/project/main.c -o /home/coder/project/hello-$n & "
            "done; wait; cp /home/coder/project/hello-1 /home/coder/project/hello"
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        peak_memory = idle_memory
        peak_cpu = 0.0
        while compile_process.poll() is None:
            memory, cpu = sample_resources(source_container)
            peak_memory = max(peak_memory, memory)
            peak_cpu = max(peak_cpu, cpu)
        output = compile_process.communicate()[0]
        need(compile_process.returncode == 0, f"Synthetic compilation failed: {output[-500:]}")
        artifact = workspace / "hello"
        need(artifact.is_file(), "Synthetic compiled artifact missing")
        artifact_hash = sha256(artifact)
        need(http_health(port), "Host code-server health request failed")

        original_container = source_container
        compose(compose_file, source_project, "up", "-d", "--no-build",
                "--force-recreate")
        source_container = wait_healthy(compose_file, source_project)
        need(source_container != original_container, "Container was not recreated")
        _, _, extensions_after, settings_hash_after = verify_runtime(source_container, plan)
        need(sha256(source) == source_hash and sha256(artifact) == artifact_hash,
             "Workspace content changed across recreation")
        need(settings_hash_after == settings_hash,
             "Editor settings changed across recreation")
        need(set(expected_extensions(plan)) <= set(extensions_after),
             "Extensions changed across recreation")
        need(http_health(port), "Reconnect health failed after recreation")

        compose(compose_file, source_project, "stop")
        backup.mkdir(parents=True, exist_ok=True)
        helper(root, image,
               "tar -C /trial/source-state -cf /trial/stopped-backup/state.tar .; "
               "tar -C /trial/source-workspace -cf /trial/stopped-backup/workspace.tar .")
        compose(compose_file, source_project, "down")
        source_container = None
        helper(root, image,
               "rm -rf /trial/source-state /trial/source-workspace; "
               "mkdir -p /trial/restored-state /trial/restored-workspace; "
               "tar -C /trial/restored-state -xf /trial/stopped-backup/state.tar; "
               "tar -C /trial/restored-workspace -xf /trial/stopped-backup/workspace.tar")
        recovered = replace_sources(spec, state, workspace,
                                    restored_state, restored_workspace)
        save(restored_compose, recovered)
        compose(restored_compose, restored_project, "config", "--quiet")
        compose(restored_compose, restored_project, "up", "-d", "--no-build")
        restored_container = wait_healthy(restored_compose, restored_project)
        _, _, restored_extensions, restored_settings_hash = verify_runtime(
            restored_container, plan)
        restored_source_hash = helper(
            root, image,
            "sha256sum /trial/restored-workspace/main.c | awk '{print $1}'")
        need(restored_source_hash == source_hash,
             "Restored synthetic source hash mismatch")
        need(restored_settings_hash == settings_hash,
             "Restored settings hash mismatch")
        need(set(expected_extensions(plan)) <= set(restored_extensions),
             "Restored extension set is incomplete")
        need(http_health(port), "Recovered code-server health request failed")

        value = {
            "kind": "homelab-code-server-evidence",
            "contract": code_server.CONTRACT,
            "plan_id": plan["plan_id"],
            "build": {
                "architecture": plan["architecture"],
                "code_server_version": code_version,
                "node_version": node_version,
                "node_archive_sha256": labels["org.homelab.node.archive-sha256"],
                "platform_digest": labels["org.homelab.code-server.platform-digest"],
                "extensions": expected_extensions(plan),
            },
            "exercise": {
                "synthetic_project": True,
                "server_side_compile": True,
                "compile_exit_code": 0,
                "source_sha256": source_hash,
                "artifact_sha256": artifact_hash,
                "http_health": True,
                "reconnect_after_restart": True,
            },
            "persistence": {
                "autosave": True,
                "settings": True,
                "extensions": True,
                "workspace": True,
                "terminal_policy": True,
                "container_recreated": True,
            },
            "recovery": {
                "services_stopped": True,
                "included": ["config", "local", "secure", "workspace"],
                "independent_root": True,
                "restored": True,
                "source_hash_match": True,
                "settings_hash_match": True,
            },
            "resources": {
                "idle_memory_mib": round(idle_memory, 3),
                "compile_peak_memory_mib": round(peak_memory, 3),
                "compile_peak_cpu_percent": round(peak_cpu, 3),
            },
            "safety": {
                "production_paths_used": False,
                "production_credentials_used": False,
                "private_workspace_read": False,
                "docker_socket_mounted": False,
                "runtime_extension_network": False,
                "cleanup_completed": True,
            },
        }
        code_server.validate_evidence(value, plan)
        succeeded = True
    finally:
        if source_container is not None:
            compose(compose_file, source_project, "down", check=False)
        if restored_container is not None:
            compose(restored_compose, restored_project, "down", check=False)
        if succeeded:
            safe_remove(root, plan["plan_id"], image)

    write_private(plan_output, plan)
    write_private(evidence_output, value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18444)
    parser.add_argument("--plan-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    try:
        need(args.confirm == CONFIRM, f"Confirmation must be exactly {CONFIRM}")
        result = trial(args.root, args.port, args.plan_output, args.output)
        print(json.dumps({
            "status": "passed",
            "plan_id": result["plan_id"],
            "code_server": result["build"]["code_server_version"],
            "node": result["build"]["node_version"],
            "extensions": len(result["build"]["extensions"]),
            "idle_memory_mib": result["resources"]["idle_memory_mib"],
            "compile_peak_memory_mib": result["resources"]["compile_peak_memory_mib"],
            "compile_peak_cpu_percent": result["resources"]["compile_peak_cpu_percent"],
            "cleanup_completed": result["safety"]["cleanup_completed"],
        }, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError,
            json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
