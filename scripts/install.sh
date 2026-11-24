#!/usr/bin/env bash
# Install PanelPro from a complete checkout on a Linux systemd host.

read_install_answer() {
  local answer
  printf '%s' "$1" >&2
  if ! IFS= read -r answer; then
    echo "Installation cancelled before applying any changes." >&2
    return 1
  fi
  IFS=$' \t' read -r "$2" <<< "${answer%$'\r'}"
}

prompt_install_options() {
  local php_available="$1" choice
  local hostname_pattern='^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$'

  echo "PanelPro installation setup" >&2
  if [[ -z $PANEL_DOMAIN && $PANEL_HOST == 127.0.0.1 ]]; then
    echo "For public HTTPS, point the panel hostname to this VPS and allow TCP ports 80 and 443." >&2
    while true; do
      read_install_answer "Panel hostname (e.g. panel.example.com, Enter for SSH tunnel access): " PANEL_DOMAIN || return 1
      if [[ -z $PANEL_DOMAIN ]]; then
        break
      fi
      PANEL_DOMAIN="${PANEL_DOMAIN%.}"
      if [[ ${#PANEL_DOMAIN} -le 253 && $PANEL_DOMAIN =~ $hostname_pattern ]]; then
        break
      fi
      echo "Enter a hostname such as panel.example.com, without https:// or a port." >&2
    done
  fi

  if [[ -n $PANEL_DOMAIN && -z $PANEL_EMAIL ]]; then
    while true; do
      read_install_answer "Email for Let's Encrypt: " PANEL_EMAIL || return 1
      if [[ $PANEL_EMAIL == ?*@?* && $PANEL_EMAIL != -* && $PANEL_EMAIL != *[[:space:]]* ]]; then
        break
      fi
      echo "Enter a valid email address." >&2
    done
  fi

  if [[ -z $STACK ]]; then
    echo "1) Nginx for static websites and reverse proxies" >&2
    if [[ $php_available == true ]]; then
      echo "2) Nginx, PHP-FPM and MariaDB" >&2
    fi
    echo "3) Use the existing web stack" >&2
    while true; do
      read_install_answer "Web stack [1]: " choice || return 1
      case "$choice" in
        1|'') STACK=nginx; break ;;
        2) if [[ $php_available == true ]]; then STACK=php; break; fi ;;
        3) STACK=none; break ;;
      esac
      echo "Choose one of the web stacks listed above." >&2
    done
  fi
}

if [[ ${BASH_SOURCE[0]} != "$0" ]]; then
  return
fi
set -euo pipefail

PANEL_PORT="${PANEL_PORT:-21000}"
PANEL_HOST="${PANEL_HOST:-127.0.0.1}"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/panelpro}"
STACK=""
PANEL_DOMAIN=""
PANEL_EMAIL=""
INSTALL_PHPMYADMIN=true
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INTERACTIVE=false
if [[ $# -eq 0 && -t 0 ]]; then
  INTERACTIVE=true
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port|--host|--dir|--stack|--domain|--email)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for $1" >&2
        exit 1
      fi
      case "$1" in
        --port) PANEL_PORT="$2" ;;
        --host) PANEL_HOST="$2" ;;
        --dir) INSTALL_DIR="$2" ;;
        --stack) STACK="$2" ;;
        --domain) PANEL_DOMAIN="$2" ;;
        --email) PANEL_EMAIL="$2" ;;
      esac
      shift 2
      ;;
    --interactive) INTERACTIVE=true; shift ;;
    --skip-phpmyadmin) INSTALL_PHPMYADMIN=false; shift ;;
    --non-interactive) INTERACTIVE=false; shift ;;
    --help)
      echo "Usage: sudo bash scripts/install.sh [--port 21000] [--host 127.0.0.1] [--dir /usr/local/panelpro] [--stack none|nginx|php]"
      echo "Run without options in a terminal for guided setup, or add --interactive with other options."
      echo "For HTTPS access, add: --domain panel.example.com --email admin@example.com"
      echo "Use --skip-phpmyadmin to omit phpMyAdmin on a new Debian or Ubuntu installation."
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
FRESH_INSTALL=true
if [[ -f "$INSTALL_DIR/data/panel.db" ]]; then
  FRESH_INSTALL=false
fi
if [[ $INSTALL_DIR == / || ! -f "$SOURCE_DIR/panelpro/__main__.py" || ! -f "$SOURCE_DIR/requirements.txt" ]]; then
  echo "Choose an application directory and run from the complete PanelPro checkout." >&2
  exit 1
fi
if [[ $INTERACTIVE == true ]]; then
  PHP_AVAILABLE=false
  if command -v apt-get >/dev/null 2>&1; then
    PHP_AVAILABLE=true
  fi
  prompt_install_options "$PHP_AVAILABLE"
fi
if [[ -n $PANEL_DOMAIN ]]; then
  if [[ -z $PANEL_EMAIL || $PANEL_HOST != 127.0.0.1 ]]; then
    echo "--domain requires --email and a panel listener on 127.0.0.1." >&2
    exit 1
  fi
  STACK="${STACK:-nginx}"
fi
STACK="${STACK:-none}"
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
        packages+=(php-fpm php-mysql php-curl php-gd php-xml php-mbstring php-zip mariadb-server)
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
install -d -m 0700 "$INSTALL_DIR/data" "$INSTALL_DIR/data/ssl" "$INSTALL_DIR/tmp" "$INSTALL_DIR/backup"
venv/bin/python -m panelpro set-port "$PANEL_PORT"
if [[ $INTERACTIVE == true ]]; then
  venv/bin/python -m panelpro setup-admin
fi
bash scripts/install_cli.sh "$INSTALL_DIR"

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

APP_FAILED=false
if [[ $FRESH_INSTALL == true && $INSTALL_PHPMYADMIN == true && $STACK != none ]] && command -v apt-get >/dev/null 2>&1; then
  echo "Setting up phpMyAdmin..."
  if ! venv/bin/panelpro install-app phpmyadmin; then
    APP_FAILED=true
    echo "PanelPro started. Retry phpMyAdmin from the App Store after resolving the package or webserver error above." >&2
  fi
fi

DOMAIN_FAILED=false
if [[ -n $PANEL_DOMAIN ]]; then
  if ! venv/bin/panelpro setup-domain "$PANEL_DOMAIN" --email "$PANEL_EMAIL"; then
    DOMAIN_FAILED=true
    echo "PanelPro started locally. Check DNS and ports 80/443, then retry with setup-domain." >&2
  fi
fi
if [[ -z $PANEL_DOMAIN || $DOMAIN_FAILED == true ]]; then
  echo "PanelPro is running at $URL/$ENTRY"
  if [[ $PANEL_HOST == 127.0.0.1 ]]; then
    echo "From your workstation, connect with: ssh -N -L $PANEL_PORT:127.0.0.1:$PANEL_PORT user@server"
  fi
fi
if [[ -f "$INSTALL_DIR/data/admin_credentials.txt" ]]; then
  echo "Initial credentials: $INSTALL_DIR/data/admin_credentials.txt"
fi
echo "CLI: $INSTALL_DIR/venv/bin/panelpro"
echo "Terminal menu: sudo panelpro menu"
if [[ $DOMAIN_FAILED == true || $APP_FAILED == true ]]; then
  exit 1
fi
