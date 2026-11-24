#!/usr/bin/env bash
set -euo pipefail

PANEL_INSTALL_DIR="$1"
CLI_PATH="$PANEL_INSTALL_DIR/venv/bin/panelpro"
CLI_LINK=/usr/local/bin/panelpro

TEMP_CLI="$(mktemp "$PANEL_INSTALL_DIR/venv/bin/.panelpro.XXXXXXXX")"
trap 'rm -f -- "$TEMP_CLI"' EXIT
cat > "$TEMP_CLI" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
launcher="$(readlink -f -- "${BASH_SOURCE[0]}")"
panel_home="$(cd "$(dirname "$launcher")/../.." && pwd)"
export PANELPRO_HOME="$panel_home"
cd "$panel_home"
exec "$panel_home/venv/bin/python" -m panelpro "$@"
LAUNCHER
chmod 0755 "$TEMP_CLI"
mv -f -- "$TEMP_CLI" "$CLI_PATH"

if [[ -L $CLI_LINK && $(readlink -- "$CLI_LINK") == "$CLI_PATH" ]]; then
  exit 0
fi
if [[ -e $CLI_LINK || -L $CLI_LINK ]]; then
  echo "$CLI_LINK is already in use. Open the menu with $CLI_PATH menu." >&2
  exit 0
fi
mkdir -p -- "$(dirname "$CLI_LINK")"
ln -s -- "$CLI_PATH" "$CLI_LINK"
