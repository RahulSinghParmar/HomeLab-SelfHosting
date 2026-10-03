"""Small, explicit publication guard; not a replacement for a full secret scanner."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import PurePosixPath


PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "github-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"),
    "aws-access-key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "credentialed-url": re.compile(r"https?://[^\s/:@]+:[^\s/@]+@[^\s/]+"),
}
BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3", ".dump", ".clixml"}
BLOCKED_DIRS = {"private", "backups", "runtime", "state", "exports", "reports", "local"}


def inspect_text(path: str, content: str) -> list[str]:
    findings = []
    source = PurePosixPath(path)
    if (source.name == ".env" or source.suffix.lower() in BLOCKED_SUFFIXES
            or any(part in BLOCKED_DIRS for part in source.parts[:-1])):
        findings.append(f"{path}: prohibited publication path")
    for number, line in enumerate(content.splitlines(), 1):
        for name, pattern in PATTERNS.items():
            if pattern.search(line):
                # The synthetic URL regression fixture deliberately tests rejection.
                fixture = '"https://' + 'user:example@example.com/repo"'
                if name == "credentialed-url" and path == "tests/test_repository.py" and fixture in line:
                    continue
                findings.append(f"{path}:{number}: {name}")
    return findings


def git(*arguments: str) -> bytes:
    return subprocess.run(["git", *arguments], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).stdout


def scan(*, history: bool = False) -> tuple[int, list[str]]:
    candidates: dict[str, str] = {}
    # Scan index contents, not a possibly different working-tree version.
    for raw_path in git("ls-files", "-z").split(b"\0"):
        if raw_path:
            path = raw_path.decode("utf-8")
            candidates[f"index:{path}"] = path
    if history:
        for commit in git("rev-list", "--all").decode().splitlines():
            for raw_path in git("ls-tree", "-r", "--name-only", "-z", commit).split(b"\0"):
                if raw_path:
                    path = raw_path.decode("utf-8")
                    candidates[f"{commit}:{path}"] = path
    findings = []
    for reference, path in candidates.items():
        specifier = ":" + path if reference.startswith("index:") else reference
        content = git("show", specifier)
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(f"{path}: non-UTF-8 artifact requires separate publication review")
            continue
        findings.extend(inspect_text(path, text))
    return len(candidates), sorted(set(findings))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="Also inspect all locally reachable commits")
    arguments = parser.parse_args()
    try:
        count, findings = scan(history=arguments.history)
    except (subprocess.CalledProcessError, UnicodeError) as error:
        print(f"FAIL: Git publication input unavailable ({type(error).__name__})", file=sys.stderr)
        return 1
    if findings:
        print("\n".join(findings), file=sys.stderr)
        return 1
    print(f"PASS: publication guard checked {count} index/history file versions. Manual review is still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
