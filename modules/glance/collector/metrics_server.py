"""Read-only snapshot server for the reusable Glance operations layout."""

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import urllib.parse


DATA = Path(os.getenv("GLANCE_SNAPSHOT_DIR", "/data"))
PORT = int(os.getenv("GLANCE_METRICS_PORT", "8765"))
MAX_AGE_SECONDS = int(os.getenv("GLANCE_MAX_SNAPSHOT_AGE", "300"))
MAX_BYTES = 1024 * 1024
ROUTES = {f"/v1/{name}": name for name in ("overview", "resources", "storage", "services", "security")}


def unavailable(name, reason):
    return {"schema_version": 1, "generated_at": None, "status": "unavailable", "snapshot": name, "reason": reason}


def snapshot(name):
    path = DATA / f"{name}.json"
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return 503, unavailable(name, "missing-or-invalid")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            return 503, unavailable(name, "schema-invalid")
        stamp = datetime.fromisoformat(str(value["generated_at"]).replace("Z", "+00:00"))
        age = max(0, int((datetime.now(timezone.utc) - stamp).total_seconds()))
        result = dict(value)
        result["age_seconds"] = age
        result["stale"] = age > MAX_AGE_SECONDS
        if result["stale"] and result.get("status") == "ok":
            result["status"] = "stale"
        return 200, result
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return 503, unavailable(name, "unreadable")


class Handler(BaseHTTPRequestHandler):
    server_version = "HomeLabGlanceMetrics/1"

    def send_json(self, status, value):
        body = json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        route = urllib.parse.urlsplit(self.path).path
        if route == "/healthz":
            available = sum(snapshot(name)[0] == 200 for name in ROUTES.values())
            self.send_json(200, {"status": "ok", "available_snapshots": available, "expected_snapshots": len(ROUTES)})
            return
        name = ROUTES.get(route)
        if name is None:
            self.send_json(404, {"status": "not-found"})
            return
        self.send_json(*snapshot(name))

    def do_HEAD(self):
        self.do_GET()

    def log_message(self, format, *arguments):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
