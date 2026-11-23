#!/usr/bin/env bash
# =============================================================================
# PanelPro installer — Ubuntu / Debian / CentOS / RHEL / Rocky / Alma
# Original script, written from scratch for the PanelPro project.
#
#   curl -fsSL <raw-url>/scripts/install.sh | bash
#   # or: bash install.sh [options]
#
# Options:
#   --port N        panel port (default 21000)
#   --dir PATH      install root (default /usr/local/panelpro)
# =============================================================================
set -euo pipefail

PANEL_PORT="${PANEL_PORT:-21000}"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/panelpro}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PANEL_PORT="$2"; shift 2 ;;
    --dir)  INSTALL_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo ">> Run as root (sudo bash install.sh)" >&2
  exit 1
fi

echo "=============================================================="
echo " PanelPro installer"
echo "   install dir : $INSTALL_DIR"
echo "   panel port  : $PANEL_PORT"
echo "=============================================================="

# ---------------------------------------------------------------------------
# 1. Base packages + Python 3.10+
# ---------------------------------------------------------------------------
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip curl ca-certificates \
    cron unzip zip >/dev/null
  PY=python3
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y -q python3 python3-pip curl cronie unzip zip >/dev/null
  PY=python3
elif command -v yum >/dev/null 2>&1; then
  yum install -y -q python3 python3-pip curl cronie unzip zip >/dev/null
  PY=python3
else
  echo ">> Unsupported distro: install Python 3.10+ manually" >&2
  exit 1
fi

PY_VERSION=$($PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$($PY -c 'import sys; print(sys.version_info.major)')
if [[ "$PY_MAJOR" -lt 3 ]]; then
  echo ">> Python 3 required, found: $PY_VERSION" >&2
  exit 1
fi
echo ">> Python $PY_VERSION OK"

# ---------------------------------------------------------------------------
# 2. Copy application code
# ---------------------------------------------------------------------------
mkdir -p "$INSTALL_DIR"
cp -r "$SOURCE_DIR"/panelpro "$INSTALL_DIR"/
cp -r "$SOURCE_DIR"/web "$INSTALL_DIR"/
cp -r "$SOURCE_DIR"/scripts "$INSTALL_DIR"/ 2>/dev/null || true
cp "$SOURCE_DIR"/requirements.txt "$INSTALL_DIR"/ 2>/dev/null || true

# ---------------------------------------------------------------------------
# 3. Virtualenv + dependencies
# ---------------------------------------------------------------------------
$PY -m venv "$INSTALL_DIR/venv"
PIP="$INSTALL_DIR/venv/bin/pip"
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r "$INSTALL_DIR/requirements.txt" || \
  "$PIP" install fastapi 'uvicorn[standard]' sqlalchemy psutil bcrypt pyotp qrcode \
                 cryptography paramiko jinja2 python-multipart httpx croniter
echo ">> Dependencies installed"

# ---------------------------------------------------------------------------
# 4. Environment
# ---------------------------------------------------------------------------
export PANELPRO_HOME="$INSTALL_DIR"
"$INSTALL_DIR/venv/bin/python" -c "
from panelpro.config import CFG
CFG.ensure_dirs()
import os; os.environ.setdefault('PANELPRO_HOME', '$INSTALL_DIR')
from panelpro.core.database import init_db
init_db()
print('>> Panel home ready:', CFG.home)
"

# ---------------------------------------------------------------------------
# 5. systemd service
# ---------------------------------------------------------------------------
cat > /etc/systemd/system/panelpro.service <<UNIT
[Unit]
Description=PanelPro server control panel
Documentation=https://github.com/your-name/PanelPro
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
Environment=PANELPRO_HOME=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/panelpro start --port $PANEL_PORT
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now panelpro

# ---------------------------------------------------------------------------
# 6. Firewall + cron
# ---------------------------------------------------------------------------
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow "$PANEL_PORT"/tcp >/dev/null 2>&1 || true
  echo ">> ufw: port $PANEL_PORT/tcp opened"
elif command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port="$PANEL_PORT"/tcp >/dev/null 2>&1 || true
  firewall-cmd --reload >/dev/null 2>&1 || true
  echo ">> firewalld: port $PANEL_PORT/tcp opened"
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl enable crond 2>/dev/null || systemctl enable cron 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 7. Summary
# ---------------------------------------------------------------------------
sleep 2
ENTRY=$("$INSTALL_DIR/venv/bin/python" - <<PYEOF
import os
os.environ.setdefault('PANELPRO_HOME', '$INSTALL_DIR')
from panelpro.core import settings_store
settings_store.init_defaults()
print(settings_store.get_setting('entry_path'))
PYEOF
)

echo ""
echo "=============================================================="
echo " PanelPro installed successfully!"
echo ""
echo "   Panel URL : http://<server-ip>:$PANEL_PORT/$ENTRY"
echo "   Service   : systemctl status panelpro"
echo "   Logs      : journalctl -u panelpro -f"
echo ""
echo "   First admin credentials are in:"
echo "     $INSTALL_DIR/data/admin_credentials.txt"
echo "   (open it, save the password, then delete the file)"
echo ""
echo "   CLI: $INSTALL_DIR/venv/bin/panelpro doctor|set-port|reset-password"
echo "=============================================================="
