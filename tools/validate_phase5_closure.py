"""Validate the final Phase 5 encrypted recovery-kit and semantic restore contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.validate_phase5 import RESTIC_VERSION, load_json, require, validate_phase5


RELEASE = "0.6.0"
CONTRACT = "phase5-recovery-closure-v1"
COMMON_PROOF_FIELDS = (
    "clean_runner",
    "source_machine_state_used",
    "full_repository_data_check",
    "decryption_verified",
    "production_data_used",
)
MODULE_FILES = {
    "paperless-ngx": ("homelab/paperless.py", "tools/paperless_dr_trial.py"),
    "affine": ("homelab/affine.py", "tools/affine_dr_trial.py"),
    "nextcloud": ("homelab/nextcloud.py", "tools/nextcloud_dr_trial.py"),
    "firefly-iii": ("homelab/firefly.py", "tools/firefly_dr_trial.py"),
    "vaultwarden": ("homelab/vaultwarden.py", "tools/vaultwarden_dr_trial.py"),
    "karakeep": ("homelab/karakeep.py", "tools/karakeep_dr_trial.py"),
}


def validate_closure(root: Path = ROOT) -> str:
    base = validate_phase5(root)
    require(RELEASE in base, "Phase 5 release validator is not final")
    closure = load_json(root / "modules/phase5/closure.json")
    require(set(closure) == {"contract", "release", "scope", "production_adoption",
                             "production_data_used", "encryption", "retention",
                             "kit_components", "modules"},
            "Phase 5 closure fields changed")
    require(closure["contract"] == CONTRACT and closure["release"] == RELEASE,
            "Phase 5 closure identity changed")
    require(closure["scope"] == "synthetic-application-recovery-toolkit"
            and closure["production_adoption"] is False
            and closure["production_data_used"] is False,
            "Phase 5 closure must not claim production-data adoption")
    require(closure["encryption"] == {
        "tool": "restic",
        "version": RESTIC_VERSION,
        "full_data_check_required": True,
        "recovery_key_separate_from_repository": True,
    }, "Phase 5 encryption closure changed")
    require(closure["retention"] == {
        "daily": 7,
        "weekly": 4,
        "monthly": 3,
        "apply_requires_restore_verified": True,
    }, "Phase 5 retention closure changed")
    require(closure["kit_components"] == [
        "tagged-source-and-runbooks",
        "encrypted-repository-per-module",
        "portable-recovery-manifest-per-module",
        "separately-custodied-recovery-key-per-module",
        "sanitized-clean-runner-recovery-proof-per-module",
    ], "Phase 5 recovery-kit component list changed")

    integrated = load_json(root / "modules/phase5/recovery.json")
    modules = closure["modules"]
    require(isinstance(modules, list) and len(modules) == 6,
            "Phase 5 closure must cover exactly six modules")
    require([item["id"] for item in modules] == [item["id"] for item in integrated["modules"]]
            == list(MODULE_FILES), "Phase 5 closure module order or coverage changed")

    for item, integrated_item in zip(modules, integrated["modules"]):
        module_id = item["id"]
        require(set(item) == {"id", "consistency_method", "fixture_marker",
                              "authoritative_material", "semantic_proof_fields"},
                f"{module_id}: closure fields changed")
        require(isinstance(item["consistency_method"], str)
                and len(item["consistency_method"]) >= 12,
                f"{module_id}: consistency method missing")
        require(isinstance(item["fixture_marker"], str) and item["fixture_marker"],
                f"{module_id}: nonempty test-content marker missing")
        require(isinstance(item["authoritative_material"], list)
                and len(item["authoritative_material"]) >= 3
                and len(item["authoritative_material"]) == len(set(item["authoritative_material"])),
                f"{module_id}: authoritative recovery material incomplete")
        fields = item["semantic_proof_fields"]
        require(isinstance(fields, list) and len(fields) >= 3
                and len(fields) == len(set(fields)),
                f"{module_id}: semantic restore proof is incomplete")

        application_path, trial_path = MODULE_FILES[module_id]
        application = (root / application_path).read_text(encoding="utf-8")
        trial = (root / trial_path).read_text(encoding="utf-8")
        workflow = (root / ".github/workflows" / integrated_item["workflow"]).read_text(
            encoding="utf-8")
        require(item["fixture_marker"] in application,
                f"{module_id}: declared nonempty fixture marker is absent")
        require(f"'method': '{item['consistency_method']}'" in application,
                f"{module_id}: declared consistency method differs from implementation")
        for field in (*COMMON_PROOF_FIELDS, *fields):
            require(f"'{field}':" in trial,
                    f"{module_id}: hosted recovery proof missing {field}")
        require("'source_machine_state_used': False" in trial
                and "'production_data_used': False" in trial,
                f"{module_id}: clean synthetic recovery boundary changed")
        require("recover(work_root" in trial and "restart" in trial.lower(),
                f"{module_id}: application restore/restart trial changed")
        trial_module = trial_path.removesuffix(".py").replace("/", ".")
        require(trial_module in workflow and "recovery-proof.json" in workflow,
                f"{module_id}: workflow no longer runs or publishes semantic proof")

    integrated_workflow = (
        root / ".github/workflows/phase5-integrated-recovery.yml").read_text(encoding="utf-8")
    require(integrated_workflow.count("uses: ./.github/workflows/") == 6,
            "Phase 5 closure must invoke all six clean-runner recovery workflows")
    for relative in ("docs/phase5-recovery-kit.md",
                     "docs/validation/phase5-closure.md",
                     "docs/releases/v0.6.0.md"):
        require((root / relative).is_file(), f"Phase 5 closure document missing {relative}")
    return ("PASS: Phase 5 0.6.0 closure binds six application-consistent backups, "
            "nonempty semantic restore proofs, separate-key encrypted repositories, "
            "full-data checks and restore-gated 7/4/3 retention")


def main() -> int:
    try:
        print(validate_closure())
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
