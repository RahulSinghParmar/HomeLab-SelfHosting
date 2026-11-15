#!/bin/sh
set -eu

manifest="${1:-/opt/homelab/extensions.txt}"
destination="${2:-/opt/homelab/extensions}"

test -r "$manifest"
mkdir -p "$destination"

while IFS= read -r extension || test -n "$extension"; do
    case "$extension" in
        ''|'#'*) continue ;;
    esac
    case "$extension" in
        *@*) ;;
        *) echo "Unpinned extension refused: $extension" >&2; exit 65 ;;
    esac
    code-server --extensions-dir "$destination" \
        --install-extension "$extension" --force
done < "$manifest"

installed="$(code-server --extensions-dir "$destination" \
    --list-extensions --show-versions 2>/dev/null | sort)"
requested="$(grep -Ev '^[[:space:]]*(#|$)' "$manifest" | sort)"

while IFS= read -r extension || test -n "$extension"; do
    printf '%s\n' "$installed" | grep -Fqx "$extension" || {
        echo "Pinned extension missing after install: $extension" >&2
        exit 66
    }
done <<EOF
$requested
EOF
