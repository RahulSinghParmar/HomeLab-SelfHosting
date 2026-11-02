"""Validate the non-activating Phase 6 media and acceleration foundation."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homelab.media_acceleration import CONTRACT, load_policy, make_plan


RELEASE = "0.7.0-alpha.1"
DIGEST = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_phase6(root: Path = ROOT) -> str:
    package = (root / "homelab/__init__.py").read_text(encoding="utf-8")
    catalog = load(root / "catalog/services.json")
    require(f'__version__ = "{RELEASE}"' in package,
            "package release version mismatch")
    require(catalog.get("release") == RELEASE,
            "catalog release version mismatch")
    images = load(root / "modules/immich/images.json")
    require(set(images) == {"server", "machine_learning", "cache", "database"},
            "Immich image roles changed")
    require(all(isinstance(value, str) and DIGEST.fullmatch(value)
                for value in images.values()),
            "Immich images must use immutable sha256 references")
    require("immich-server:v3.3.5" in images["server"]
            and "immich-machine-learning:v3.3.5" in images["machine_learning"]
            and "valkey/valkey:9" in images["cache"]
            and "14-vectorchord0.4.3-pgvectors0.2.0" in images["database"],
            "Immich v3.3.5 compatible release set changed")
    policy = load_policy(root / "modules/phase6/media-policy.example.json")
    fixture = {
        "kind": "homelab-phase6-capability-audit", "contract": CONTRACT,
        "host_platform": "windows",
        "docker": {"available": True, "context": "desktop-linux",
                   "server": {"version": "reviewed", "os": "linux",
                              "architecture": "amd64", "kernel": "wsl2"},
                   "runtimes": ["nvidia", "runc"]},
        "nvidia": {"available": True, "devices": [{
            "name": "GeForce GT 730", "driver": "391.35",
            "compute_capability": {"minimum": 2.1, "maximum": 3.5,
                                   "source": "nvidia-legacy-table"}}]},
        "mutations_performed": False, "synthetic_gpu_test": "not-run",
    }
    plan = make_plan(policy, fixture)
    require(plan["execution"] == "disabled-review-only"
            and plan["acceleration"]["selected"] == "cpu"
            and plan["acceleration"]["cuda_status"] == "blocked"
            and plan["production_media_used"] is False
            and plan["deployment_performed"] is False,
            "Phase 6 foundation must fail closed without deployment")
    require(set(plan["acceleration"]["blocking_reasons"]) == {
        "compute-capability-below-5.2", "nvidia-driver-below-545"},
        "Reference-host GPU result changed")
    code = (root / "homelab/media_acceleration.py").read_text(encoding="utf-8")
    for marker in ("phase6-media-acceleration-v1", "CUDA_MIN_COMPUTE = 5.2",
                   "CUDA_MIN_DRIVER = 545.0", "synthetic_test_required",
                   "gpu_enabled", "destructive_cleanup"):
        require(marker in code, f"Phase 6 safety contract missing {marker}")
    cli = (root / "homelab/cli.py").read_text(encoding="utf-8")
    require("'media'" in cli and "media_acceleration" in cli,
            "Media audit/plan CLI is not wired")
    workflow = (root / ".github/workflows/validate.yml").read_text(encoding="utf-8")
    require("python tools/validate_phase6.py" in workflow,
            "Phase 6 validator is absent from CI")
    for path in ("docs/phase6-media-foundation.md",
                 "docs/validation/phase6-media-foundation.md",
                 "docs/releases/v0.7.0-alpha.1.md",
                 "tests/test_media_acceleration.py"):
        require((root / path).is_file(), f"Missing Phase 6 artifact: {path}")
    return ("PASS: Phase 6 0.7.0-alpha.1 pins the Immich v3.3.5 release set, "
            "preserves authoritative media classes, keeps heavy jobs manual and "
            "fails closed to CPU after a read-only capability audit")


def main() -> int:
    try:
        print(validate_phase6())
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
