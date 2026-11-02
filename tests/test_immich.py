"""Immich protected-original recovery and ML isolation contracts."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from homelab import immich as i
from homelab.config import ConfigError, ROOT
from homelab.privatefs import atomic_json, create_private_directory


class ImmichTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="homelab immich ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.runtime = {"context": "local-test", "endpoint": "unix:///test/docker.sock",
                        "engine_id": "test-engine"}
        self.plan = i.make_plan(self.base / "install", 18060, self.runtime)
        self.credentials = {"database_password": "b" * 64,
                            "admin_password": "a" * 64}

    def test_plan_is_deterministic_private_and_noop(self):
        self.assertEqual(self.plan, i.make_plan(self.base / "install", 18060, self.runtime))
        self.assertEqual(list(self.base.iterdir()), [])
        self.assertEqual(self.plan["access"], "loopback")
        self.assertEqual(self.plan["authoritative_material"],
                         ["postgres-custom-dump", "library", "upload", "profile"])
        self.assertEqual(self.plan["derived_material"],
                         ["thumbs", "encoded-video", "backups"])
        self.assertFalse(self.plan["machine_learning"]["device_access"])

    def test_plan_tampering_and_unsafe_inputs_are_refused(self):
        for field, value in (("images", {}), ("port", 80), ("access", "public"),
                             ("docker_socket", True), ("external_libraries", "host-root")):
            changed = copy.deepcopy(self.plan)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError):
                i.validate_plan(changed)
        for root, port in ((ROOT / "runtime", 18060), (self.base / "$INPUT", 18060),
                           (self.base / "missing/root", 18060),
                           (self.base / "other", True)):
            with self.subTest(root=root), self.assertRaises(ConfigError):
                i.make_plan(root, port, self.runtime)

    def test_compose_protects_originals_and_limits_ml_separately(self):
        spec = i.compose(self.plan, "a" * 32, self.credentials)
        services = spec["services"]
        self.assertEqual(set(services), set(i.SERVICES))
        self.assertEqual(services["immich-server"]["ports"], [{
            "target": 2283, "published": "18060", "host_ip": "127.0.0.1",
            "protocol": "tcp"}])
        for role in ("redis", "database", "immich-machine-learning"):
            self.assertNotIn("ports", services[role])
        self.assertTrue(spec["networks"]["backend"]["internal"])
        self.assertEqual(services["immich-machine-learning"]["mem_limit"], "1536m")
        self.assertEqual(services["immich-machine-learning"]["cpus"], 1.0)
        self.assertEqual(services["immich-machine-learning"]["pids_limit"], 256)
        self.assertEqual(services["immich-machine-learning"]["environment"], i.ML_ENVIRONMENT)
        self.assertNotIn("device_requests", json.dumps(spec).lower())
        self.assertNotIn("docker.sock", json.dumps(spec))
        self.assertNotIn(self.credentials["database_password"], json.dumps(spec))
        self.assertEqual(services["immich-server"]["volumes"][0]["target"], "/data")

    def test_credentials_are_random_strict_and_not_embedded(self):
        first, second = i.new_credentials(), i.new_credentials()
        self.assertNotEqual(first, second)
        self.assertEqual(i.validate_credentials(first), first)
        for changed in ({"database_password": "short", "admin_password": "a" * 64},
                        {**self.credentials, "extra": "x" * 64},
                        {**self.credentials, "admin_password": "a" * 63 + "\n"}):
            with self.assertRaises(ConfigError):
                i.validate_credentials(changed)

    def test_multipart_contains_exact_fixture_without_obsolete_v2_fields(self):
        body, content_type = i._multipart_asset()
        self.assertIn("multipart/form-data; boundary=homelab-", content_type)
        self.assertIn(i.FIXTURE_BODY, body)
        self.assertIn(i.FIXTURE_NAME.encode(), body)
        self.assertNotIn(b"deviceAssetId", body)
        self.assertNotIn(b"deviceId", body)

    def test_fixture_evidence_requires_exact_original_download(self):
        response = MagicMock()
        response.status = 200
        response.read.return_value = i.FIXTURE_BODY
        response.headers.get_content_type.return_value = "image/png"
        response.__enter__.return_value = response
        with patch.object(i, "_login", return_value="token"), \
                patch.object(i.urllib.request, "urlopen", return_value=response):
            evidence = i._fixture_evidence(self.plan, self.credentials, "asset-id")
        self.assertEqual(evidence["sha256"], hashlib.sha256(i.FIXTURE_BODY).hexdigest())
        self.assertTrue(evidence["original_verified"])
        response.read.return_value = b"changed"
        with patch.object(i, "_login", return_value="token"), \
                patch.object(i.urllib.request, "urlopen", return_value=response), \
                self.assertRaises(ConfigError):
            i._fixture_evidence(self.plan, self.credentials, "asset-id")

    def test_restore_is_scoped_and_excludes_derived_and_ml_cache(self):
        backup = self.base / "backup"
        (backup / "filesystem").mkdir(parents=True)
        (backup / "system-markers").mkdir()
        for name in i.AUTHORITATIVE_AREAS:
            (backup / "filesystem" / name).mkdir()
        for name in i.DERIVED_AREAS:
            (backup / "system-markers" / name).mkdir()
            (backup / "system-markers" / name / i.SYSTEM_MARKER).write_text(
                "fixture\n", encoding="utf-8")
        (backup / "immich-postgres.dump").write_bytes(b"PGDMP")
        (Path(self.plan["root"]) / "media").mkdir(parents=True)
        with patch.object(i, "docker") as docker:
            i._restore_database(self.plan, backup, "database-id")
        calls = [call.args[0] for call in docker.call_args_list]
        self.assertEqual(calls[0][0], "cp")
        self.assertIn("pg_restore", calls[1])
        self.assertIn("--clean", calls[1])
        self.assertIn("--no-owner", calls[1])
        with patch.object(i, "docker") as docker:
            i._restore_files(self.plan, backup, "server-id")
        targets = [call.args[0][-1] for call in docker.call_args_list]
        self.assertEqual(len(targets), len(i.AUTHORITATIVE_AREAS))
        self.assertFalse(any("/cache" in target for target in targets))
        for name in i.DERIVED_AREAS:
            marker = Path(self.plan["root"]) / "media" / name / i.SYSTEM_MARKER
            self.assertEqual(marker.read_text(encoding="utf-8"), "fixture\n")

    def test_confirmation_precedes_runtime_or_mutation(self):
        with patch.object(i, "local_runtime") as runtime, self.assertRaises(ConfigError):
            i.operate(self.plan, "stop", "wrong")
        runtime.assert_not_called()
        with patch.object(i, "local_runtime") as runtime, self.assertRaises(ConfigError):
            i.exercise(self.plan, "wrong")
        runtime.assert_not_called()
        with patch.object(i, "local_runtime") as runtime, self.assertRaises(ConfigError):
            i.backup(self.plan, self.base / "backup", "wrong")
        runtime.assert_not_called()


class ImmichBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="homelab immich backup ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "snapshot"
        create_private_directory(self.root)
        create_private_directory(self.root / "filesystem")
        for name in i.AUTHORITATIVE_AREAS:
            create_private_directory(self.root / "filesystem" / name)
            (self.root / "filesystem" / name / ".immich").write_text(
                "fixture\n", encoding="utf-8")
        original = self.root / "filesystem/upload/user/asset.png"
        original.parent.mkdir(parents=True)
        original.write_bytes(i.FIXTURE_BODY)
        i.tree_files(self.root / "filesystem", protect_new=True)
        create_private_directory(self.root / "system-markers")
        for name in i.DERIVED_AREAS:
            create_private_directory(self.root / "system-markers" / name)
            (self.root / "system-markers" / name / i.SYSTEM_MARKER).write_text(
                "fixture\n", encoding="utf-8")
        i.tree_files(self.root / "system-markers", protect_new=True)
        (self.root / "immich-postgres.dump").write_bytes(b"PGDMP-synthetic")
        self.credentials = {"database_password": "1" * 64,
                            "admin_password": "2" * 64}
        atomic_json(self.root / "credentials.json", self.credentials)
        atomic_json(self.root / "fixture.json", {"asset_id": "asset-id"})
        for name, content in (("compose.private.json", '{"services":{}}\n'),
                              ("sanitized-config.json", '{"kind":"fixture"}\n')):
            path = self.root / name
            path.write_text(content, encoding="utf-8")
            if i.os.name == "nt":
                i.windows_acl(path, create=True)
            else:
                path.chmod(0o600)
        for path in (self.root / "immich-postgres.dump", self.root / "fixture.json"):
            if i.os.name == "nt":
                i.windows_acl(path, create=True)
            else:
                path.chmod(0o600)
        trees = {name: i.tree_files(self.root / "filesystem" / name)
                 for name in i.AUTHORITATIVE_AREAS}
        file_inventory = []
        for area, values in trees.items():
            for relative, sha256 in values.items():
                path = self.root / "filesystem" / area / relative
                file_inventory.append({"path": f"{area}/{relative}",
                                       "bytes": path.stat().st_size,
                                       "sha256": sha256})
        fixture = {"asset_id": "asset-id", "filename": i.FIXTURE_NAME,
                   "bytes": len(i.FIXTURE_BODY),
                   "sha256": hashlib.sha256(i.FIXTURE_BODY).hexdigest(),
                   "content_type": "image/png", "original_verified": True}
        self.manifest = {
            "kind": "immich-consistent-backup-v1",
            "created_utc": "2026-11-02T00:00:00+00:00", "images": i.images(),
            "method": "quiesced-postgres-protected-originals",
            "authoritative_material": ["postgres-custom-dump", *i.AUTHORITATIVE_AREAS],
            "derived_material": list(i.DERIVED_AREAS),
            "cache_material": ["redis-data", "model-cache"],
            "system_markers": {
                name: i.file_hash(self.root / "system-markers" / name / i.SYSTEM_MARKER)
                for name in i.DERIVED_AREAS
            },
            "consistency": {"server_quiesced": True, "ml_quiesced": True,
                            "postgres_archive_readable": True,
                            "protected_originals_complete": True},
            "recovery_status": "pending-independent-restore",
            "credentials_hash": i.digest(self.credentials),
            "configuration_sha256": {
                "private": i.file_hash(self.root / "compose.private.json"),
                "sanitized": i.file_hash(self.root / "sanitized-config.json")},
            "database_sha256": i.file_hash(self.root / "immich-postgres.dump"),
            "trees": trees, "file_inventory": file_inventory,
            "fixture": fixture, "summary": None,
        }
        self.manifest["summary"] = i.backup_summary(self.manifest)
        atomic_json(self.root / "manifest.json", self.manifest)

    def test_backup_evidence_and_recovery_plan(self):
        manifest = i.verify_backup(self.root)
        self.assertFalse(manifest["summary"]["derived_included"])
        self.assertFalse(manifest["summary"]["ml_cache_included"])
        runtime = {"context": "test", "endpoint": "unix:///test/docker.sock",
                   "engine_id": "test"}
        plan = i.make_plan(self.root.parent / "restore", 18061, runtime, self.root)
        self.assertEqual(plan["recovery"]["method"],
                         "quiesced-postgres-protected-originals")

    def test_changed_original_database_or_manifest_is_refused(self):
        cases = (self.root / "filesystem/upload/user/asset.png",
                 self.root / "immich-postgres.dump")
        for path in cases:
            original = path.read_bytes()
            path.write_bytes(original + b"changed")
            with self.subTest(path=path), self.assertRaises(ConfigError):
                i.verify_backup(self.root)
            path.write_bytes(original)
        changed = copy.deepcopy(self.manifest)
        changed["derived_material"] = []
        atomic_json(self.root / "manifest.json", changed, replace=True)
        with self.assertRaises(ConfigError):
            i.verify_backup(self.root)


if __name__ == "__main__":
    unittest.main()
