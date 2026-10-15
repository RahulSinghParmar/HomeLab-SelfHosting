"""Reusable Glance collector tests; no live Docker, network, or services."""

import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from homelab import glance_collectors as c
from homelab.config import ConfigError, ROOT


class GlanceCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="homelab glance collector ")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        for name in ("storage", "backups"):
            (self.base / name).mkdir()
        self.config = {
            "kind": "homelab-glance-collector", "schema_version": 1,
            "output_dir": str(self.base / "snapshots"),
            "docker": {"enabled": True, "include": [
                {"id": "dashboard", "label": "Dashboard", "container": "private-dashboard-container"}]},
            "storage": [{"id": "system", "label": "System", "path": str(self.base / "storage"),
                         "warning_free_percent": 15}],
            "backups": [{"id": "dashboard", "label": "Dashboard backup", "path": str(self.base / "backups"),
                         "pattern": "*.zip", "max_age_hours": 48}],
            "endpoints": [{"id": "dashboard", "label": "Dashboard", "url": "http://127.0.0.1:18081/healthz",
                           "accepted_status": [200], "timeout_seconds": 5, "check_tls": False}],
            "windows_services": [{"id": "agent", "label": "Host agent", "name": "BeszelAgent"}],
        }

    def test_valid_config_and_public_summary_redact_private_values(self):
        validated = c.validate_config(self.config)
        public = json.dumps(c.public_config(validated))
        for private in (str(self.base), "127.0.0.1", "private-dashboard-container"):
            self.assertNotIn(private, public)
        self.assertIn("Dashboard", public)

    def test_credentials_remote_context_and_overlap_are_refused(self):
        changed = copy.deepcopy(self.config)
        changed["endpoints"][0]["url"] = "https://" + "user:password@" + "example.invalid/"
        with self.assertRaises(ConfigError):
            c.validate_config(changed)
        changed = copy.deepcopy(self.config)
        changed["output_dir"] = str(self.base / "storage" / "snapshots")
        with self.assertRaises(ConfigError):
            c.validate_config(changed)
        with patch.object(c, "run", side_effect=["remote", json.dumps("ssh://example.invalid")]), self.assertRaises(ConfigError):
            c.docker_snapshot(self.config["docker"])

    def test_windows_service_state_parser_uses_numeric_state(self):
        localized = "TIPO               : 10  WIN32_OWN_PROCESS\nESTADO             : 4  EN_EJECUCION"
        self.assertEqual(c.parse_windows_service_state(localized), "running")
        with self.assertRaises(ConfigError):
            c.parse_windows_service_state("no service state present")

    def test_command_failure_never_echoes_raw_output(self):
        result = subprocess.CompletedProcess([], 1, "private-value", "secret-value")
        with patch.object(c.subprocess, "run", return_value=result), self.assertRaises(ConfigError) as raised:
            c.run(["example"])
        self.assertNotIn("private-value", str(raised.exception))
        self.assertNotIn("secret-value", str(raised.exception))

    def test_collect_writes_only_bounded_snapshots(self):
        fixtures = {
            "host": {"status": "ok", "platform": "windows", "metrics_available": True,
                     "cpu_count": 8, "cpu_percent": 10.0,
                     "memory_total_gib": 32.0, "memory_used_gib": 8.0, "memory_percent": 25.0},
            "docker": {"status": "ok", "selected": [{"id": "dashboard", "label": "Dashboard", "status": "ok",
                                                        "state": "running", "health": "healthy", "restarts": 0, "oom": False}],
                       "running": 1, "attention": 0},
            "volumes": [{"id": "system", "label": "System", "status": "ok", "total_gib": 100.0,
                         "free_gib": 50.0, "used_percent": 50.0}],
            "backups": [{"id": "dashboard", "label": "Dashboard backup", "status": "ok", "age_hours": 1.0,
                         "artifact_count": 1}],
            "endpoints": [{"id": "dashboard", "label": "Dashboard", "status": "ok", "http_status": 200, "latency_ms": 3}],
            "certificates": [],
            "services": [{"id": "agent", "label": "Host agent", "status": "ok", "state": "running"}],
        }
        with patch.object(c, "host_snapshot", return_value=fixtures["host"]), \
             patch.object(c, "docker_snapshot", return_value=fixtures["docker"]), \
             patch.object(c, "storage_snapshot", return_value=fixtures["volumes"]), \
             patch.object(c, "backup_snapshot", return_value=fixtures["backups"]), \
             patch.object(c, "endpoint_snapshot", return_value=(fixtures["endpoints"], fixtures["certificates"])), \
             patch.object(c, "windows_service_snapshot", return_value=fixtures["services"]):
            result = c.collect(self.config)
        self.assertEqual(result["status"], "ok")
        output = Path(self.config["output_dir"])
        self.assertEqual({path.name for path in output.glob("*.json")},
                         {"overview.json", "resources.json", "storage.json", "services.json", "security.json"})
        combined = "".join(path.read_text(encoding="utf-8") for path in output.glob("*.json"))
        self.assertNotIn(str(self.base), combined)
        self.assertNotIn("127.0.0.1", combined)

    def test_metrics_server_rejects_missing_invalid_and_marks_stale(self):
        source = ROOT / "modules/glance/collector/metrics_server.py"
        spec = importlib.util.spec_from_file_location("test_glance_metrics_server", source)
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        server.DATA = self.base
        self.assertEqual(server.snapshot("overview")[0], 503)
        (self.base / "overview.json").write_text("{}", encoding="utf-8")
        self.assertEqual(server.snapshot("overview")[0], 503)
        old = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
        (self.base / "overview.json").write_text(json.dumps({"schema_version": 1, "generated_at": old, "status": "ok"}), encoding="utf-8")
        status, value = server.snapshot("overview")
        self.assertEqual(status, 200)
        self.assertTrue(value["stale"])
        self.assertEqual(value["status"], "stale")


if __name__ == "__main__":
    unittest.main()
