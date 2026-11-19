"""Secret-safe native Windows lifecycle, Glances and reboot-recovery audit."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path, PureWindowsPath

from .config import ROOT, canonical, keys, load_json, need
from .sandbox import digest


CONTRACT = "phase7-native-lifecycle-v1"
POLICY = ROOT / "modules/native-lifecycle/windows.example.json"
TASK_RESULT_RUNNING = 267009
TRIGGER_CLASSES = {
    "MSFT_TaskLogonTrigger": "logon",
    "MSFT_TaskDailyTrigger": "daily",
    "MSFT_TaskWeeklyTrigger": "weekly",
    "MSFT_TaskTimeTrigger": "time",
    "MSFT_TaskBootTrigger": "boot",
}


def _windows_relative(value: str) -> Path:
    path = PureWindowsPath(value)
    need(not path.is_absolute() and ".." not in path.parts and len(path.parts) > 1,
         "Native lifecycle relative path is unsafe")
    return Path(*path.parts)


def validate_policy(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "root", "glances", "samples",
                 "services", "startup", "tasks", "recovery"},
         "Native lifecycle policy")
    need(value["kind"] == "homelab-native-lifecycle-policy"
         and value["contract"] == CONTRACT,
         "Unsupported native lifecycle policy")
    need(value["platform"] == "windows-interactive-docker-desktop",
         "Only the reviewed interactive Windows host is supported")
    need(isinstance(value["root"], str)
         and bool(re.fullmatch(r"[A-Za-z]:\\[^\x00]+", value["root"])),
         "Native lifecycle root must be an absolute Windows path")

    glances = value["glances"]
    keys(glances, {"version", "status_url", "all_url", "ui_url", "listener",
                   "task", "start_script", "configuration", "required_flags"},
         "Glances policy")
    need(bool(re.fullmatch(r"\d+\.\d+\.\d+", glances["version"])),
         "Glances version must be exact")
    need(glances["listener"] == "127.0.0.1:61208"
         and all(glances[name].startswith("http://127.0.0.1:61208/glances/")
                 for name in ("status_url", "all_url", "ui_url")),
         "Glances must remain loopback-only below /glances")
    _windows_relative(glances["start_script"])
    _windows_relative(glances["configuration"])
    need(isinstance(glances["required_flags"], list)
         and len(glances["required_flags"]) == len(set(glances["required_flags"]))
         and all(isinstance(item, str) and item.startswith("--")
                 for item in glances["required_flags"]),
         "Glances privacy flags are invalid")

    need(isinstance(value["samples"], list) and len(value["samples"]) == 5,
         "Native sample policy is incomplete")
    sample_names = set()
    for row in value["samples"]:
        keys(row, {"name", "max_age_seconds"}, "Native sample")
        need(bool(re.fullmatch(r"[a-z][a-z0-9-]*\.json", row["name"]))
             and row["name"] not in sample_names,
             "Native sample name is invalid or duplicated")
        sample_names.add(row["name"])
        need(type(row["max_age_seconds"]) is int
             and 60 <= row["max_age_seconds"] <= 3600,
             "Native sample freshness limit is invalid")

    need(isinstance(value["services"], list) and value["services"],
         "Native service policy is empty")
    service_names = set()
    for row in value["services"]:
        keys(row, {"name", "start_mode", "required"}, "Native service")
        need(bool(re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", row["name"]))
             and row["name"] not in service_names,
             "Native service name is invalid or duplicated")
        service_names.add(row["name"])
        need(row["start_mode"] == "Auto" and type(row["required"]) is bool,
             "Native service start policy changed")

    need(isinstance(value["startup"], list) and value["startup"],
         "User-startup policy is empty")
    startup_names = set()
    for row in value["startup"]:
        keys(row, {"name", "process", "required"}, "User-startup item")
        need(all(isinstance(row[name], str) and 0 < len(row[name]) <= 64
                 for name in ("name", "process"))
             and row["name"] not in startup_names
             and type(row["required"]) is bool,
             "User-startup item is invalid or duplicated")
        startup_names.add(row["name"])

    need(isinstance(value["tasks"], list) and value["tasks"],
         "Scheduled-task policy is empty")
    task_names = set()
    for row in value["tasks"]:
        keys(row, {"name", "role", "action_marker", "triggers", "state_mode",
                   "result_mode", "start_when_available", "restart_count_min",
                   "first_day_gate"}, "Scheduled-task policy")
        need(isinstance(row["name"], str) and 0 < len(row["name"]) <= 128
             and row["name"] not in task_names,
             "Scheduled-task name is invalid or duplicated")
        task_names.add(row["name"])
        _windows_relative(row["action_marker"])
        need(row["role"] in {"long-running", "monitor", "startup", "backup",
                             "maintenance"}
             and row["state_mode"] in {"running", "ready"}
             and row["result_mode"] in {"running", "success"}
             and isinstance(row["triggers"], list) and bool(row["triggers"])
             and set(row["triggers"]) <= set(TRIGGER_CLASSES.values())
             and type(row["start_when_available"]) is bool
             and type(row["restart_count_min"]) is int
             and 0 <= row["restart_count_min"] <= 10,
             "Scheduled-task lifecycle policy is invalid")
        if row["first_day_gate"] is not None:
            need(row["role"] == "backup", "First-day gate is only valid for backups")
            _windows_relative(row["first_day_gate"])

    recovery = value["recovery"]
    keys(recovery, {"requires_user_logon", "unattended_boot_supported",
                    "automatic_reboot_allowed", "required_boot_tasks"},
         "Native reboot policy")
    need(recovery == {
        "requires_user_logon": True,
        "unattended_boot_supported": False,
        "automatic_reboot_allowed": False,
        "required_boot_tasks": [
            "Parmar Home - Glances Monitor",
            "Parmar Home - Glance Resources",
            "Coolify-Startup-Reconcile",
        ],
    }, "Native reboot boundary changed")
    need(set(recovery["required_boot_tasks"]) <= task_names,
         "Required reboot task is absent from the policy")
    return json.loads(canonical(value))


def load_policy(path: Path = POLICY) -> dict:
    return validate_policy(load_json(path))


def _run(arguments: list[str], *, timeout: int = 30,
         environment: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if environment:
        env.update(environment)
    try:
        return subprocess.run(arguments, text=True, encoding="utf-8", errors="replace",
                              capture_output=True, timeout=timeout, check=False, env=env,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(arguments, 127, "", "unavailable")


def _powershell_json(script: str, policy: dict) -> dict:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    need(bool(shell), "PowerShell is unavailable")
    result = _run([shell, "-NoProfile", "-NonInteractive", "-Command", script],
                  timeout=60,
                  environment={"HOMELAB_NATIVE_POLICY": canonical(policy)})
    need(result.returncode == 0, "Windows native lifecycle query failed")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("Windows native lifecycle query returned invalid JSON") from error
    need(isinstance(value, dict), "Windows native lifecycle query returned no object")
    return value


WINDOWS_QUERY = r"""
$ErrorActionPreference='Stop'
$p=$env:HOMELAB_NATIVE_POLICY|ConvertFrom-Json
$os=Get-CimInstance Win32_OperatingSystem
$boot=$os.LastBootUpTime
$serviceRows=@(foreach($s in $p.services){
  $item=Get-CimInstance Win32_Service -Filter ("Name='"+$s.name.Replace("'","''")+"'") -ErrorAction SilentlyContinue
  [pscustomobject]@{name=$s.name;exists=($null-ne$item);state=if($item){[string]$item.State}else{'missing'};start_mode=if($item){[string]$item.StartMode}else{$null}}
})
$startupCommands=@(Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue)
$startupRows=@(foreach($s in $p.startup){
  $entry=@($startupCommands|Where-Object Name -eq $s.name)
  $proc=@(Get-Process -Name $s.process -ErrorAction SilentlyContinue)
  [pscustomobject]@{name=$s.name;entry_present=($entry.Count-gt 0);process_running=($proc.Count-gt 0)}
})
$taskRows=@(foreach($spec in $p.tasks){
  $task=Get-ScheduledTask -TaskName $spec.name -TaskPath '\' -ErrorAction SilentlyContinue
  if(-not$task){[pscustomobject]@{name=$spec.name;exists=$false;enabled=$false;state='missing';last_result=$null;result_class='missing';last_run=$null;last_run_after_boot=$false;action_matches=$false;triggers=@();logon_type=$null;run_level=$null;start_when_available=$false;restart_count=0;definition_fingerprint=$null};continue}
  $info=Get-ScheduledTaskInfo -TaskName $spec.name -TaskPath '\'
  $action=(($task.Actions|ForEach-Object{($_.Execute+' '+$_.Arguments).Trim()})-join' | ')
  $types=@($task.Triggers|ForEach-Object{switch($_.CimClass.CimClassName){'MSFT_TaskLogonTrigger'{'logon'};'MSFT_TaskDailyTrigger'{'daily'};'MSFT_TaskWeeklyTrigger'{'weekly'};'MSFT_TaskTimeTrigger'{'time'};'MSFT_TaskBootTrigger'{'boot'};default{'other'}}})
  $last=if($info.LastRunTime-gt[datetime]::MinValue){$info.LastRunTime}else{$null}
  $resultClass=if([string]$task.State-eq'Running'-and[int64]$info.LastTaskResult-eq267009){'running'}elseif([int64]$info.LastTaskResult-eq0){'success'}else{'failure'}
  $fingerprintInput=(@([string]$task.Principal.LogonType,[string]$task.Principal.RunLevel,[string]$task.Settings.StartWhenAvailable,[string]$task.Settings.RestartCount)+$types+@($action.ToLowerInvariant()))-join'|'
  $sha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($fingerprintInput))).ToLowerInvariant()
  [pscustomobject]@{name=$spec.name;exists=$true;enabled=[bool]$task.Settings.Enabled;state=([string]$task.State).ToLowerInvariant();last_result=[int64]$info.LastTaskResult;result_class=$resultClass;last_run=if($last){$last.ToUniversalTime().ToString('o')}else{$null};last_run_after_boot=if($last){$last-ge$boot}else{$false};action_matches=$action.ToLowerInvariant().Contains(([string]$spec.action_marker).ToLowerInvariant());triggers=$types;logon_type=[string]$task.Principal.LogonType;run_level=[string]$task.Principal.RunLevel;start_when_available=[bool]$task.Settings.StartWhenAvailable;restart_count=[int]$task.Settings.RestartCount;definition_fingerprint=$sha}
})
$listener=@(Get-NetTCPConnection -State Listen -LocalPort 61208 -ErrorAction SilentlyContinue)
$gp=@()
foreach($connection in $listener){
  $candidate=Get-CimInstance Win32_Process -Filter ("ProcessId="+[int]$connection.OwningProcess) -ErrorAction SilentlyContinue
  if($candidate-and$candidate.CommandLine-match'(?i)-m\s+glances'){$gp+=@($candidate)}
}
$gp=@($gp|Select-Object -First 1)
$cmd=if($gp){[string]$gp[0].CommandLine}else{''}
$flags=@{};foreach($flag in $p.glances.required_flags){$flags[$flag]=$cmd.ToLowerInvariant().Contains(([string]$flag).ToLowerInvariant())}
$dockerContext=(& docker context show 2>$null|Out-String).Trim()
$dockerVersion=(& docker version --format '{{.Server.Version}}' 2>$null|Out-String).Trim()
[pscustomobject]@{
  boot_utc=$boot.ToUniversalTime().ToString('o');uptime_seconds=[math]::Floor(((Get-Date)-$boot).TotalSeconds);user_signed_in=(@(Get-Process explorer -ErrorAction SilentlyContinue|Where-Object SessionId -gt 0).Count-gt0);services=$serviceRows;startup=$startupRows;tasks=$taskRows;listener=[pscustomobject]@{loopback_only=($listener.Count-gt0-and@($listener|Where-Object LocalAddress-ne'127.0.0.1').Count-eq0);listening=($listener.Count-gt0)};glances_process=[pscustomobject]@{present=($gp.Count-gt0);required_flags=$flags};docker=[pscustomobject]@{context=$dockerContext;server_version=if($dockerVersion){$dockerVersion}else{$null};ready=[bool]$dockerVersion};secrets_read=$false;changes_made=$false
}|ConvertTo-Json -Depth 8 -Compress
"""


def collect_windows(policy: dict) -> dict:
    need(os.name == "nt", "Native lifecycle live audit only runs on Windows")
    result = _powershell_json(WINDOWS_QUERY, policy)
    by_name = {row["name"]: row for row in result.get("tasks", [])}
    root = Path(policy["root"])
    for spec in policy["tasks"]:
        row = by_name.get(spec["name"])
        if row is None:
            continue
        gate = spec["first_day_gate"]
        if gate is None:
            row["first_day_gate"] = None
            continue
        path = root / _windows_relative(gate)
        valid = False
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= 100_000:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            valid = bool(re.search(r"(?i)day\s*-ne\s*1", text))
        row["first_day_gate"] = valid
    return result


def _read_url(url: str, maximum: int) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "HomeLabNativeLifecycle/1"})
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read(maximum + 1)
        status = response.status
    need(len(body) <= maximum, "Native endpoint response is too large")
    return status, body


def collect_glances(policy: dict) -> dict:
    glances = policy["glances"]
    try:
        status_code, status_body = _read_url(glances["status_url"], 100_000)
        ui_code, ui_body = _read_url(glances["ui_url"], 2_000_000)
        all_code, all_body = _read_url(glances["all_url"], 5_000_000)
        status_value = json.loads(status_body)
        all_value = json.loads(all_body)
        need(isinstance(status_value, dict) and isinstance(all_value, dict),
             "Glances returned invalid objects")
        required = {name: name in all_value for name in
                    ("cpu", "mem", "load", "processcount", "diskio", "network")}
        return {
            "status": "checked",
            "status_http": status_code,
            "ui_http": ui_code,
            "all_http": all_code,
            "version": str(status_value.get("version", "")),
            "required_plugins": required,
            "ui_nonempty": len(ui_body) > 256,
            "raw_values_persisted": False,
        }
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
        return {
            "status": "unavailable", "status_http": None, "ui_http": None,
            "all_http": None, "version": None, "required_plugins": {},
            "ui_nonempty": False, "raw_values_persisted": False,
        }


def _utc(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    need(parsed.tzinfo is not None, "Native lifecycle timestamp has no timezone")
    return parsed.astimezone(dt.timezone.utc)


def collect_samples(policy: dict, now: dt.datetime | None = None) -> list[dict]:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    root = Path(policy["root"]) / "glance" / "resource-data"
    rows = []
    for spec in policy["samples"]:
        path = root / spec["name"]
        row = {"name": spec["name"], "exists": False, "valid_json": False,
               "age_seconds": None, "fresh": False, "source_statuses_ready": None}
        try:
            need(path.is_file() and not path.is_symlink()
                 and path.stat().st_size <= 2_000_000,
                 "Native sample is unavailable or unsafe")
            value = json.loads(path.read_text(encoding="utf-8"))
            need(isinstance(value, dict), "Native sample must contain an object")
            generated = value.get("generated_at")
            timestamp = _utc(generated) if isinstance(generated, str) else dt.datetime.fromtimestamp(
                path.stat().st_mtime, tz=dt.timezone.utc)
            age = max(0, round((now - timestamp).total_seconds(), 1))
            statuses = [item.get("status") for item in value.values()
                        if isinstance(item, dict) and "status" in item]
            healthy_statuses = {"ok", "reported"}
            row.update({
                "exists": True,
                "valid_json": True,
                "age_seconds": age,
                "fresh": age <= spec["max_age_seconds"],
                "source_statuses_ready": all(item in healthy_statuses for item in statuses)
                if statuses else True,
            })
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            pass
        rows.append(row)
    return rows


def _hash_file(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1_000_000:
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_audit(policy: dict, host: dict, glances: dict, samples: list[dict],
                generated_at: str | None = None,
                configuration: dict[str, str | None] | None = None) -> dict:
    policy = validate_policy(policy)
    service_specs = {row["name"]: row for row in policy["services"]}
    startup_specs = {row["name"]: row for row in policy["startup"]}
    task_specs = {row["name"]: row for row in policy["tasks"]}
    services = []
    for row in host["services"]:
        spec = service_specs[row["name"]]
        ready = bool(row["exists"] and row["state"] == "Running"
                     and row["start_mode"] == spec["start_mode"])
        services.append({**row, "ready": ready})
    startup = []
    for row in host["startup"]:
        ready = bool(row["entry_present"] and row["process_running"])
        startup.append({**row, "ready": ready})
    tasks = []
    boot_names = set(policy["recovery"]["required_boot_tasks"])
    for row in host["tasks"]:
        spec = task_specs[row["name"]]
        trigger_ready = set(row["triggers"]) == set(spec["triggers"])
        gate_ready = (row.get("first_day_gate") is True
                      if spec["first_day_gate"] else row.get("first_day_gate") is None)
        ready = bool(
            row["exists"] and row["enabled"] and row["action_matches"]
            and row["state"] == spec["state_mode"]
            and row["result_class"] == spec["result_mode"]
            and trigger_ready
            and row["start_when_available"] == spec["start_when_available"]
            and row["restart_count"] >= spec["restart_count_min"]
            and row["logon_type"] == "Interactive"
            and row["run_level"] == "Limited"
            and gate_ready
            and (row["last_run_after_boot"] if row["name"] in boot_names else True)
        )
        tasks.append({**row, "ready": ready})

    root = Path(policy["root"])
    config_hashes = configuration or {
        "start_script_sha256": _hash_file(
            root / _windows_relative(policy["glances"]["start_script"])),
        "configuration_sha256": _hash_file(
            root / _windows_relative(policy["glances"]["configuration"])),
    }
    flag_rows = host["glances_process"]["required_flags"]
    glances_ready = bool(
        glances["status"] == "checked"
        and glances["status_http"] == glances["ui_http"] == glances["all_http"] == 200
        and glances["version"] == policy["glances"]["version"]
        and glances["ui_nonempty"]
        and all(glances["required_plugins"].values())
        and host["listener"]["listening"]
        and host["listener"]["loopback_only"]
        and host["glances_process"]["present"]
        and set(flag_rows) == set(policy["glances"]["required_flags"])
        and all(flag_rows.values())
        and all(config_hashes.values())
    )
    samples_ready = (len(samples) == len(policy["samples"])
                     and all(row["exists"] and row["valid_json"] and row["fresh"]
                             and row["source_statuses_ready"] for row in samples))
    services_ready = all(row["ready"] for row in services
                         if service_specs[row["name"]]["required"])
    startup_ready = all(row["ready"] for row in startup
                        if startup_specs[row["name"]]["required"])
    tasks_ready = all(row["ready"] for row in tasks)
    host_ready = bool(host["user_signed_in"] and host["docker"]["ready"]
                      and host["docker"]["context"] == "desktop-linux")
    observed_reboot = bool(host_ready and services_ready and startup_ready and tasks_ready
                           and glances_ready and samples_ready
                           and host["uptime_seconds"] >= 60)
    blockers = []
    for name, ready in (("native-services-not-ready", services_ready),
                        ("user-startup-applications-not-ready", startup_ready),
                        ("scheduled-tasks-not-ready", tasks_ready),
                        ("glances-not-ready-or-not-private", glances_ready),
                        ("host-samples-not-fresh", samples_ready),
                        ("interactive-docker-desktop-host-not-ready", host_ready)):
        if not ready:
            blockers.append(name)
    result = {
        "kind": "homelab-native-lifecycle-audit",
        "contract": CONTRACT,
        "platform": policy["platform"],
        "support": "windows-interactive-existing-host",
        "generated_at": generated_at or dt.datetime.now(dt.timezone.utc).isoformat(),
        "policy_fingerprint": digest(policy),
        "host": {
            "boot_utc": host["boot_utc"],
            "uptime_seconds": host["uptime_seconds"],
            "user_signed_in": host["user_signed_in"],
            "docker": host["docker"],
        },
        "services": services,
        "startup": startup,
        "tasks": tasks,
        "glances": {**glances, "ready": glances_ready,
                     "configuration": config_hashes},
        "samples": samples,
        "readiness": {
            "services": services_ready,
            "startup": startup_ready,
            "tasks": tasks_ready,
            "glances": glances_ready,
            "samples": samples_ready,
            "host": host_ready,
            "observed_reboot_recovery": observed_reboot,
            "controlled_two_snapshot_reboot": False,
            "unattended_boot_supported": False,
        },
        "blockers": blockers,
        "safety": {
            "secrets_read": False,
            "paths_persisted": False,
            "raw_metrics_persisted": False,
            "changes_made": False,
            "automatic_reboot_performed": False,
        },
    }
    result["audit_id"] = digest(result)
    return result


def audit(policy: dict) -> dict:
    policy = validate_policy(policy)
    host = collect_windows(policy)
    return build_audit(policy, host, collect_glances(policy), collect_samples(policy))


def validate_audit(value: object) -> dict:
    keys(value, {"kind", "contract", "platform", "support", "generated_at",
                 "policy_fingerprint", "host", "services", "startup", "tasks",
                 "glances", "samples", "readiness", "blockers", "safety",
                 "audit_id"}, "Native lifecycle audit")
    need(value["kind"] == "homelab-native-lifecycle-audit"
         and value["contract"] == CONTRACT,
         "Unsupported native lifecycle audit")
    need(value["support"] == "windows-interactive-existing-host"
         and value["readiness"]["unattended_boot_supported"] is False,
         "Native lifecycle support boundary changed")
    need(value["safety"] == {
        "secrets_read": False,
        "paths_persisted": False,
        "raw_metrics_persisted": False,
        "changes_made": False,
        "automatic_reboot_performed": False,
    }, "Native lifecycle audit crossed its read-only boundary")
    text = canonical(value)
    need(not re.search(r"(?i)[A-Z]:\\|HOMESERVER\\|token=|password=", text),
         "Native lifecycle audit leaked a path, identity or credential marker")
    copy = dict(value)
    identifier = copy.pop("audit_id")
    need(identifier == digest(copy), "Native lifecycle audit identifier is invalid")
    return value


def checkpoint(observed: dict) -> dict:
    observed = validate_audit(observed)
    need(observed["readiness"]["observed_reboot_recovery"]
         and not observed["blockers"],
         "Native reboot checkpoint requires a ready current-boot audit")
    result = {
        "kind": "homelab-native-reboot-checkpoint",
        "contract": CONTRACT,
        "audit_id": observed["audit_id"],
        "boot_utc": observed["host"]["boot_utc"],
        "policy_fingerprint": observed["policy_fingerprint"],
        "task_fingerprints": {row["name"]: row["definition_fingerprint"]
                              for row in observed["tasks"]},
        "glances_configuration": observed["glances"]["configuration"],
        "automatic_reboot_allowed": False,
        "secrets_persisted": False,
    }
    result["checkpoint_id"] = digest(result)
    return result


def validate_checkpoint(value: object) -> dict:
    keys(value, {"kind", "contract", "audit_id", "boot_utc", "policy_fingerprint",
                 "task_fingerprints", "glances_configuration",
                 "automatic_reboot_allowed", "secrets_persisted", "checkpoint_id"},
         "Native reboot checkpoint")
    need(value["kind"] == "homelab-native-reboot-checkpoint"
         and value["contract"] == CONTRACT
         and value["automatic_reboot_allowed"] is False
         and value["secrets_persisted"] is False,
         "Native reboot checkpoint crossed its safety boundary")
    copy = dict(value)
    identifier = copy.pop("checkpoint_id")
    need(identifier == digest(copy), "Native reboot checkpoint identifier is invalid")
    return value


def reboot_evidence(before: dict, after: dict) -> dict:
    before = validate_checkpoint(before)
    after = validate_audit(after)
    blockers = []
    boot_changed = _utc(after["host"]["boot_utc"]) > _utc(before["boot_utc"])
    if not boot_changed:
        blockers.append("windows-boot-identifier-did-not-change")
    if before["policy_fingerprint"] != after["policy_fingerprint"]:
        blockers.append("native-lifecycle-policy-changed")
    current_tasks = {row["name"]: row["definition_fingerprint"]
                     for row in after["tasks"]}
    if before["task_fingerprints"] != current_tasks:
        blockers.append("scheduled-task-definitions-changed")
    if before["glances_configuration"] != after["glances"]["configuration"]:
        blockers.append("glances-configuration-changed")
    if not after["readiness"]["observed_reboot_recovery"]:
        blockers.append("post-reboot-native-lifecycle-not-ready")
    result = {
        "kind": "homelab-native-reboot-evidence",
        "contract": CONTRACT,
        "checkpoint_id": before["checkpoint_id"],
        "after_audit_id": after["audit_id"],
        "actual_reboot_observed": boot_changed,
        "task_definitions_persisted": before["task_fingerprints"] == current_tasks,
        "glances_configuration_persisted": (
            before["glances_configuration"] == after["glances"]["configuration"]),
        "native_services_recovered": after["readiness"]["services"],
        "user_startup_recovered": after["readiness"]["startup"],
        "scheduled_tasks_recovered": after["readiness"]["tasks"],
        "glances_recovered": after["readiness"]["glances"],
        "samples_recovered": after["readiness"]["samples"],
        "passed": not blockers,
        "blockers": blockers,
        "automatic_reboot_performed": False,
        "changes_performed": False,
    }
    result["evidence_id"] = digest(result)
    return result


def validate_reboot_evidence(value: object) -> dict:
    keys(value, {"kind", "contract", "checkpoint_id", "after_audit_id",
                 "actual_reboot_observed", "task_definitions_persisted",
                 "glances_configuration_persisted", "native_services_recovered",
                 "user_startup_recovered", "scheduled_tasks_recovered",
                 "glances_recovered", "samples_recovered", "passed", "blockers",
                 "automatic_reboot_performed", "changes_performed", "evidence_id"},
         "Native reboot evidence")
    need(value["kind"] == "homelab-native-reboot-evidence"
         and value["contract"] == CONTRACT
         and value["automatic_reboot_performed"] is False
         and value["changes_performed"] is False,
         "Native reboot evidence crossed its execution boundary")
    copy = dict(value)
    identifier = copy.pop("evidence_id")
    need(identifier == digest(copy), "Native reboot evidence identifier is invalid")
    return value
