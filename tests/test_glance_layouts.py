"""Reusable Glance layout assembly tests."""

import json
from pathlib import Path
import tempfile
import unittest

from homelab import glance_layouts as layouts
from homelab.config import ConfigError


class GlanceLayoutTests(unittest.TestCase):
    def test_operations_profile_is_complete_and_private(self):
        dashboard = layouts.load_profile("operations")
        self.assertEqual(len(dashboard["pages"]), 7)
        self.assertEqual(dashboard["pages"][0]["slug"], "home")
        serialized = json.dumps(dashboard)
        for private in ("parmar.homes", "@gmail.com", "@protonmail.com", "C:\\Docker", "${"):
            self.assertNotIn(private, serialized)
        self.assertNotIn("docker.sock", serialized)

    def test_custom_api_widgets_are_internal_only(self):
        dashboard = layouts.load_profile("operations")

        def walk(widget):
            yield widget
            for child in widget.get("widgets", []):
                yield from walk(child)

        widgets = [nested for page in dashboard["pages"] for column in page["columns"]
                   for widget in column["widgets"] for nested in walk(widget)]
        custom = [widget for widget in widgets if widget["type"] == "custom-api"]
        self.assertGreaterEqual(len(custom), 10)
        self.assertTrue(all(widget["url"].startswith("http://metrics:8765/v1/") for widget in custom))

    def test_summary_is_deterministic_and_unknown_profile_refused(self):
        self.assertEqual(layouts.summary("operations"), layouts.summary("operations"))
        with self.assertRaises(ConfigError):
            layouts.load_profile("unknown")

    def test_render_is_no_overwrite_and_outside_repository(self):
        with tempfile.TemporaryDirectory(prefix="homelab glance layout ") as temporary:
            output = Path(temporary).resolve() / "glance.json"
            result = layouts.render("operations", output)
            self.assertTrue(result["rendered"])
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), layouts.load_profile("operations"))
            with self.assertRaises(ConfigError):
                layouts.render("operations", output)

    def test_compose_example_has_no_socket_or_metrics_port(self):
        source = (layouts.LAYOUTS.parent / "operations.compose.yml").read_text(encoding="utf-8")
        self.assertNotIn("docker.sock", source)
        self.assertIn("host_ip: 127.0.0.1", source)
        self.assertIn("read_only: true", source)
        self.assertIn("no-new-privileges:true", source)
        self.assertEqual(source.count("published:"), 1)


if __name__ == "__main__":
    unittest.main()
