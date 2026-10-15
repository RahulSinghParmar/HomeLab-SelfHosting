"""Validate the bounded Phase 4 release surface without contacting Docker."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = "0.5.0-rc.1"
DIGEST = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")

MODULES = {
    "glance": {
        "commands": ("glance", "glance-layout", "glance-collector"),
        "code": ("homelab/glance.py", "homelab/glance_layouts.py", "homelab/glance_collectors.py"),
        "docs": ("docs/glance-module.md", "docs/glance-operations-layout.md"),
        "evidence": ("docs/validation/glance-operations-layout.md",),
        "manifests": (("modules/glance/image.json", ("image",)),
                      ("modules/glance/collector/image.json", ("image",))),
        "tests": ("tests/test_glance.py", "tests/test_glance_layouts.py", "tests/test_glance_collectors.py"),
    },
    "uptime-kuma": {
        "commands": ("kuma",),
        "code": ("homelab/kuma.py", "homelab/kuma_config.py"),
        "docs": ("docs/kuma-module.md", "docs/kuma-configuration.md"),
        "evidence": ("docs/validation/kuma-configuration.md",),
        "manifests": (("modules/uptime-kuma/image.json", ("image",)),),
        "tests": ("tests/test_kuma.py", "tests/test_kuma_config.py"),
    },
    "beszel": {
        "commands": ("beszel", "beszel-windows"),
        "code": ("homelab/beszel.py", "homelab/beszel_windows.py"),
        "docs": ("docs/beszel-module.md", "docs/beszel-windows-host.md"),
        "evidence": ("docs/validation/beszel-trial.md", "docs/validation/beszel-windows-host.md"),
        "manifests": (("modules/beszel/image.json", ("hub", "agent")),),
        "tests": ("tests/test_beszel.py", "tests/test_beszel_windows.py"),
    },
    "stirling-pdf": {
        "commands": ("stirling",),
        "code": ("homelab/stirling.py",),
        "docs": ("docs/stirling-pdf-module.md",),
        "evidence": ("docs/validation/stirling-pdf.md",),
        "manifests": (("modules/stirling-pdf/image.json", ("image",)),),
        "tests": ("tests/test_stirling.py",),
    },
    "portainer": {
        "commands": ("portainer",),
        "code": ("homelab/portainer.py",),
        "docs": ("docs/portainer-module.md",),
        "evidence": ("docs/validation/portainer.md",),
        "manifests": (("modules/portainer/images.json", ("portainer_image", "engine_image")),),
        "tests": ("tests/test_portainer.py",),
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, f"{path}: duplicate JSON key {key}")
            value[key] = item
        return value

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def validate_digest(value: object, where: str) -> None:
    require(isinstance(value, str) and bool(DIGEST.fullmatch(value)),
            f"{where}: exact sha256 image digest required")


def validate_phase4(root: Path = ROOT) -> str:
    package = (root / "homelab/__init__.py").read_text(encoding="utf-8")
    catalog = load_json(root / "catalog/services.json")
    cli = (root / "homelab/cli.py").read_text(encoding="utf-8")
    require(f'__version__ = "{RELEASE}"' in package, "package release version mismatch")
    require(catalog.get("release") == RELEASE, "catalog release version mismatch")

    for name, contract in MODULES.items():
        for group in ("code", "docs", "evidence", "tests"):
            for relative in contract[group]:
                require((root / relative).is_file(), f"{name}: missing {group} file {relative}")
        for command in contract["commands"]:
            require(f'add_parser("{command}"' in cli or f"add_parser('{command}'" in cli,
                    f"{name}: missing CLI command {command}")
        for relative, keys in contract["manifests"]:
            path = root / relative
            require(path.is_file(), f"{name}: missing image manifest {relative}")
            manifest = load_json(path)
            for key in keys:
                require(key in manifest, f"{name}: image manifest missing {key}")
                validate_digest(manifest[key], f"{name} {key}")

    release = root / "docs/releases/v0.5.0-rc.1.md"
    integrated = root / "docs/validation/phase4-integrated.md"
    require(release.is_file(), "missing Phase 4 release review")
    require(integrated.is_file(), "missing Phase 4 integrated validation record")
    return (f"PASS: Phase 4 {RELEASE} contract validates {len(MODULES)} isolated modules; "
            "runtime claims remain bounded by the published support matrix")


def main() -> int:
    try:
        print(validate_phase4())
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
