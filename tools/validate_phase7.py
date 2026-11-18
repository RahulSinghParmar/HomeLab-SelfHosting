"""Validate the first Phase 7 development and host-integration contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homelab import (code_server, code_server_migration, coolify_adapter,
                     docker_updates, matrix, matrix_integration)


RELEASE = "0.8.0-alpha.6"


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

    matrix_images = matrix.load_images(root / "modules/matrix/images.json")
    require(matrix_images["synapse"]["version"] == "1.164.2"
            and matrix_images["database"]["version"] == "15.19.0"
            and matrix_images["element"]["version"] == "1.12.35",
            "Reviewed Matrix component versions changed")
    require(all(set(matrix_images[role]["platform_digests"])
                == {"amd64", "arm64"} and "@sha256:" in
                matrix_images[role]["image"] for role in matrix.ROLES),
            "Matrix immutable multiarchitecture inputs changed")
    matrix_selection = matrix.load_selection(
        root / "modules/matrix/selection.example.json")
    matrix_plan = matrix.make_plan(matrix_selection, matrix_images)
    matrix_spec = matrix.compose(matrix_plan)
    require(matrix_plan["identity"] == {
        "server_name": "matrix.example.invalid",
        "renamable_after_restore": False,
        "signing_key_required": True,
    } and matrix_plan["client_e2ee_recovery"]
        == "separate-owner-validated-key-backup"
        and matrix_plan["production_state_adopted"] is False
        and matrix_plan["deployment_performed"] is False,
        "Matrix identity or review-only boundary changed")
    require(matrix_plan["features"] == matrix.FEATURES
            and not any(matrix_plan["features"][name] for name in
                        ("federation", "open_registration", "turn", "bridges",
                         "admin_ui", "metrics")),
            "Optional Matrix integrations must remain separately gated")
    require(matrix_spec["services"]["synapse"]["ports"] == [{
        "target": 8008, "published": "18008", "host_ip": "127.0.0.1",
        "protocol": "tcp"}]
        and matrix_spec["services"]["element"]["ports"] == [{
            "target": 80, "published": "18089", "host_ip": "127.0.0.1",
            "protocol": "tcp"}]
        and matrix_spec["networks"]["backend"]["internal"] is True
        and matrix_spec["services"]["database"]["environment"]
            ["POSTGRES_PASSWORD_FILE"] == "/run/secrets/postgres_password",
        "Matrix loopback, database-network or secret-file policy changed")
    matrix_text = json.dumps(matrix_spec).casefold()
    require("docker.sock" not in matrix_text and "privileged" not in matrix_text
            and "registration_shared_secret" not in matrix_text
            and "macaroon_secret_key" not in matrix_text,
            "Matrix Compose leaked control or production secret material")
    matrix_trial = (root / "tools/matrix_trial.py").read_text(encoding="utf-8")
    for marker in ("RUN-ISOLATED-MATRIX-TRIAL", "pg_dump", "pg_restore",
                   "signing_key_sha256_before", "source_removed",
                   "client_key_backup_tested", "production_messages_read",
                   "cleanup_completed"):
        require(marker in matrix_trial, f"Matrix trial gate missing {marker}")

    coolify_policy = coolify_adapter.load_policy(
        root / "modules/coolify/policy.example.json")
    require(coolify_policy["platform"]
            == "windows-docker-desktop-existing-instance"
            and coolify_policy["backup"]["encrypted_off_host_required"] is True
            and coolify_policy["backup"]["managed_application_data_included"] is False,
            "Coolify support or backup boundary changed")
    require(coolify_policy["components"] == {
        name: {"owner": coolify_adapter.OWNERS[name],
               "docker_control": name in coolify_adapter.DOCKER_CONTROL}
        for name in coolify_adapter.COMPONENTS
    }, "Coolify component ownership changed")
    coolify_source = (root / "homelab/coolify_adapter.py").read_text(
        encoding="utf-8")
    for marker in ("experimental-existing-instance-only", "update_ready",
                   "managed_application_recovery_included",
                   "generated_resources_adopted", "changes_performed"):
        require(marker in coolify_source,
                f"Coolify non-owning adapter gate missing {marker}")

    migration_policy = code_server_migration.load_policy(
        root / "modules/code-server/migration.example.json")
    migration_plan = code_server_migration.make_plan(migration_policy)
    require(migration_plan["backup"]["full_data_check"] is True
            and migration_plan["backup"]["repository_separate_physical_disk"] is True
            and migration_plan["backup"]["recovery_key_separate_physical_disk"] is True
            and migration_plan["network"]["target_publish"] == "127.0.0.1:8443"
            and migration_plan["production_change_authorized"] is False
            and migration_plan["execution_performed"] is False,
            "Code-server encrypted migration gates changed")

    integration_policy = matrix_integration.load_policy(
        root / "modules/matrix/integration.example.json")
    require(integration_policy["identity"] == {
        "server_name": "matrix.parmar.homes", "immutable": True}
        and integration_policy["network"]["matrix_target_binding"]
            == "127.0.0.1:8008"
        and integration_policy["network"]["element_target_binding"]
            == "127.0.0.1:8089"
        and integration_policy["network"]["turn_dns_mode"]
            == "direct-dns-only"
        and integration_policy["network"]
            ["cloudflare_tunnel_supports_turn"] is False
        and integration_policy["turn"]["optional"] is True,
        "Matrix/Element or optional TURN integration policy changed")
    probe = (root / "tools/matrix_turn_probe.py").read_text(encoding="utf-8")
    for marker in ("BINDING_REQUEST", "BINDING_SUCCESS",
                   "mapped_address_present", "address_value_disclosed",
                   "credential_used"):
        require(marker in probe, f"Matrix TURN probe gate missing: {marker}")
    turn_workflow = (root / ".github/workflows/matrix-turn-probe.yml").read_text(
        encoding="utf-8")
    for marker in ("workflow_dispatch", "permissions:", "contents: read",
                   "MATRIX_TURN_TEST_USERNAME", "MATRIX_TURN_TEST_PASSWORD",
                   "turnutils_uclient"):
        require(marker in turn_workflow,
                f"Matrix external TURN workflow gate missing: {marker}")

    update_policy = docker_updates.load_policy(
        root / "modules/docker-updates/policy.example.json")
    require(update_policy["defaults"]["mode"] == "audit-only"
            and update_policy["projects"]["example-stack"]["mode"] == "manual"
            and update_policy["projects"]["controller-owned-example"]["mode"]
            == "controller-managed",
            "Docker update ownership defaults changed")
    update_source = (root / "homelab/docker_updates.py").read_text(
        encoding="utf-8")
    for marker in ("ROLLING_TAGS", "compose_sha256", "source_image_id",
                   "backup_required", "manual-recovery-required",
                   "--force-recreate", "plan_id"):
        require(marker in update_source,
                f"Docker update safety gate missing: {marker}")

    cli = (root / "homelab/cli.py").read_text(encoding="utf-8")
    require("'code-server'" in cli and "from . import code_server as module" in cli
            and "'matrix'" in cli and "from . import matrix as module" in cli
            and "'coolify'" in cli and "from . import coolify_adapter as module" in cli
            and "'code-server-migration'" in cli
            and "from . import code_server_migration as module" in cli
            and "'matrix-integration'" in cli
            and "from . import matrix_integration as module" in cli
            and "'docker-updates'" in cli
            and "from . import docker_updates as module" in cli
            and "render-compose" in cli and "validate-evidence" in cli,
            "Phase 7 code-server/Matrix/Coolify CLI is not wired")
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
        "docs/matrix-module.md",
        "docs/validation/matrix.md",
        "docs/releases/v0.8.0-alpha.2.md",
        "modules/matrix/images.json",
        "modules/matrix/selection.example.json",
        "tests/test_matrix.py",
        "tools/matrix_trial.py",
        "docs/coolify-adapter.md",
        "docs/validation/coolify-adapter.md",
        "docs/releases/v0.8.0-alpha.3.md",
        "homelab/coolify_adapter.py",
        "modules/coolify/policy.example.json",
        "tests/test_coolify_adapter.py",
        "docs/code-server-migration.md",
        "docs/validation/code-server-migration.md",
        "docs/releases/v0.8.0-alpha.4.md",
        "homelab/code_server_migration.py",
        "modules/code-server/migration.example.json",
        "modules/code-server/restic.json",
        "tests/test_code_server_migration.py",
        "docs/matrix-integration.md",
        "docs/validation/matrix-integration.md",
        "docs/releases/v0.8.0-alpha.5.md",
        "homelab/matrix_integration.py",
        "modules/matrix/integration.example.json",
        "tests/test_matrix_integration.py",
        "tools/matrix_turn_probe.py",
        ".github/workflows/matrix-turn-probe.yml",
        "docs/docker-update-manager.md",
        "docs/validation/docker-update-manager.md",
        "docs/releases/v0.8.0-alpha.6.md",
        "homelab/docker_updates.py",
        "modules/docker-updates/policy.example.json",
        "tests/test_docker_updates.py",
    ):
        require((root / relative).is_file(), f"Missing Phase 7 artifact: {relative}")
    return ("PASS: Phase 7 0.8.0-alpha.6 provides code-server and Matrix "
            "foundations, a non-owning Coolify adapter, backup-gated "
            "code-server production migration, and strict "
            "Matrix/Element/TURN integration gates plus explicit Docker "
            "update management")


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
