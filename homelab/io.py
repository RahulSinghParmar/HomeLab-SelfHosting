"""Explicit, no-overwrite private settings/report output, never inside this checkout."""

import json
import os
from pathlib import Path

from .config import ConfigError, ROOT, need


def write_private(path: Path, value: object) -> None:
    need(path.is_absolute(), "Output path must be absolute")
    need(path.suffix.lower() == ".json", "Output must be a JSON file")
    need(not path.exists() and not path.is_symlink(), "Refusing to overwrite an existing output")
    need(path.parent.is_dir(), "Create a private output directory first; the planner does not create storage directories")
    need(not any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()) for p in (path, *path.parents)),
         "Output path must not include symlinks or junctions")
    resolved = path.resolve()
    need(not resolved.is_relative_to(ROOT), "Private settings and reports must stay outside the repository")
    # Also refuse another Git checkout, not just this project's checkout.
    need(not any((parent / ".git").exists() for parent in path.parents), "Output must not be inside a Git checkout")
    payload = (json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    descriptor = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        # Preserve any partial output for inspection; never remove an ambiguous path.
        raise ConfigError("Could not save private JSON; inspect the requested output before retrying") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
