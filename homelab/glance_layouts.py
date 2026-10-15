"""Deterministic assembly and validation for reusable Glance layouts."""

from __future__ import annotations

import json
from pathlib import Path
import re

from .config import ROOT, ConfigError, canonical, keys, load_json, need
from .io import write_private
from .sandbox import digest


LAYOUTS = ROOT / "modules/glance/layouts"
PROFILE = re.compile(r"[a-z][a-z0-9-]{0,31}\Z")
WIDGETS = {"bookmarks", "clock", "custom-api", "html", "markets", "releases", "rss", "split-column"}


def profiles() -> list[str]:
    return sorted(path.name for path in LAYOUTS.iterdir()
                  if path.is_dir() and PROFILE.fullmatch(path.name) and (path / "manifest.json").is_file())


def validate_widget(widget: object) -> None:
    need(isinstance(widget, dict) and isinstance(widget.get("type"), str), "Every layout widget requires a type")
    need(widget["type"] in WIDGETS, "Layout contains an unsupported widget type")
    if "title" in widget:
        need(isinstance(widget["title"], str) and 0 < len(widget["title"]) <= 100, "Widget title is invalid")
    if widget["type"] == "custom-api":
        need(isinstance(widget.get("url"), str) and widget["url"].startswith("http://metrics:8765/v1/"),
             "Reusable custom API widgets may only query the internal metrics service")
        need(isinstance(widget.get("template"), str) and 0 < len(widget["template"]) <= 20_000,
             "Custom API widget template is invalid")
    if widget["type"] == "split-column":
        need(isinstance(widget.get("widgets"), list) and 1 <= len(widget["widgets"]) <= 4,
             "Split-column widget requires one to four children")
        for child in widget["widgets"]:
            validate_widget(child)


def validate_page(page: object) -> None:
    need(isinstance(page, dict), "Layout page must be an object")
    need(set(page) <= {"name", "slug", "head-widgets", "columns", "show-mobile-header"}
         and {"name", "slug", "columns"} <= set(page), "Layout page contains missing or unexpected fields")
    need(isinstance(page["name"], str) and 0 < len(page["name"]) <= 50, "Layout page name is invalid")
    need(isinstance(page["slug"], str) and PROFILE.fullmatch(page["slug"]), "Layout page slug is invalid")
    need(isinstance(page["columns"], list) and 1 <= len(page["columns"]) <= 3, "Layout page must contain one to three columns")
    for column in page["columns"]:
        keys(column, {"size", "widgets"}, "layout column")
        need(column["size"] in ("small", "full"), "Layout column size is invalid")
        need(isinstance(column["widgets"], list) and 1 <= len(column["widgets"]) <= 30,
             "Layout column widget count is invalid")
        for widget in column["widgets"]:
            validate_widget(widget)


def load_profile(name: str) -> dict:
    need(isinstance(name, str) and PROFILE.fullmatch(name) and name in profiles(), "Unknown Glance layout profile")
    root = LAYOUTS / name
    manifest = load_json(root / "manifest.json")
    keys(manifest, {"kind", "schema_version", "name", "description", "theme", "pages", "required_snapshots"}, "layout manifest")
    need(manifest["kind"] == "homelab-glance-layout" and manifest["schema_version"] == 1
         and manifest["name"] == name, "Unsupported Glance layout manifest")
    need(isinstance(manifest["description"], str) and bool(manifest["description"]), "Layout description is required")
    need(isinstance(manifest["theme"], dict) and bool(manifest["theme"]), "Layout theme is required")
    need(isinstance(manifest["pages"], list) and 1 <= len(manifest["pages"]) <= 20
         and len(manifest["pages"]) == len(set(manifest["pages"])), "Layout page manifest is invalid")
    need(manifest["required_snapshots"] == ["overview", "resources", "security", "services", "storage"],
         "Layout snapshot contract is invalid")
    pages = []
    for filename in manifest["pages"]:
        need(isinstance(filename, str) and re.fullmatch(r"[a-z0-9-]+\.json", filename), "Layout page filename is invalid")
        page = load_json(root / "pages" / filename)
        validate_page(page)
        pages.append(page)
    slugs = [page["slug"] for page in pages]
    need(len(slugs) == len(set(slugs)), "Layout page slugs must be unique")
    dashboard = {"server": {"port": 8080}, "theme": manifest["theme"], "pages": pages}
    serialized = canonical(dashboard)
    for prohibited in ("parmar.homes", "@gmail.com", "@protonmail.com", "C:\\\\Docker", "${"):
        need(prohibited not in serialized, "Reusable layout contains a private or unresolved value")
    return dashboard


def summary(name: str) -> dict:
    dashboard = load_profile(name)
    widgets = []
    for page in dashboard["pages"]:
        widgets.extend(widget["type"] for column in page["columns"] for widget in column["widgets"])
    return {"profile": name, "page_count": len(dashboard["pages"]), "page_slugs": [page["slug"] for page in dashboard["pages"]],
            "top_level_widget_count": len(widgets), "widget_types": sorted(set(widgets)),
            "sha256": digest(dashboard), "private_values": False}


def render(name: str, output: Path) -> dict:
    dashboard = load_profile(name)
    write_private(output, dashboard)
    return {**summary(name), "rendered": True, "output": "<private-output>"}
