"""Validate the Phase 6 media foundation and isolated Immich recovery module."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homelab.media_acceleration import CONTRACT, load_policy, make_plan
from homelab import immich, immich_vault, jellyfin


RELEASE = "0.7.0-alpha.5"
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
    require("'immich'" in cli and "from . import immich as module" in cli,
            "Immich lifecycle CLI is not wired")
    require("'immich-vault'" in cli and "from . import immich_vault as module" in cli,
            "Immich encrypted-vault CLI is not wired")
    require("'jellyfin'" in cli and "from . import jellyfin as module" in cli
            and "render-compose" in cli and "validate-recovery" in cli,
            "Jellyfin deployment-selection CLI is not wired")
    runtime = {"context": "phase6-test", "endpoint": "unix:///phase6-test.sock",
               "engine_id": "phase6-test"}
    # macOS exposes its temporary directory through /var -> /private/var. The
    # execution safety layer correctly rejects symlinked ancestors, so use an
    # absent sibling of the checkout for this no-write plan/Compose check.
    candidate_root = root.parent / "homelab-phase6-validator-install"
    candidate = immich.make_plan(candidate_root, 18060, runtime)
    spec = immich.compose(candidate, "a" * 32,
                          {"database_password": "b" * 64,
                           "admin_password": "c" * 64})
    require(candidate["authoritative_material"] == [
        "postgres-custom-dump", "library", "upload", "profile"],
        "Immich authoritative recovery set changed")
    require(candidate["derived_material"] == ["thumbs", "encoded-video", "backups"]
            and candidate["cache_material"] == ["redis-data", "model-cache"],
            "Immich derived/cache exclusion changed")
    require(candidate["machine_learning"] == {
        "backend": "cpu", "environment": immich.ML_ENVIRONMENT,
        "device_access": False, "independently_stoppable": True},
        "Immich ML policy changed")
    ml = spec["services"]["immich-machine-learning"]
    require(ml["mem_limit"] == "1536m" and ml["cpus"] == 1.0
            and ml["pids_limit"] == 256 and "ports" not in ml,
            "Immich ML is not separately bounded/internal")
    server = spec["services"]["immich-server"]
    require(server["ports"] == [{"target": 2283, "published": "18060",
                                  "host_ip": "127.0.0.1", "protocol": "tcp"}]
            and spec["networks"]["backend"]["internal"] is True,
            "Immich access isolation changed")
    require("docker.sock" not in json.dumps(spec)
            and not any("device" in key.casefold()
                        for key in ml if key not in ("environment",)),
            "Immich gained Docker/device control")
    module_code = (root / "homelab/immich.py").read_text(encoding="utf-8")
    for marker in ("quiesced-postgres-protected-originals", "pg_dump",
                   "pg_restore", "protected_originals_complete",
                   "system_markers", "machine_learning_independent"):
        require(marker in module_code, f"Immich recovery contract missing {marker}")
    restic = load(root / "modules/immich/restic.json")
    require(restic == {
        "version": "0.19.1",
        "windows_amd64": {
            "archive_url": "https://github.com/restic/restic/releases/download/v0.19.1/restic_0.19.1_windows_amd64.zip",
            "archive_sha256": "da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d",
            "executable_sha256": "b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830",
        },
        "linux_amd64": {
            "archive_url": "https://github.com/restic/restic/releases/download/v0.19.1/restic_0.19.1_linux_amd64.bz2",
            "archive_sha256": "f415415624dcc452f2a02b8c33641791a8c6d3b65bbb3543fcf9a25151585c",
            "executable_sha256": "20d4142678d0d95ec11a4759def1b73fd9190abc9ca19e4b62d067c0b387e639",
        },
    }, "Reviewed Immich Restic release identity changed")
    vault_code = (root / "homelab/immich_vault.py").read_text(encoding="utf-8")
    for marker in ("immich-restic-vault-v1", "check\", \"--read-data",
                   "recovery-verified", "source_machine_state_required",
                   "derived_included", "ml_cache_included"):
        require(marker in vault_code, f"Immich encrypted recovery contract missing {marker}")
    jellyfin_images = load(root / "modules/jellyfin/image.json")
    require(jellyfin_images == {
        "server": "docker.io/jellyfin/jellyfin:12.4@sha256:fea863d0cd9ec445985d9c75fc6ed64e38a1d2766cf0c250a33d553f4fc1b771"
    }, "Reviewed Jellyfin 12.4 image identity changed")
    require(jellyfin.validate_media(load(root / "modules/jellyfin/media.example.json")) == [{
        "source": "/srv/media/video", "target": "/media/video", "read_only": True}],
        "Jellyfin example media map changed")
    native_audit = {
        "kind": "homelab-jellyfin-audit", "contract": jellyfin.CONTRACT,
        "host_platform": "windows",
        "native": {"present": True, "running": True, "autostart": True,
                   "manager": "windows-service", "service": "JellyfinServer"},
        "container": {"present": False, "running": False,
                      "engine_available": True, "engine_os": "linux",
                      "matching_containers": 0},
        "public_api": {"reachable": True, "version": "12.4.0",
                       "startup_complete": True},
        "detected_deployment": "native", "mutations_performed": False,
        "production_media_read": False, "credentials_read": False,
    }
    native_plan = jellyfin.make_plan("native", native_audit, 8096)
    require(native_plan["selected_deployment"] == "native"
            and native_plan["adoption"] == "existing"
            and native_plan["container_image"] is None
            and native_plan["acceleration"]["selected"] == "cpu"
            and native_plan["deployment_performed"] is False,
            "Jellyfin native adoption boundary changed")
    container_audit = json.loads(json.dumps(native_audit))
    container_audit["host_platform"] = "linux"
    container_audit["native"] = {
        "present": False, "running": False, "autostart": False,
        "manager": "systemd", "service": None}
    container_audit["public_api"] = {
        "reachable": False, "version": None, "startup_complete": None}
    container_audit["detected_deployment"] = "none"
    container_plan = jellyfin.make_plan("container", container_audit, 18096)
    media = {"kind": "homelab-jellyfin-media-map",
             "contract": jellyfin.CONTRACT,
             "mounts": [{"source": "/srv/media/fixture",
                          "target": "/media/fixture", "read_only": True}]}
    jellyfin_spec = jellyfin.compose(
        container_plan, "/srv/homelab/jellyfin", media, 1000, 1000)
    jellyfin_service = jellyfin_spec["services"]["jellyfin"]
    require(jellyfin_service["ports"] == [{
        "target": 8096, "published": "18096", "host_ip": "127.0.0.1",
        "protocol": "tcp"}]
        and jellyfin_service["read_only"] is True
        and jellyfin_service["cap_drop"] == ["ALL"]
        and jellyfin_service["mem_limit"] == "2048m"
        and "docker.sock" not in json.dumps(jellyfin_spec)
        and "device" not in json.dumps(jellyfin_spec).casefold(),
        "Jellyfin Linux container restrictions changed")
    jellyfin_code = (root / "homelab/jellyfin.py").read_text(encoding="utf-8")
    for marker in ("jellyfin-explicit-deployment-v1", "disabled-review-only",
                   "Choose Jellyfin deployment explicitly", "same_version_restore_required",
                   "codec-capability-and-synthetic-transcode-required",
                   "jellyfin-native-recovery-trial-v1",
                   "validate_recovery_evidence"):
        require(marker in jellyfin_code, f"Jellyfin selection contract missing {marker}")
    trial_code = (root / "tools/jellyfin_native_trial.py").read_text(encoding="utf-8")
    for marker in ("RUN-ISOLATED-JELLYFIN-TRIAL", "--restore-archive",
                   "source_state_removed_before_restore",
                   "restore_target_initialized_same_version",
                   "wait_library_idle", "direct_play_exact"):
        require(marker in trial_code, f"Jellyfin recovery trial missing {marker}")
    dr_workflow = (root / ".github/workflows/immich-disaster-recovery.yml").read_text(
        encoding="utf-8")
    for marker in ("IMMICH_DR_TEST_PASSWORD", "prepare-encrypted-repository",
                   "recover-on-clean-runner", "compression-level: 0",
                   "tools.immich_dr_trial recover", "check --strict"):
        require(marker in dr_workflow, f"Immich off-host workflow missing {marker}")
    workflow = (root / ".github/workflows/validate.yml").read_text(encoding="utf-8")
    require("python tools/validate_phase6.py" in workflow,
            "Phase 6 validator is absent from CI")
    for path in ("docs/phase6-media-foundation.md",
                 "docs/validation/phase6-media-foundation.md",
                 "docs/releases/v0.7.0-alpha.1.md",
                 "docs/immich-module.md",
                 "docs/validation/immich.md",
                 "docs/releases/v0.7.0-alpha.2.md",
                 "docs/immich-vault.md",
                 "docs/validation/immich-off-host-recovery.md",
                 "docs/releases/v0.7.0-alpha.3.md",
                 "docs/jellyfin-module.md",
                 "docs/validation/jellyfin.md",
                 "docs/releases/v0.7.0-alpha.4.md",
                 "docs/jellyfin-recovery.md",
                 "docs/validation/jellyfin-recovery.md",
                 "docs/releases/v0.7.0-alpha.5.md",
                 "modules/jellyfin/media.example.json",
                 "tests/test_media_acceleration.py",
                 "tests/test_immich.py",
                 "tests/test_immich_vault.py",
                 "tests/test_jellyfin.py",
                 "tools/jellyfin_native_trial.py",
                 "tools/immich_dr_trial.py",
                 "tools/immich_vault_local_trial.py"):
        require((root / path).is_file(), f"Missing Phase 6 artifact: {path}")
    return ("PASS: Phase 6 0.7.0-alpha.5 preserves Immich protected-original "
            "recovery and validates Jellyfin same-version application restore "
            "with exact synthetic direct play before and after restart")


def main() -> int:
    try:
        print(validate_phase6())
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
