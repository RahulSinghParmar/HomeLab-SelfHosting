"""Validated desired state for Uptime Kuma 2.5.5 monitors and notifications."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import urllib.parse

from .config import ConfigError, ID, canonical, keys, load_json, need
from .privatefs import safe_path, verify_private


SCHEMA = 1
MAX_MONITORS = 64
MAX_NOTIFICATIONS = 16
MAX_GROUPS = 16
HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\Z")
STATUS = re.compile(r"(?P<start>[1-5][0-9]{2})(?:-(?P<end>[1-5][0-9]{2}))?\Z")


def _label(value: object, location: str, maximum: int = 120) -> str:
    need(isinstance(value, str) and value == value.strip() and 0 < len(value) <= maximum,
         f"{location} must be a bounded nonblank string")
    need(not any(ord(char) < 32 or ord(char) == 127 for char in value),
         f"{location} cannot contain control characters")
    return value


def _identifier(value: object, location: str) -> str:
    need(isinstance(value, str) and ID.fullmatch(value), f"{location} contains an invalid ID")
    return value


def _items(value: object, location: str, maximum: int) -> list[dict]:
    need(isinstance(value, list) and 0 <= len(value) <= maximum, f"{location} must be a bounded list")
    need(all(isinstance(item, dict) for item in value), f"{location} entries must be objects")
    identifiers = [_identifier(item.get("id"), location) for item in value]
    need(len(identifiers) == len(set(identifiers)), f"{location} contains duplicate IDs")
    return value


def _secret_ref(value: object, location: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    return _identifier(value, location)


def _url(value: object, location: str) -> str:
    need(isinstance(value, str) and len(value) <= 2048, f"{location} must be a bounded URL")
    parsed = urllib.parse.urlsplit(value)
    need(parsed.scheme in ("http", "https") and bool(parsed.hostname)
         and parsed.username is None and parsed.password is None and not parsed.fragment,
         f"{location} must be a credential-free HTTP or HTTPS URL")
    return value


def _status_codes(value: object) -> list[str]:
    need(isinstance(value, list) and 1 <= len(value) <= 20, "Monitor accepted status codes are invalid")
    for entry in value:
        need(isinstance(entry, str), "Monitor accepted status codes must be strings")
        match = STATUS.fullmatch(entry)
        need(match is not None, "Monitor accepted status code range is invalid")
        start = int(match.group("start"))
        end = int(match.group("end") or start)
        need(start <= end, "Monitor accepted status code range is reversed")
    return value


def validate_config(config: object) -> dict:
    keys(config, {"kind", "schema_version", "monitors", "notifications", "status_page"}, "Kuma configuration")
    need(config["kind"] == "homelab-kuma-config" and config["schema_version"] == SCHEMA,
         "Unsupported Kuma configuration")

    notifications = _items(config["notifications"], "Kuma notifications", MAX_NOTIFICATIONS)
    notification_ids = {item["id"] for item in notifications}
    for item in notifications:
        common = {"id", "name", "type", "enabled"}
        _label(item["name"], "Notification name")
        need(type(item["enabled"]) is bool, "Notification enabled must be true or false")
        if item["type"] == "webhook":
            keys(item, common | {"url", "url_secret", "method", "content_type", "additional_headers_secret"}, "Webhook notification")
            need((item["url"] is None) != (item["url_secret"] is None),
                 "Webhook requires exactly one of url or url_secret")
            if item["url"] is not None:
                _url(item["url"], "Webhook URL")
            _secret_ref(item["url_secret"], "Webhook URL secret", optional=True)
            need(item["method"] in ("GET", "POST"), "Webhook method must be GET or POST")
            need(item["content_type"] == "json", "Only JSON webhook bodies are supported")
            _secret_ref(item["additional_headers_secret"], "Webhook header secret", optional=True)
        elif item["type"] == "smtp":
            keys(item, common | {"host", "port", "secure", "ignore_tls_errors", "disable_starttls",
                                  "username_secret", "password_secret", "from_secret", "to_secret",
                                  "cc_secret", "bcc_secret", "custom_subject", "custom_body", "html_body"},
                 "SMTP notification")
            need(isinstance(item["host"], str) and HOST.fullmatch(item["host"]), "Invalid SMTP hostname")
            need(type(item["port"]) is int and 1 <= item["port"] <= 65535, "Invalid SMTP port")
            for field in ("secure", "ignore_tls_errors", "disable_starttls", "html_body"):
                need(type(item[field]) is bool, f"SMTP {field} must be true or false")
            need(not item["secure"] or not item["disable_starttls"], "Implicit TLS cannot disable STARTTLS")
            for field in ("username_secret", "password_secret", "cc_secret", "bcc_secret"):
                _secret_ref(item[field], f"SMTP {field}", optional=True)
            for field in ("from_secret", "to_secret"):
                _secret_ref(item[field], f"SMTP {field}")
            _label(item["custom_subject"], "SMTP custom subject", 240) if item["custom_subject"] else None
            need(isinstance(item["custom_body"], str) and len(item["custom_body"]) <= 8000,
                 "SMTP custom body must be a bounded string")
        else:
            raise ConfigError("Only webhook and SMTP notifications are supported")

    monitors = _items(config["monitors"], "Kuma monitors", MAX_MONITORS)
    need(bool(monitors), "At least one Kuma monitor is required")
    monitor_ids = {item["id"] for item in monitors}
    for item in monitors:
        keys(item, {"id", "name", "type", "url", "interval_seconds", "retry_interval_seconds", "retries",
                    "timeout_seconds", "method", "accepted_status_codes", "follow_redirects", "tls_verify",
                    "upside_down", "notification_ids"}, "HTTP monitor")
        need(item["type"] == "http", "Only HTTP monitors are currently supported")
        _label(item["name"], "Monitor name")
        parsed = urllib.parse.urlsplit(_url(item["url"], "Monitor URL"))
        need(type(item["interval_seconds"]) is int and 20 <= item["interval_seconds"] <= 86400,
             "Monitor interval must be between 20 and 86400 seconds")
        need(type(item["retry_interval_seconds"]) is int and 20 <= item["retry_interval_seconds"] <= 86400,
             "Monitor retry interval must be between 20 and 86400 seconds")
        need(type(item["retries"]) is int and 0 <= item["retries"] <= 10, "Monitor retries must be between 0 and 10")
        need(type(item["timeout_seconds"]) is int and 1 <= item["timeout_seconds"] <= 60,
             "Monitor timeout must be between 1 and 60 seconds")
        need(item["method"] in ("GET", "HEAD"), "Monitor method must be GET or HEAD")
        _status_codes(item["accepted_status_codes"])
        need(type(item["follow_redirects"]) is bool and type(item["tls_verify"]) is bool
             and type(item["upside_down"]) is bool, "Monitor flags must be true or false")
        need(item["tls_verify"] or parsed.scheme == "https", "TLS verification can be disabled only for HTTPS monitors")
        need(isinstance(item["notification_ids"], list)
             and len(item["notification_ids"]) == len(set(item["notification_ids"]))
             and all(ref in notification_ids for ref in item["notification_ids"]),
             "Monitor notification reference is invalid")
        enabled = {row["id"] for row in notifications if row["enabled"]}
        need(all(ref in enabled for ref in item["notification_ids"]), "Monitors cannot reference disabled notifications")

    page = config["status_page"]
    keys(page, {"slug", "title", "description", "theme", "refresh_seconds", "show_tags", "show_powered_by",
                "footer", "show_only_last_heartbeat", "show_certificate_expiry", "groups"}, "Kuma status page")
    _identifier(page["slug"], "Status-page slug")
    _label(page["title"], "Status-page title")
    need(isinstance(page["description"], str) and len(page["description"]) <= 1000, "Status-page description is too long")
    need(page["theme"] in ("light", "dark", "auto"), "Unsupported status-page theme")
    need(type(page["refresh_seconds"]) is int and 15 <= page["refresh_seconds"] <= 3600,
         "Status-page refresh must be between 15 and 3600 seconds")
    for field in ("show_tags", "show_powered_by", "show_only_last_heartbeat", "show_certificate_expiry"):
        need(type(page[field]) is bool, f"Status-page {field} must be true or false")
    need(isinstance(page["footer"], str) and len(page["footer"]) <= 500, "Status-page footer is too long")
    groups = page["groups"]
    need(isinstance(groups, list) and 1 <= len(groups) <= MAX_GROUPS, "Status-page groups must be a bounded list")
    seen: list[str] = []
    for group in groups:
        keys(group, {"name", "monitor_ids", "show_urls"}, "Status-page group")
        _label(group["name"], "Status-page group name")
        need(type(group["show_urls"]) is bool, "Status-page show_urls must be true or false")
        need(isinstance(group["monitor_ids"], list) and bool(group["monitor_ids"])
             and all(ref in monitor_ids for ref in group["monitor_ids"]), "Status-page monitor reference is invalid")
        seen.extend(group["monitor_ids"])
    need(len(seen) == len(set(seen)), "A monitor can appear only once on the status page")
    return json.loads(json.dumps(config, sort_keys=True))


def secret_references(config: dict) -> set[str]:
    config = validate_config(config)
    result: set[str] = set()
    for item in config["notifications"]:
        for key, value in item.items():
            if key.endswith("_secret") and value is not None:
                result.add(value)
    return result


def validate_secrets(secrets: object, required: set[str]) -> dict[str, str]:
    keys(secrets, {"kind", "schema_version", "values"}, "Kuma secrets")
    need(secrets["kind"] == "homelab-kuma-secrets" and secrets["schema_version"] == SCHEMA,
         "Unsupported Kuma secrets file")
    need(isinstance(secrets["values"], dict), "Kuma secret values must be an object")
    need(set(secrets["values"]) == required, "Kuma secrets must match exactly the configured references")
    for name, value in secrets["values"].items():
        _identifier(name, "Kuma secret")
        need(isinstance(value, str) and 0 < len(value) <= 16384 and "\0" not in value,
             "Kuma secret values must be bounded nonempty strings")
    return dict(secrets["values"])


def load_secret_values(path: Path | None, config: dict) -> dict[str, str]:
    required = secret_references(config)
    if not required:
        need(path is None, "This Kuma configuration does not use a secrets file")
        return {}
    need(path is not None, "A private Kuma secrets file is required")
    selected = safe_path(path)
    verify_private(selected)
    return validate_secrets(load_json(selected), required)


def configuration_hash(config: dict) -> str:
    return hashlib.sha256(canonical(validate_config(config)).encode("utf-8")).hexdigest()


def public_config(config: dict) -> dict:
    config = validate_config(config)
    return {
        "kind": config["kind"], "schema_version": config["schema_version"],
        "monitors": [{**item, "url": "<private-endpoint>"} for item in config["monitors"]],
        "notifications": [{key: ("<private-endpoint>" if key == "url" and value else value)
                           for key, value in item.items()} for item in config["notifications"]],
        "status_page": config["status_page"],
        "secret_references": sorted(secret_references(config)),
        "configuration_hash": configuration_hash(config),
    }


def materialize(config: dict, values: dict[str, str]) -> dict:
    config = validate_config(config)
    need(set(values) == secret_references(config), "Secret material does not match Kuma configuration")
    notifications = []
    for item in config["notifications"]:
        if not item["enabled"]:
            continue
        if item["type"] == "webhook":
            api = {"name": item["name"], "type": "webhook", "isDefault": False, "applyExisting": False,
                   "webhookURL": item["url"] or values[item["url_secret"]],
                   "httpMethod": item["method"].lower(), "webhookContentType": item["content_type"],
                   "webhookCustomBody": "",
                   "webhookAdditionalHeaders": values[item["additional_headers_secret"]]
                   if item["additional_headers_secret"] else None}
        else:
            def value(name: str) -> str:
                ref = item[name]
                return values[ref] if ref else ""
            api = {"name": item["name"], "type": "smtp", "isDefault": False, "applyExisting": False,
                   "smtpHost": item["host"], "smtpPort": item["port"], "smtpSecure": item["secure"],
                   "smtpIgnoreTLSError": item["ignore_tls_errors"], "smtpIgnoreSTARTTLS": item["disable_starttls"],
                   "smtpUsername": value("username_secret"), "smtpPassword": value("password_secret"),
                   "smtpFrom": value("from_secret"), "smtpTo": value("to_secret"),
                   "smtpCC": value("cc_secret"), "smtpBCC": value("bcc_secret"),
                   "customSubject": item["custom_subject"], "customBody": item["custom_body"],
                   "htmlBody": item["html_body"], "smtpAdditionalHeaders": None}
        notifications.append({"id": item["id"], "api": api})

    monitors = []
    for item in config["monitors"]:
        monitors.append({"id": item["id"], "notification_ids": item["notification_ids"], "api": {
            "name": item["name"], "url": item["url"], "type": "http", "interval": item["interval_seconds"],
            "retryInterval": item["retry_interval_seconds"], "maxretries": item["retries"],
            "timeout": item["timeout_seconds"], "method": item["method"], "active": True,
            "ignoreTls": not item["tls_verify"], "accepted_statuscodes": item["accepted_status_codes"],
            "upsideDown": item["upside_down"], "maxredirects": 10 if item["follow_redirects"] else 0,
            "resendInterval": 0, "conditions": [], "kafkaProducerBrokers": [],
            "kafkaProducerSaslOptions": {}, "rabbitmqNodes": []}})
    return {"schema_version": SCHEMA, "configuration_hash": configuration_hash(config),
            "notifications": notifications, "monitors": monitors, "status_page": config["status_page"]}


def load_and_validate(path: Path) -> dict:
    return validate_config(load_json(path))
