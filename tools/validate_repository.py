"""Validate public design fixtures. Never contacts Docker or changes host state."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def fields(value: object, expected: set[str], where: str) -> None:
    require(isinstance(value, dict), f"{where}: expected object")
    require(set(value) == expected, f"{where}: missing or unexpected fields")


def strings(value: object, where: str, *, empty: bool = False) -> None:
    require(isinstance(value, list), f"{where}: expected list")
    require(empty or bool(value), f"{where}: must not be empty")
    require(all(isinstance(v, str) and bool(v.strip()) for v in value),
            f"{where}: expected nonempty strings")
    require(len(value) == len(set(value)), f"{where}: duplicate entries")


def validate_catalog(catalog: object) -> set[str]:
    fields(catalog, {"schema_version", "release", "inventory_date", "modules"}, "catalog")
    require(type(catalog["schema_version"]) is int and catalog["schema_version"] == 1,
            "catalog: unsupported schema")
    require(catalog["release"] == "0.1.0", "catalog: update validation contract for a new release")
    require(isinstance(catalog["inventory_date"], str), "catalog: expected ISO date string")
    date.fromisoformat(catalog["inventory_date"])
    modules = catalog["modules"]
    require(isinstance(modules, list) and bool(modules), "catalog: modules required")
    ids: set[str] = set()
    by_id = {}
    for module in modules:
        fields(module, {"id", "name", "kind", "phase", "status", "dependencies",
                        "components", "state", "upstream"}, "module")
        key = module["id"]
        require(isinstance(key, str) and bool(ID_PATTERN.fullmatch(key)), "invalid module ID")
        require(key not in ids, f"duplicate module: {key}")
        ids.add(key)
        by_id[key] = module
        require(isinstance(module["name"], str) and bool(module["name"].strip()), f"{key}: name required")
        require(module["kind"] in ("compose", "native", "hybrid", "adapter"), f"{key}: invalid kind")
        require(type(module["phase"]) is int and 4 <= module["phase"] <= 8, f"{key}: invalid phase")
        require(module["status"] == "planned", f"{key}: foundation cannot claim implemented support")
        strings(module["dependencies"], f"{key} dependencies", empty=True)
        strings(module["components"], f"{key} components")
        strings(module["state"], f"{key} state")
        upstream = module["upstream"]
        require(upstream is None or isinstance(upstream, str), f"{key}: invalid upstream")
        if upstream is not None:
            parsed = urlsplit(upstream)
            require(parsed.scheme == "https" and bool(parsed.hostname)
                    and not parsed.username and not parsed.password, f"{key}: HTTPS upstream required")
    for key, module in by_id.items():
        require(set(module["dependencies"]) <= ids, f"{key}: unknown dependency")
        require(key not in module["dependencies"], f"{key}: self dependency")
    visiting: set[str] = set()
    complete: set[str] = set()

    def visit(key: str) -> None:
        require(key not in visiting, f"dependency cycle at {key}")
        if key in complete:
            return
        visiting.add(key)
        for dependency in by_id[key]["dependencies"]:
            visit(dependency)
        visiting.remove(key)
        complete.add(key)

    for key in by_id:
        visit(key)
    return ids


def validate_example(plan: object, ids: set[str]) -> None:
    fields(plan, {"schema_version", "example_only", "installation_id", "platform",
                  "architecture", "mode", "access", "services", "paths", "database_storage",
                  "resource_budget", "gpu", "public_domain", "secret_bundle", "retention"}, "plan")
    require(type(plan["schema_version"]) is int and plan["schema_version"] == 1, "plan: unsupported schema")
    require(plan["example_only"] is True, "plan must be marked example only")
    require(plan["installation_id"] == "example-lab", "example installation identity required")
    require(plan["platform"] in ("windows", "linux", "macos"), "unsupported example platform")
    require(plan["architecture"] in ("amd64", "arm64"), "invalid example architecture")
    require(plan["mode"] == "fresh" and plan["access"] == "loopback", "examples must be fresh and private")
    strings(plan["services"], "selected services")
    require(set(plan["services"]) <= ids, "unknown selected service")
    fields(plan["paths"], {"installation_root", "media_root", "backup_root"}, "paths")
    path_type = PureWindowsPath if plan["platform"] == "windows" else PurePosixPath
    paths = []
    for name, value in plan["paths"].items():
        require(isinstance(value, str) and bool(value.strip()), f"{name}: path required")
        path = path_type(value)
        require(path.is_absolute() and len(path.parts) > 1 and ".." not in path.parts,
                f"{name}: absolute non-root path without traversal required")
        paths.append(path)
    for index, path in enumerate(paths):
        for other in paths[index + 1:]:
            require(not path.is_relative_to(other) and not other.is_relative_to(path),
                    "installation, media and backup paths must not overlap")
    require(plan["database_storage"] == "docker-named-volumes", "unexpected example database policy")
    fields(plan["resource_budget"], {"cpu_limit", "memory_gib", "reserve_host_gib"}, "budget")
    require(all(type(v) is int and v > 0 for v in plan["resource_budget"].values()), "invalid resource budget")
    require(plan["gpu"] == "disabled" and plan["public_domain"] is None,
            "examples must not enable GPU or public exposure")
    require(plan["secret_bundle"] == "external-encrypted-bundle-required", "invalid secret reference")
    fields(plan["retention"], {"daily", "weekly", "monthly"}, "retention")
    require(all(type(v) is int and v > 0 for v in plan["retention"].values()), "invalid retention")


def read_json(path: Path) -> object:
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)


def validate_links(root: Path) -> int:
    documents = list(root.glob("*.md")) + list((root / "docs").rglob("*.md"))
    for document in documents:
        content = document.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            relative = unquote(target.split("#", 1)[0])
            resolved = (document.parent / relative).resolve()
            require(resolved.is_relative_to(root.resolve()), f"link leaves repository: {document.name}")
            require(resolved.exists(), f"broken local link: {document.name} -> {target}")
    return len(documents)


def validate_repository(root: Path = ROOT) -> str:
    ids = validate_catalog(read_json(root / "catalog" / "services.json"))
    examples = sorted((root / "examples").glob("*.plan.example.json"))
    require(len(examples) == 3, "expected three platform design examples")
    platforms = set()
    for example in examples:
        plan = read_json(example)
        validate_example(plan, ids)
        platforms.add(plan["platform"])
    require(platforms == {"windows", "linux", "macos"}, "missing platform design example")
    docs = validate_links(root)
    return f"PASS: {len(ids)} planned modules, {len(examples)} design examples, {docs} documents. No deployment performed."


def main() -> int:
    try:
        print(validate_repository())
        return 0
    except (ValueError, OSError, TypeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
