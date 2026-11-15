"""Validate the final Phase 6 media recovery and acceleration contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homelab import media_management
from tools.validate_phase6 import load, require, validate_phase6


RELEASE = "0.7.0"
CONTRACT = "phase6-media-closure-v1"


def validate_closure(root: Path = ROOT) -> str:
    base = validate_phase6(root)
    require(RELEASE in base, "Phase 6 release validator is not final")
    value = load(root / "modules/phase6/closure.json")
    require(set(value) == {
        "contract", "release", "scope", "production_adoption",
        "production_media_used", "kit_components", "modules",
        "acceleration", "remaining_boundaries",
    }, "Phase 6 closure fields changed")
    require(value["contract"] == CONTRACT and value["release"] == RELEASE,
            "Phase 6 closure identity changed")
    require(value["scope"] == "synthetic-media-recovery-and-acceleration-toolkit"
            and value["production_adoption"] is False
            and value["production_media_used"] is False,
            "Phase 6 closure must not claim production adoption")
    require(value["kit_components"] == [
        "protected-original-recovery",
        "encrypted-application-and-media-recovery",
        "explicit-media-integration-selection",
        "stopped-state-configuration-recovery",
        "synthetic-transcode-performance-proof",
        "cpu-fallback-and-backend-specific-gpu-gates",
    ], "Phase 6 kit component list changed")

    modules = value["modules"]
    require(isinstance(modules, list)
            and [item.get("id") for item in modules] == [
                "immich", "media-management", "jellyfin"],
            "Phase 6 closure must cover Immich, media management and Jellyfin")
    immich, media, jellyfin = modules
    require(set(immich) == {"id", "authoritative_material", "recovery", "acceleration"}
            and immich["authoritative_material"] == [
                "postgres-custom-dump", "library", "upload", "profile"]
            and immich["acceleration"] == "machine-learning-cpu"
            and len(immich["recovery"]) == 3,
            "Immich Phase 6 closure changed")
    require(set(media) == {"id", "components", "selection", "recovery"}
            and media["components"] == list(media_management.COMPONENTS)
            and media["selection"] == "explicit-no-default"
            and media["recovery"] == [
                "all-selected-services-stopped", "sqlite-quick-check",
                "independent-root", "shared-data-semantics"],
            "Media-management Phase 6 closure changed")
    require(set(jellyfin) == {"id", "authoritative_material", "recovery", "acceleration"}
            and jellyfin["authoritative_material"] == [
                "built-in-application-archive", "owner-managed-media-original"]
            and jellyfin["acceleration"] ==
            "native-windows-intel-qsv-with-cpu-fallback"
            and len(jellyfin["recovery"]) == 3,
            "Jellyfin Phase 6 closure changed")
    require(value["acceleration"] == {
        "immich_machine_learning": "cpu",
        "jellyfin_qsv": "synthetic-proof-required",
        "jellyfin_fallback": "cpu",
        "jellyfin_nvenc_reference_host": "blocked-driver-below-522.25",
    }, "Phase 6 backend-specific acceleration policy changed")
    require(value["remaining_boundaries"] == [
        "owner-production-adoption",
        "physical-off-host-storage-and-scheduling",
        "production-library-capacity-and-client-testing",
        "hdr-tone-mapping-and-low-power-encoding",
        "four-stream-transcode-concurrency",
        "external-provider-and-download-configuration",
    ], "Phase 6 remaining-boundary list changed")
    for relative in (
        "docs/phase6-media-kit.md",
        "docs/validation/phase6-closure.md",
        "docs/releases/v0.7.0.md",
    ):
        require((root / relative).is_file(),
                f"Phase 6 closure document missing {relative}")
    return ("PASS: Phase 6 0.7.0 closure binds protected-original and encrypted "
            "media recovery, eight explicit media integrations, stopped-state "
            "restore validation and measured Intel QSV with CPU fallback")


def main() -> int:
    try:
        print(validate_closure())
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
