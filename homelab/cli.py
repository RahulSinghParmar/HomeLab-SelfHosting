"""Application planning and separately gated synthetic-only execution."""

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
    parser = argparse.ArgumentParser(prog="homelab", description="Plan applications; execute only the isolated synthetic sandbox.")
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
    sandbox = sub.add_parser("sandbox", help="Synthetic local files only; no Docker or real applications")
    actions = sandbox.add_subparsers(dest="action", required=True)
    proposal = actions.add_parser("plan", help="Propose dedicated synthetic storage; save private plan")
    for name in ("root", "data-root", "backup-root", "output"):
        proposal.add_argument("--" + name, type=Path, required=True)
    for verb in ("apply", "status", "retire"):
        action = actions.add_parser(verb)
        action.add_argument("--plan", type=Path, required=True)
        if verb != "status":
            action.add_argument("--confirm", required=True, help="Exact full plan ID from the reviewed plan")
    args = parser.parse_args(arguments)
    try:
        if args.command == "sandbox":
            from . import sandbox as engine
            if args.action == "plan":
                result = engine.make_plan(args.root, args.data_root, args.backup_root)
                # The plan itself must not occupy future runtime storage.
                destination = args.output.resolve()
                need_outside = all(not destination.is_relative_to(Path(value)) for value in result['paths'].values())
                if not need_outside:
                    raise ConfigError("Plan output must be outside all proposed storage roots")
                write_private(args.output, result)
                result = engine.public_plan(result)
            else:
                reviewed = engine.validate_plan(load_json(args.plan))
                result = (engine.status(reviewed) if args.action == "status" else
                          getattr(engine, args.action)(reviewed, args.confirm))
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
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
        print("ERROR: Input, host evidence or private state could not be processed safely. Sandbox work may be incomplete; retain files and inspect before retrying.", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("Cancelled. Retain any sandbox files and retry only with the same reviewed plan.", file=sys.stderr)
        return 130
