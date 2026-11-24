#!/usr/bin/env bash
# Install PanelPro from a complete checkout on a Linux systemd host.
set -euo pipefail

PANEL_PORT="${PANEL_PORT:-21000}"
PANEL_HOST="${PANEL_HOST:-127.0.0.1}"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/panelpro}"
STACK=none
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port|--host|--dir|--stack)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for $1" >&2
        exit 1
      fi
      case "$1" in
        --port) PANEL_PORT="$2" ;;
        --host) PANEL_HOST="$2" ;;
        --dir) INSTALL_DIR="$2" ;;
        --stack) STACK="$2" ;;
      esac
      shift 2
      ;;
    --help)
      echo "Usage: sudo bash scripts/install.sh [--port 21000] [--host 127.0.0.1] [--dir /usr/local/panelpro] [--stack none|nginx|php]"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ $EUID -ne 0 || ! -d /run/systemd/system ]]; then
  echo "Run the installer as root on a Linux host running systemd." >&2
  exit 1
fi
if [[ ! $PANEL_PORT =~ ^[1-9][0-9]{3,4}$ ]] || (( PANEL_PORT < 1024 || PANEL_PORT > 65535 )); then
  echo "Panel port must be between 1024 and 65535." >&2
  exit 1
fi
if [[ ! $PANEL_HOST =~ ^[a-zA-Z0-9_.:-]+$ || ! $INSTALL_DIR =~ ^/[a-zA-Z0-9._/-]+$ ]]; then
  echo "Use a valid bind host and an absolute install directory without spaces." >&2
  exit 1
fi
INSTALL_DIR="$(realpath -m -- "$INSTALL_DIR")"
if [[ $INSTALL_DIR == / || ! -f "$SOURCE_DIR/panelpro/__main__.py" || ! -f "$SOURCE_DIR/requirements.txt" ]]; then
  echo "Choose an application directory and run from the complete PanelPro checkout." >&2
  exit 1
fi
if [[ $STACK != none && $STACK != nginx && $STACK != php ]]; then
  echo "Unknown stack: $STACK" >&2
  exit 1
fi
if [[ $STACK == php ]] && ! command -v apt-get >/dev/null 2>&1; then
  echo "The PHP stack installer requires Debian or Ubuntu." >&2
  exit 1
fi

PY=python3
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip curl ca-certificates cron unzip zip
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y -q python3.11 python3.11-pip curl ca-certificates cronie unzip zip
  PY=python3.11
else
  echo "The installer requires apt-get or dnf." >&2
  exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  echo "Python 3.10 or newer is required. Use Debian 12+ or Ubuntu 22.04+." >&2
  exit 1
fi

case "$STACK" in
  nginx|php)
    if command -v apt-get >/dev/null 2>&1; then
      packages=(nginx certbot)
      if [[ $STACK == php ]]; then
        packages+=(php-fpm php-mysql mariadb-server)
      fi
      apt-get install -y -qq "${packages[@]}"
    else
      dnf install -y -q nginx
    fi
    systemctl enable --now nginx
    nginx -t
    if [[ $STACK == php ]]; then
      systemctl enable --now mariadb
    fi
    ;;
esac

mkdir -p "$INSTALL_DIR"
if [[ $SOURCE_DIR != "$INSTALL_DIR" ]]; then
  cp -r "$SOURCE_DIR"/{panelpro,web,scripts} "$INSTALL_DIR/"
  cp "$SOURCE_DIR/requirements.txt" "$INSTALL_DIR/"
fi
cd "$INSTALL_DIR"
"$PY" -m venv venv
venv/bin/python -m pip install --quiet -r requirements.txt
bash scripts/vendor_assets.sh

export PANELPRO_HOME="$INSTALL_DIR"
venv/bin/python -m panelpro set-port "$PANEL_PORT"
install -d -m 0700 "$INSTALL_DIR/data" "$INSTALL_DIR/data/ssl" "$INSTALL_DIR/tmp" "$INSTALL_DIR/backup"
cat > venv/bin/panelpro <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
panel_home="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PANELPRO_HOME="$panel_home"
cd "$panel_home"
exec "$panel_home/venv/bin/python" -m panelpro "$@"
LAUNCHER
chmod 0755 venv/bin/panelpro

cat > /etc/systemd/system/panelpro.service <<UNIT
[Unit]
Description=PanelPro server control panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
Environment=PANELPRO_HOME=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/panelpro start --host $PANEL_HOST
Restart=on-failure
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable panelpro
systemctl restart panelpro

ENTRY="$(venv/bin/python -c 'from panelpro.core.settings_store import get_setting; print(get_setting("entry_path"))')"
SCHEME="$(venv/bin/python -c 'from panelpro.core.settings_store import get_setting; print("https" if get_setting("panel_ssl") else "http")')"
CHECK_HOST="$PANEL_HOST"
case "$CHECK_HOST" in
  0.0.0.0) CHECK_HOST=127.0.0.1 ;;
  ::) CHECK_HOST='[::1]' ;;
  *:*) CHECK_HOST="[$CHECK_HOST]" ;;
esac
URL="$SCHEME://$CHECK_HOST:$PANEL_PORT"
READY=false
for (( attempt=0; attempt<30; attempt++ )); do
  if curl --insecure --noproxy '*' --fail --silent --max-time 2 "$URL/api/health" >/dev/null; then
    READY=true
    break
  fi
  sleep 1
done
if [[ $READY != true ]]; then
  echo "PanelPro failed its local health check. Run: journalctl -u panelpro -n 60" >&2
  exit 1
fi

echo "PanelPro is running at $URL/$ENTRY"
if [[ $PANEL_HOST == 127.0.0.1 ]]; then
  echo "From your workstation, connect with: ssh -N -L $PANEL_PORT:127.0.0.1:$PANEL_PORT user@server"
fi
if [[ -f "$INSTALL_DIR/data/admin_credentials.txt" ]]; then
  echo "Initial credentials: $INSTALL_DIR/data/admin_credentials.txt"
fi
echo "CLI: $INSTALL_DIR/venv/bin/panelpro"
