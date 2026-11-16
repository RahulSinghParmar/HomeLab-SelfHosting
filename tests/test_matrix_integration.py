"""Phase 7 Matrix/Element and optional TURN integration tests."""
from __future__ import annotations

import copy
import struct
import unittest

from homelab import matrix_integration as integration
from homelab.config import ConfigError
from homelab.sandbox import digest
from tools import matrix_turn_probe


def sample_audit() -> dict:
    value = {
        "kind": "homelab-matrix-integration-audit",
        "contract": integration.CONTRACT,
        "platform": "windows-docker-desktop-amd64",
        "identity": {
            "server_name": "matrix.parmar.homes",
            "element_server_name": "matrix.parmar.homes",
            "unchanged": True,
        },
        "runtime": {
            role: {
                "version": item["version"],
                "image_id": item["image_id"],
                "state": "running",
                "health": "running" if role == "coturn" else "healthy",
            }
            for role, item in integration.EXPECTED_RUNTIME.items()
        },
        "http": {
            "local_matrix": True,
            "public_matrix": True,
            "public_element": True,
            "well_known_client": True,
            "well_known_server": True,
            "element_config_matches": True,
        },
        "exposure": {
            "matrix_loopback": False,
            "element_loopback": False,
            "admin_loopback": True,
            "native_tunnel_running": True,
        },
        "turn": {
            "configured": True,
            "shared_secret_present": True,
            "shared_secret_matches": True,
            "local_stun": True,
            "dns_direct": True,
            "dns_matches_public_ipv4": False,
            "external_stun": False,
            "external_relay": False,
            "real_call": False,
        },
        "ddns": {
            "running": True,
            "scheduled": True,
            "last_update_success": False,
            "error_class": "api-token-client-ip-filter",
        },
        "safety": {
            "secrets_disclosed": False,
            "production_messages_read": False,
            "production_media_read": False,
            "changes_made": False,
        },
    }
    value["audit_id"] = digest(value)
    return value


def completed_evidence(plan: dict, *, turn_selected: bool = True) -> dict:
    value = {
        "kind": "homelab-matrix-integration-evidence",
        "contract": integration.CONTRACT,
        "plan_id": plan["plan_id"],
        "identity": {
            "server_name": plan["identity"]["server_name"],
            "signing_key_sha256_before": "a" * 64,
            "signing_key_sha256_after": "a" * 64,
            "unchanged": True,
        },
        "integration": {
            "compose_rollback_copy": True,
            "matrix_loopback": True,
            "element_loopback": True,
            "local_matrix": True,
            "public_matrix": True,
            "public_element": True,
            "well_known_client": True,
            "well_known_server": True,
            "element_config_matches": True,
        },
        "turn": {
            "selected": turn_selected,
            "shared_secret_matches": turn_selected,
            "dns_direct": turn_selected,
            "dns_matches_public_ipv4": turn_selected,
            "local_stun": turn_selected,
            "external_udp_stun": turn_selected,
            "external_tcp_stun": turn_selected,
            "external_relay": turn_selected,
            "real_audio_call": turn_selected,
            "real_video_call": turn_selected,
        },
        "restart": {
            "matrix_healthy": True,
            "element_healthy": True,
            "public_matrix": True,
            "public_element": True,
            "turn_healthy_if_selected": turn_selected,
        },
        "safety": {
            "server_name_changed": False,
            "signing_key_replaced": False,
            "database_migrated": False,
            "federation_changed": False,
            "bridge_changed": False,
            "secrets_disclosed": False,
            "rollback_retained": True,
        },
    }
    value["evidence_id"] = digest(value)
    return value


class MatrixIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.policy = integration.load_policy()
        self.audit = sample_audit()
        self.plan = integration.make_plan(self.policy, self.audit)

    def test_reference_policy_keeps_turn_optional_and_direct(self):
        self.assertTrue(self.policy["turn"]["optional"])
        self.assertFalse(self.policy["network"]["cloudflare_tunnel_supports_turn"])
        self.assertEqual(self.policy["network"]["turn_dns_mode"],
                         "direct-dns-only")

    def test_current_audit_reports_real_blockers_without_false_readiness(self):
        integration.validate_audit(self.audit)
        self.assertTrue(self.plan["matrix_element_ready"])
        self.assertFalse(self.plan["loopback_hardening_ready"])
        self.assertTrue(self.plan["turn_config_ready"])
        self.assertFalse(self.plan["turn_public_ready"])
        self.assertIn("turn-ddns-update-failed", self.plan["blockers"])
        self.assertIn("turn-external-relay-not-proven", self.plan["blockers"])

    def test_plan_is_nonexecuting_and_tamper_evident(self):
        integration.validate_plan(self.plan)
        self.assertFalse(self.plan["production_change_authorized"])
        self.assertFalse(self.plan["changes_performed"])
        changed = copy.deepcopy(self.plan)
        changed["turn_public_ready"] = True
        with self.assertRaises(ConfigError):
            integration.validate_plan(changed)

    def test_selected_turn_requires_external_relay_and_call_proof(self):
        value = completed_evidence(self.plan)
        integration.validate_evidence(value, self.plan)
        changed = copy.deepcopy(value)
        changed["turn"]["external_relay"] = False
        changed.pop("evidence_id")
        changed["evidence_id"] = digest(changed)
        with self.assertRaises(ConfigError):
            integration.validate_evidence(changed, self.plan)

    def test_turn_can_be_explicitly_unselected_without_false_claims(self):
        value = completed_evidence(self.plan, turn_selected=False)
        integration.validate_evidence(value, self.plan)
        changed = copy.deepcopy(value)
        changed["turn"]["local_stun"] = True
        changed.pop("evidence_id")
        changed["evidence_id"] = digest(changed)
        with self.assertRaises(ConfigError):
            integration.validate_evidence(changed, self.plan)

    def test_identity_or_signing_key_change_is_rejected(self):
        value = completed_evidence(self.plan)
        value["identity"]["signing_key_sha256_after"] = "b" * 64
        value.pop("evidence_id")
        value["evidence_id"] = digest(value)
        with self.assertRaises(ConfigError):
            integration.validate_evidence(value, self.plan)

    def test_audit_rejects_runtime_or_secret_drift(self):
        changed = copy.deepcopy(self.audit)
        changed["runtime"]["synapse"]["version"] = "1.0.0"
        changed.pop("audit_id")
        changed["audit_id"] = digest(changed)
        with self.assertRaises(ConfigError):
            integration.validate_audit(changed)
        changed = copy.deepcopy(self.audit)
        changed["turn"]["shared_secret_present"] = False
        changed.pop("audit_id")
        changed["audit_id"] = digest(changed)
        with self.assertRaises(ConfigError):
            integration.validate_audit(changed)

    def test_public_policy_contains_no_secret_value_fields(self):
        text = str(self.policy).casefold()
        for marker in ("turn_shared_secret", "password", "access_token",
                       "registration_shared_secret"):
            self.assertNotIn(marker, text)

    def test_stun_parser_accepts_mapped_address_without_disclosing_it(self):
        transaction = b"t" * 12
        attribute = struct.pack("!HHBBH4s", 0x0020, 8, 0, 1, 0,
                                b"\x00\x00\x00\x00")
        response = struct.pack(
            "!HHI12s", matrix_turn_probe.BINDING_SUCCESS, len(attribute),
            matrix_turn_probe.MAGIC_COOKIE, transaction) + attribute
        self.assertEqual(
            matrix_turn_probe.mapped_family(response, transaction), "ipv4")

    def test_stun_parser_rejects_transaction_mismatch(self):
        response = struct.pack(
            "!HHI12s", matrix_turn_probe.BINDING_SUCCESS, 0,
            matrix_turn_probe.MAGIC_COOKIE, b"x" * 12)
        with self.assertRaises(ValueError):
            matrix_turn_probe.mapped_family(response, b"y" * 12)


if __name__ == "__main__":
    unittest.main()
