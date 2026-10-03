#!/bin/sh
# Thin launcher only. Does not install packages or change working directory.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then
        exec "$candidate" "$script_dir/homelab_cli.py" "$@"
    fi
done
printf '%s\n' 'Python 3.12 or newer was not found. Install Python manually and rerun.' >&2
exit 2
