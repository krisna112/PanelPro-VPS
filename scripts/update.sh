#!/usr/bin/env bash
# PanelPro updater — re-copies application code from this repository into the
# install root, refreshes dependencies and restarts the service.
# Original script, written from scratch for the PanelPro project.
set -euo pipefail

INSTALL_DIR="${PANELPRO_HOME:-/usr/local/panelpro}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo ">> Run as root" >&2
  exit 1
fi

echo ">> Updating PanelPro in $INSTALL_DIR from $SOURCE_DIR"

# keep the database + secrets; replace only code and assets
rm -rf "$INSTALL_DIR/panelpro" "$INSTALL_DIR/web"
cp -r "$SOURCE_DIR"/panelpro "$INSTALL_DIR"/
cp -r "$SOURCE_DIR"/web "$INSTALL_DIR"/
cp "$SOURCE_DIR"/requirements.txt "$INSTALL_DIR"/ 2>/dev/null || true

if [[ -x "$INSTALL_DIR/venv/bin/pip" ]]; then
  "$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
fi

systemctl restart panelpro 2>/dev/null || true
echo ">> Done. PanelPro restarted."
