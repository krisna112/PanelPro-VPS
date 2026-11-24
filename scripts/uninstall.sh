#!/usr/bin/env bash
# PanelPro uninstaller — removes the service and (optionally) all data.
# Original script, written from scratch for the PanelPro project.
set -euo pipefail

INSTALL_DIR="${PANELPRO_HOME:-/usr/local/panelpro}"

if [[ $EUID -ne 0 ]]; then
  echo ">> Run as root" >&2
  exit 1
fi

echo ">> Stopping panelpro service…"
systemctl disable --now panelpro 2>/dev/null || true
rm -f /etc/systemd/system/panelpro.service
systemctl daemon-reload 2>/dev/null || true
CLI_LINK=/usr/local/bin/panelpro
if [[ -L $CLI_LINK && $(readlink -- "$CLI_LINK") == "$(realpath -m -- "$INSTALL_DIR")/venv/bin/panelpro" ]]; then
  rm -f -- "$CLI_LINK"
fi

if [[ "${1:-}" == "--purge" ]]; then
  echo ">> Removing $INSTALL_DIR (including panel database and secrets)…"
  rm -rf "$INSTALL_DIR"
else
  echo ">> Keeping $INSTALL_DIR (use --purge to delete data as well)."
  echo "   Backup first with: panelpro backup-panel"
fi

echo ">> PanelPro uninstalled."
