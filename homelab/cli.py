"""Command-line interface for non-deploying homelab planning."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, catalogs, load_json, validate_config
from .doctor import diagnose
from .io import write_private
from .planner import create_plan
from .wizard import configure


def display(value: dict, json_output: bool) -> None:
    if json_output:
        print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True))
        return
    if value.get("kind") == "homelab-doctor":
        print("Doctor: " + value["status"] + " - deployment disabled")
        for check in value["checks"]:
            print(f"[{check['status'].upper()}] {check['name']}: {check['detail']}")
        return
    print("Review plan " + value["plan_id"][:16] + " - NO DEPLOYMENT")
    print("Services: " + ", ".join(row["id"] for row in value["services"]))
    print(f"Provisional allowance: {value['resources']['allowance_memory_mib']} MiB / {value['resources']['allowance_cpu_millicores'] / 1000:g} CPUs")
    print("Storage values redacted; configuration and catalog hashes bind this review to its inputs.")
    for port in value["ports"]:
        extent = str(port["first"]) if port["first"] == port["last"] else f"{port['first']}-{port['last']}"
        print(f"Proposed {port['key']}: {port['bind']}:{extent}/{port['protocol']}")
    for issue in value["issues"]:
        print("[BLOCK] " + issue["detail"])
    for warning in value["warnings"]:
        print("[REVIEW] " + warning)
    if "host_report" in value:
        display(value["host_report"], False)
    else:
        print("Host not checked. Use doctor --config or plan --check-host for live read-only checks.")


def main(arguments=None) -> int:
    parser = argparse.ArgumentParser(prog="homelab", description="Select, check and plan. No deployment commands are implemented.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("catalog", help="List all selectable, not-yet-deployable modules")
    listing.add_argument("--json", action="store_true")
    wizard = sub.add_parser("configure", help="Save settings through wizard or validated file input")
    wizard.add_argument("--output", type=Path, required=True)
    wizard.add_argument("--from", dest="source", type=Path, help="Validate/copy a settings example instead of running the wizard")
    validate = sub.add_parser("validate", help="Validate settings without probing the host")
    validate.add_argument("--config", type=Path, required=True)
    doctor = sub.add_parser("doctor", help="Read-only prerequisite checks, optionally against settings")
    doctor.add_argument("--config", type=Path)
    plan = sub.add_parser("plan", help="Create an offline deterministic review plan")
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--check-host", action="store_true", help="Attach a separate changing, read-only host report")
    for command in (doctor, plan):
        command.add_argument("--json", action="store_true")
        command.add_argument("--output", type=Path, help="Save redacted report outside Git; never overwrite")
    args = parser.parse_args(arguments)
    try:
        modules, planning = catalogs()
        if args.command == "catalog":
            rows = [{"id": key, "name": value["name"], "kind": value["kind"], "status": value["status"]} for key, value in sorted(modules.items())]
            if args.json:
                print(json.dumps(rows, indent=2))
            else:
                for row in rows:
                    print(f"{row['id']:20} {row['kind']:8} not yet deployable")
            return 0
        if args.command == "configure":
            config = validate_config(load_json(args.source), modules, planning) if args.source else configure(modules, planning)
            if config is None:
                print("Cancelled. Nothing saved or deployed.")
                return 0
            write_private(args.output, config)
            print("Private settings saved to the requested file. Review with plan; no deployment occurred.")
            return 0
        config = validate_config(load_json(args.config), modules, planning) if args.config else None
        if args.command == "validate":
            print("Settings schema valid. Host resources and deployment support are not verified.")
            return 0
        result = diagnose(config, modules, planning) if args.command == "doctor" else create_plan(config, modules, planning)
        if args.command == "plan" and args.check_host:
            result["host_report"] = diagnose(config, modules, planning)
        if args.output:
            write_private(args.output, result)
        display(result, args.json)
        blocked = result.get("status") == "blocked" or bool(result.get("issues")) or result.get("host_report", {}).get("status") == "blocked"
        return 2 if blocked else 0
    except ConfigError as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError):
        print("ERROR: Input or host evidence could not be interpreted safely; no deployment performed.", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("Cancelled. No deployment performed.", file=sys.stderr)
        return 130
