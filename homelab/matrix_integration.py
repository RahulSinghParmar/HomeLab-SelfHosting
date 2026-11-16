"""Matrix/Element integration planning and optional TURN evidence contracts."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .config import ROOT, canonical, keys, load_json, need
from .sandbox import digest


CONTRACT = "phase7-matrix-integration-v1"
MODULE = ROOT / "modules/matrix"
POLICY = MODULE / "integration.example.json"
ROLES = ("synapse", "element", "coturn")
EXPECTED_RUNTIME = {
    "synapse": {
        "version": "1.164.2",
        "configured_image": "matrixdotorg/synapse:latest",
        "image_id":
            "sha256:1909bcc07d4180945464712a7f4d4bb6f644c4c1774d026d77cdadc196b91eb8",
    },
    "element": {
        "version": "1.12.33",
        "configured_image": "vectorim/element-web:latest",
        "image_id":
            "sha256:b0aa4b5a4fc1afaaff62e2dbd0c92d57e2b20724f3ccb2fef53aae949088c3d2",
    },
    "coturn": {
        "version": "4.18.0",
        "configured_image": "coturn/coturn:latest",
        "image_id":
            "sha256:bbefd3e1fdfdc0d58770fe01b581fd8b00d9f3a5580d00acb77cf719a6bc78e3",
    },
}


def _https_origin(value: object, label: str) -> str:
    need(isinstance(value, str), f"Invalid {label}")
    parsed = urlparse(value)
    need(parsed.scheme == "https" and bool(parsed.hostname)
         and parsed.username is None and parsed.password is None
         and parsed.query == "" and parsed.fragment == ""
         and parsed.path in ("", "/"),
         f"{label} must be an HTTPS origin")
    return value.rstrip("/") + "/"


def _hostname(value: object, label: str) -> str:
    need(isinstance(value, str)
         and bool(re.fullmatch(
             r"(?=.{1,255}$)(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)",
             value)), f"Invalid {label}")
    return value.casefold()


def validate_policy(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "ownership", "identity",
                 "endpoints", "runtime", "network", "turn", "validation",
                 "safety"}, "Matrix integration policy")
    need(value["kind"] == "homelab-matrix-integration-policy"
         and value["contract"] == CONTRACT
         and value["platform"] == "windows-docker-desktop-amd64",
         "Unsupported Matrix integration policy")

    keys(value["ownership"], {"compose_project", "compose_file",
                              "native_tunnel_service"},
         "Matrix integration ownership")
    need(value["ownership"] == {
        "compose_project": "matrix-synapse",
        "compose_file": "C:\\Docker\\matrix-synapse\\docker-compose.yml",
        "native_tunnel_service": "Cloudflared",
    }, "Reference Matrix lifecycle ownership changed")

    keys(value["identity"], {"server_name", "immutable"},
         "Matrix integration identity")
    server_name = _hostname(value["identity"]["server_name"],
                            "Matrix server name")
    need(value["identity"]["immutable"] is True,
         "Matrix server identity must remain immutable")

    keys(value["endpoints"], {"matrix", "element", "turn"},
         "Matrix integration endpoints")
    matrix_url = _https_origin(value["endpoints"]["matrix"],
                               "Matrix public endpoint")
    element_url = _https_origin(value["endpoints"]["element"],
                                "Element public endpoint")
    turn_host = _hostname(value["endpoints"]["turn"], "TURN hostname")
    need(urlparse(matrix_url).hostname == server_name,
         "Matrix endpoint must preserve the server name")
    need(len({urlparse(matrix_url).hostname,
              urlparse(element_url).hostname, turn_host}) == 3,
         "Matrix, Element and TURN must use distinct hostnames")

    keys(value["runtime"], set(ROLES), "Matrix integration runtime")
    for role in ROLES:
        keys(value["runtime"][role],
             {"version", "configured_image", "image_id"},
             f"Matrix integration {role} runtime")
        need(value["runtime"][role] == EXPECTED_RUNTIME[role],
             f"Reference {role} runtime identity changed")

    keys(value["network"], {"matrix_source_binding",
                            "matrix_target_binding",
                            "element_source_binding",
                            "element_target_binding", "admin_binding",
                            "turn_port", "relay_min_port", "relay_max_port",
                            "turn_transports", "turn_dns_mode",
                            "cloudflare_tunnel_supports_turn"},
         "Matrix integration network")
    need(value["network"] == {
        "matrix_source_binding": "0.0.0.0:8008",
        "matrix_target_binding": "127.0.0.1:8008",
        "element_source_binding": "0.0.0.0:8089",
        "element_target_binding": "127.0.0.1:8089",
        "admin_binding": "127.0.0.1:8448",
        "turn_port": 3478,
        "relay_min_port": 49160,
        "relay_max_port": 49200,
        "turn_transports": ["udp", "tcp"],
        "turn_dns_mode": "direct-dns-only",
        "cloudflare_tunnel_supports_turn": False,
    }, "Matrix/Element loopback or TURN network policy changed")

    keys(value["turn"], {"optional", "configured", "shared_secret_match",
                         "ddns_required", "external_stun_required",
                         "external_relay_required", "real_call_required"},
         "Matrix TURN policy")
    need(value["turn"] == {
        "optional": True,
        "configured": True,
        "shared_secret_match": True,
        "ddns_required": True,
        "external_stun_required": True,
        "external_relay_required": True,
        "real_call_required": True,
    }, "Optional TURN validation policy changed")

    keys(value["validation"], {"local_matrix", "public_matrix",
                               "public_element", "well_known_client",
                               "well_known_server", "element_config",
                               "restart_persistence"},
         "Matrix integration validation")
    need(all(item is True for item in value["validation"].values()),
         "Matrix/Element integration gates cannot be disabled")

    need(value["safety"] == {
        "server_name_change": False,
        "signing_key_replacement": False,
        "federation_change": False,
        "bridge_change": False,
        "automatic_image_pull": False,
    }, "Matrix integration safety boundary changed")

    result = json.loads(canonical(value))
    result["identity"]["server_name"] = server_name
    result["endpoints"] = {
        "matrix": matrix_url, "element": element_url, "turn": turn_host}
    return result


def load_policy(path: Path = POLICY) -> dict:
    return validate_policy(load_json(path))


def validate_audit(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "identity", "runtime",
                 "http", "exposure", "turn", "ddns", "safety", "audit_id"},
         "Matrix integration audit")
    need(value["kind"] == "homelab-matrix-integration-audit"
         and value["contract"] == CONTRACT
         and value["platform"] == "windows-docker-desktop-amd64",
         "Unsupported Matrix integration audit")

    keys(value["identity"], {"server_name", "element_server_name",
                             "unchanged"}, "Matrix audit identity")
    need(value["identity"]["server_name"]
         == value["identity"]["element_server_name"]
         and value["identity"]["unchanged"] is True,
         "Synapse and Element identities do not match")

    keys(value["runtime"], set(ROLES), "Matrix audit runtime")
    for role in ROLES:
        keys(value["runtime"][role],
             {"version", "image_id", "state", "health"},
             f"Matrix audit {role} runtime")
        need(value["runtime"][role]["version"]
             == EXPECTED_RUNTIME[role]["version"]
             and value["runtime"][role]["image_id"]
             == EXPECTED_RUNTIME[role]["image_id"]
             and value["runtime"][role]["state"] == "running",
             f"Matrix audit {role} runtime drifted")
    need(value["runtime"]["synapse"]["health"] == "healthy"
         and value["runtime"]["element"]["health"] == "healthy"
         and value["runtime"]["coturn"]["health"] in ("running", "healthy"),
         "Matrix, Element or coturn is not healthy")

    keys(value["http"], {"local_matrix", "public_matrix", "public_element",
                         "well_known_client", "well_known_server",
                         "element_config_matches"}, "Matrix audit HTTP")
    need(all(type(item) is bool for item in value["http"].values()),
         "Matrix HTTP observations must be booleans")

    keys(value["exposure"], {"matrix_loopback", "element_loopback",
                             "admin_loopback", "native_tunnel_running"},
         "Matrix audit exposure")
    need(all(type(item) is bool for item in value["exposure"].values()),
         "Matrix exposure observations must be booleans")

    keys(value["turn"], {"configured", "shared_secret_present",
                         "shared_secret_matches", "local_stun",
                         "dns_direct", "dns_matches_public_ipv4",
                         "external_stun", "external_relay", "real_call"},
         "Matrix audit TURN")
    need(all(type(item) is bool for item in value["turn"].values()),
         "TURN observations must be booleans")
    need(value["turn"]["configured"] is True
         and value["turn"]["shared_secret_present"] is True,
         "Configured TURN must retain its shared secret")

    keys(value["ddns"], {"running", "scheduled", "last_update_success",
                         "error_class"}, "Matrix audit DDNS")
    need(type(value["ddns"]["running"]) is bool
         and type(value["ddns"]["scheduled"]) is bool
         and type(value["ddns"]["last_update_success"]) is bool
         and value["ddns"]["error_class"] in (
             "none", "api-token-client-ip-filter", "other"),
         "Invalid Matrix DDNS evidence")

    need(value["safety"] == {
        "secrets_disclosed": False,
        "production_messages_read": False,
        "production_media_read": False,
        "changes_made": False,
    }, "Matrix audit crossed its privacy or read-only boundary")
    copy = dict(value)
    identifier = copy.pop("audit_id")
    need(identifier == digest(copy), "Matrix audit identifier changed")
    return value


def make_plan(policy: dict, audit: dict) -> dict:
    policy = validate_policy(policy)
    audit = validate_audit(audit)
    need(audit["identity"]["server_name"] == policy["identity"]["server_name"],
         "Matrix audit belongs to another server identity")

    matrix_element_ready = (
        all(audit["http"].values())
        and audit["exposure"]["admin_loopback"]
        and audit["exposure"]["native_tunnel_running"]
    )
    loopback_ready = (audit["exposure"]["matrix_loopback"]
                      and audit["exposure"]["element_loopback"])
    turn_config_ready = all(audit["turn"][name] for name in (
        "configured", "shared_secret_present", "shared_secret_matches",
        "local_stun", "dns_direct"))
    turn_public_ready = (turn_config_ready
                         and audit["ddns"]["last_update_success"]
                         and all(audit["turn"][name] for name in (
                             "dns_matches_public_ipv4", "external_stun",
                             "external_relay", "real_call")))
    blockers = []
    if not loopback_ready:
        blockers.append("matrix-and-element-direct-ports-not-loopback-only")
    if not audit["ddns"]["last_update_success"]:
        blockers.append("turn-ddns-update-failed")
    if not audit["turn"]["dns_matches_public_ipv4"]:
        blockers.append("turn-dns-does-not-match-current-public-ipv4")
    if not audit["turn"]["external_stun"]:
        blockers.append("turn-external-stun-not-proven")
    if not audit["turn"]["external_relay"]:
        blockers.append("turn-external-relay-not-proven")
    if not audit["turn"]["real_call"]:
        blockers.append("element-real-call-not-proven")

    result = {
        "kind": "homelab-matrix-integration-plan",
        "contract": CONTRACT,
        "platform": policy["platform"],
        "audit_id": audit["audit_id"],
        "identity": policy["identity"],
        "endpoints": policy["endpoints"],
        "matrix_element_ready": matrix_element_ready,
        "loopback_hardening_ready": loopback_ready,
        "turn_config_ready": turn_config_ready,
        "turn_public_ready": turn_public_ready,
        "turn_optional": True,
        "ordered_gates": [
            "read-only-runtime-and-identity-audit",
            "compose-rollback-copy",
            "matrix-and-element-loopback-bindings",
            "local-and-public-http-validation",
            "well-known-and-element-config-validation",
            "turn-shared-secret-parity-without-disclosure",
            "direct-dns-current-address-validation",
            "external-udp-and-tcp-stun-probe",
            "external-authenticated-relay-probe",
            "real-element-call-test",
            "controlled-restart-and-rollback-check",
        ],
        "blockers": blockers,
        "production_change_authorized": False,
        "changes_performed": False,
    }
    result["plan_id"] = digest(result)
    return result


def validate_plan(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "audit_id", "identity",
                 "endpoints", "matrix_element_ready",
                 "loopback_hardening_ready", "turn_config_ready",
                 "turn_public_ready", "turn_optional", "ordered_gates",
                 "blockers", "production_change_authorized",
                 "changes_performed", "plan_id"},
         "Matrix integration plan")
    need(value["kind"] == "homelab-matrix-integration-plan"
         and value["contract"] == CONTRACT
         and value["platform"] == "windows-docker-desktop-amd64",
         "Unsupported Matrix integration plan")
    need(value["identity"]["immutable"] is True
         and value["turn_optional"] is True
         and value["production_change_authorized"] is False
         and value["changes_performed"] is False,
         "Matrix integration plan exceeded its review-only boundary")
    need(all(type(value[name]) is bool for name in (
        "matrix_element_ready", "loopback_hardening_ready",
        "turn_config_ready", "turn_public_ready")),
         "Invalid Matrix readiness state")
    copy = dict(value)
    identifier = copy.pop("plan_id")
    need(identifier == digest(copy), "Matrix integration plan changed")
    return value


def validate_evidence(value: object, plan: dict) -> dict:
    plan = validate_plan(plan)
    keys(value, {"kind", "contract", "plan_id", "identity", "integration",
                 "turn", "restart", "safety", "evidence_id"},
         "Matrix integration evidence")
    need(value["kind"] == "homelab-matrix-integration-evidence"
         and value["contract"] == CONTRACT
         and value["plan_id"] == plan["plan_id"],
         "Matrix integration evidence does not match the reviewed plan")

    identity = value["identity"]
    keys(identity, {"server_name", "signing_key_sha256_before",
                    "signing_key_sha256_after", "unchanged"},
         "Matrix integration identity evidence")
    need(identity["server_name"] == plan["identity"]["server_name"]
         and identity["unchanged"] is True
         and identity["signing_key_sha256_before"]
             == identity["signing_key_sha256_after"]
         and bool(re.fullmatch(r"[0-9a-f]{64}",
                              identity["signing_key_sha256_before"])),
         "Matrix identity or signing key changed")

    integration = value["integration"]
    keys(integration, {"compose_rollback_copy", "matrix_loopback",
                       "element_loopback", "local_matrix", "public_matrix",
                       "public_element", "well_known_client",
                       "well_known_server", "element_config_matches"},
         "Matrix/Element integration evidence")
    need(all(item is True for item in integration.values()),
         "Matrix/Element integration is incomplete")

    turn = value["turn"]
    keys(turn, {"selected", "shared_secret_matches", "dns_direct",
                "dns_matches_public_ipv4", "local_stun", "external_udp_stun",
                "external_tcp_stun", "external_relay", "real_audio_call",
                "real_video_call"}, "Matrix TURN evidence")
    need(type(turn["selected"]) is bool,
         "TURN selection must be explicit")
    turn_checks = [name for name in turn if name != "selected"]
    if turn["selected"]:
        need(all(turn[name] is True for name in turn_checks),
             "Selected TURN requires external STUN, relay and real-call proof")
    else:
        need(all(turn[name] is False for name in turn_checks),
             "Unselected TURN must not carry inferred success claims")

    restart = value["restart"]
    keys(restart, {"matrix_healthy", "element_healthy", "public_matrix",
                   "public_element", "turn_healthy_if_selected"},
         "Matrix integration restart evidence")
    need(all(restart[name] is True for name in (
        "matrix_healthy", "element_healthy", "public_matrix",
        "public_element")), "Matrix/Element restart persistence failed")
    need(restart["turn_healthy_if_selected"] is turn["selected"],
         "TURN restart evidence does not match its selection")

    need(value["safety"] == {
        "server_name_changed": False,
        "signing_key_replaced": False,
        "database_migrated": False,
        "federation_changed": False,
        "bridge_changed": False,
        "secrets_disclosed": False,
        "rollback_retained": True,
    }, "Matrix integration crossed its identity or safety boundary")
    copy = dict(value)
    identifier = copy.pop("evidence_id")
    need(identifier == digest(copy), "Matrix integration evidence changed")
    return value
