"""Validate the first Phase 7 development and host-integration contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homelab import code_server


RELEASE = "0.8.0-alpha.1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_phase7(root: Path = ROOT) -> str:
    package = (root / "homelab/__init__.py").read_text(encoding="utf-8")
    catalog = load(root / "catalog/services.json")
    require(f'__version__ = "{RELEASE}"' in package,
            "package release version mismatch")
    require(catalog.get("release") == RELEASE,
            "catalog release version mismatch")

    build = code_server.load_build(root / "modules/code-server/build.json")
    require(build["code_server"] == {
        "version": "4.145.0",
        "image": ("ghcr.io/coder/code-server:4.145.0@sha256:"
                  "992796b850b8b7ec6f7393b8dd2295840a65cf5071981990ff41ef52dd566c43"),
        "platform_digests": {
            "amd64": "sha256:b1da9efc3f8ca7ec9d772c4a81024b2dfa8a418644ea8db26924c649cc9be96c",
            "arm64": "sha256:781d3c0ffc304c29228313a99a515cb63b0609e8e41cd875480d306639a13016",
        },
    }, "Reviewed code-server release identity changed")
    require(build["node"]["version"] == "24.19.0"
            and set(build["node"]["archives"]) == {"amd64", "arm64"},
            "Reviewed Node multiarchitecture release changed")
    require(len(build["extensions"]) == 18
            and all(item.get("version") for item in build["extensions"]),
            "Pinned extension set changed")

    selection = code_server.load_selection(
        root / "modules/code-server/selection.example.json")
    plan = code_server.make_plan(selection, build)
    spec = code_server.compose(plan)
    service = spec["services"]["code-server"]
    require(plan["architecture"] == "amd64"
            and plan["production_state_adopted"] is False
            and plan["deployment_performed"] is False,
            "Code-server example crossed the review-only boundary")
    require(service["ports"] == [{
        "target": 8080, "published": "18443",
        "host_ip": "127.0.0.1", "protocol": "tcp"}]
        and service["pull_policy"] == "never"
        and service["cap_drop"] == ["ALL"]
        and service["security_opt"] == ["no-new-privileges:true"]
        and service["mem_limit"] == "6144m"
        and service["mem_reservation"] == "512m"
        and service["pids_limit"] == 2048,
        "Code-server runtime isolation or limits changed")
    text = json.dumps(spec).casefold()
    require("docker.sock" not in text and "privileged" not in text
            and "password" not in text,
            "Code-server Compose leaked control or authentication material")
    require({item["target"] for item in service["volumes"]}
            == set(code_server.MOUNTS.values()),
            "Code-server persistence scopes changed")

    dockerfile = (root / "modules/code-server/image/Dockerfile").read_text(
        encoding="utf-8")
    for marker in ("TARGETARCH", "amd64) node_arch=x64",
                   "arm64) node_arch=arm64", "sha256sum --check --strict",
                   "CODE_SERVER_EXPECTED_VERSION", "install-code-extensions"):
        require(marker in dockerfile or marker in
                (root / "modules/code-server/image/start-code-server.sh").read_text(
                    encoding="utf-8"),
                f"Architecture/version build marker missing: {marker}")
    start = (root / "modules/code-server/image/start-code-server.sh").read_text(
        encoding="utf-8")
    require("test ! -e \"$settings\"" in start
            and "cp /opt/homelab/settings.json" in start,
            "Settings seed must remain copy-once")
    trial = (root / "tools/code_server_trial.py").read_text(encoding="utf-8")
    for marker in ("RUN-ISOLATED-CODE-SERVER-TRIAL", "server_side_compile",
                   "--force-recreate", "services_stopped", "independent_root",
                   "production_credentials_used", "cleanup_completed"):
        require(marker in trial, f"Code-server trial gate missing {marker}")

    cli = (root / "homelab/cli.py").read_text(encoding="utf-8")
    require("'code-server'" in cli and "from . import code_server as module" in cli
            and "render-compose" in cli and "validate-evidence" in cli,
            "Code-server CLI is not wired")
    workflow = (root / ".github/workflows/validate.yml").read_text(
        encoding="utf-8")
    require("python tools/validate_phase7.py" in workflow,
            "Phase 7 validator is absent from CI")
    for relative in (
        "docs/code-server-module.md",
        "docs/validation/code-server.md",
        "docs/releases/v0.8.0-alpha.1.md",
        "modules/code-server/build.json",
        "modules/code-server/selection.example.json",
        "modules/code-server/image/Dockerfile",
        "modules/code-server/image/extensions.txt",
        "modules/code-server/image/settings.json",
        "tests/test_code_server.py",
        "tools/code_server_trial.py",
    ):
        require((root / relative).is_file(), f"Missing Phase 7 artifact: {relative}")
    return ("PASS: Phase 7 0.8.0-alpha.1 provides a pinned multiarchitecture "
            "code-server build, copy-once developer persistence, restricted "
            "Compose rendering and isolated compile/recreation/recovery proof")


def main() -> int:
    try:
        print(validate_phase7())
        return 0
    except (OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
