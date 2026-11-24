#!/usr/bin/env bash
# Refresh an installed PanelPro from this checkout.
set -euo pipefail

INSTALL_DIR="$(realpath -m -- "${PANELPRO_HOME:-/usr/local/panelpro}")"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi
if [[ $INSTALL_DIR == / || ! -x "$INSTALL_DIR/venv/bin/panelpro" || ! -f "$INSTALL_DIR/panelpro/__main__.py" || ! -d "$INSTALL_DIR/web" ]]; then
  echo "PanelPro installation not found. Run scripts/install.sh to create or repair it." >&2
  exit 1
fi

PYTHON="$INSTALL_DIR/venv/bin/python"
if [[ $SOURCE_DIR == "$INSTALL_DIR" ]]; then
  "$PYTHON" -m pip install --quiet -r "$INSTALL_DIR/requirements.txt"
  bash "$INSTALL_DIR/scripts/vendor_assets.sh"
  systemctl restart panelpro
  systemctl is-active --quiet panelpro
  exit 0
fi

STAGING="$(mktemp -d "$INSTALL_DIR/.update.XXXXXXXX")"
mkdir "$STAGING/old"
backup_moved=false

cleanup() {
  local status=$?
  if [[ $status -ne 0 && $backup_moved == true ]]; then
    for item in panelpro web scripts requirements.txt; do
      if [[ -e "$STAGING/old/$item" ]]; then
        rm -rf -- "$INSTALL_DIR/$item"
        mv -- "$STAGING/old/$item" "$INSTALL_DIR/$item"
      fi
    done
    systemctl restart panelpro || true
  fi
  rm -rf -- "$STAGING"
}
trap cleanup EXIT

cp -r "$SOURCE_DIR"/{panelpro,web,scripts} "$STAGING/"
cp "$SOURCE_DIR/requirements.txt" "$STAGING/"
if [[ -d "$INSTALL_DIR/web/assets/vendor" ]]; then
  mkdir -p "$STAGING/web/assets/vendor"
  cp -an "$INSTALL_DIR/web/assets/vendor/." "$STAGING/web/assets/vendor/"
fi
bash "$STAGING/scripts/vendor_assets.sh"
"$PYTHON" -m pip install --quiet -r "$STAGING/requirements.txt"
"$PYTHON" -m compileall -q "$STAGING/panelpro"

backup_moved=true
for item in panelpro web scripts requirements.txt; do
  if [[ -e "$INSTALL_DIR/$item" ]]; then
    mv -- "$INSTALL_DIR/$item" "$STAGING/old/$item"
  fi
  mv -- "$STAGING/$item" "$INSTALL_DIR/$item"
done
systemctl restart panelpro
sleep 1
systemctl is-active --quiet panelpro
echo "PanelPro updated and restarted."
