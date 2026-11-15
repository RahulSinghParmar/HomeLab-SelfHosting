#!/bin/sh
set -eu

expected="${CODE_SERVER_EXPECTED_VERSION:?CODE_SERVER_EXPECTED_VERSION is required}"
actual="$(code-server --version 2>&1 \
    | sed -n '/^[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*/{s/ .*//;p;q;}')"
test "$actual" = "$expected" || {
    echo "code-server version mismatch: expected $expected, found $actual" >&2
    exit 67
}

user_data="${CODE_SERVER_USER_DATA_DIR:-/home/coder/.local/share/code-server}"
extensions="$user_data/extensions"
settings="$user_data/User/settings.json"
mkdir -p "$extensions" "$(dirname "$settings")"

if test ! -e "$settings"; then
    cp /opt/homelab/settings.json "$settings"
fi

for source in /opt/homelab/extensions/*; do
    test -d "$source" || continue
    target="$extensions/$(basename "$source")"
    test -e "$target" || cp -R "$source" "$target"
done

exec code-server --user-data-dir "$user_data" \
    --extensions-dir "$extensions" "$@"
