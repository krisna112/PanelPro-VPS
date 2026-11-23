# Installation & Operations Guide

## Requirements

* A Linux server (Ubuntu 20.04+/Debian 11+/CentOS Stream 9+/RHEL-family)
  with root access — the panel manages system services, so production
  targets Linux.
* Python 3.10+ (installed automatically by `install.sh`).
* ~150 MB free disk + whatever your sites need.

## Production install

```bash
git clone https://github.com/your-name/PanelPro.git
cd PanelPro
sudo bash scripts/install.sh            # defaults: /usr/local/panelpro, port 21000
sudo bash scripts/install.sh --port 24000 --dir /opt/panelpro
```

What the installer does:

1. Installs Python 3 + base tools via the distro package manager.
2. Copies `panelpro/` (backend), `web/` (frontend), `scripts/` into the
   install root.
3. Creates a virtualenv and installs dependencies.
4. Generates the panel database, secret key, **random admin password** and
   **random security entry path**.
5. Installs a `panelpro.service` systemd unit (auto-start + restart).
6. Opens the chosen port in ufw/firewalld when a firewall is active.

After the install:

* Panel URL: `http://<server-ip>:21000/<entry-path>` (printed at the end).
* Admin credentials: `/usr/local/panelpro/data/admin_credentials.txt`
  (read it, save the password, delete the file).

## Offline frontend assets

The SPA loads Vue/vue-router/xterm from a CDN with automatic fallback.
For fully offline servers run once:

```bash
bash scripts/vendor_assets.sh   # downloads into web/assets/vendor/
```

`index.html` prefers the local vendor copies automatically.

## Update & uninstall

```bash
sudo bash scripts/update.sh              # refresh code + deps + restart
sudo bash scripts/uninstall.sh           # keep data (DB/secrets)
sudo bash scripts/uninstall.sh --purge   # remove everything
```

## CLI reference (`panelpro`)

| Command | Purpose |
| --- | --- |
| `panelpro start [--host H] [--port P] [--dev]` | run the panel (systemd uses this) |
| `panelpro reset-password [--username admin]` | print a fresh admin password, revoke sessions |
| `panelpro set-port 21000` | change the panel port (restart required) |
| `panelpro set-entry my-secret-path` | change the security entry path |
| `panelpro backup-panel` | tar the panel DB + secret key |
| `panelpro doctor` | environment check: tools found, DB, deps |
| `panelpro version` | print version |

The CLI lives in `venv/bin/panelpro` inside the install root
(`/usr/local/panelpro/venv/bin/panelpro`).

## Development mode

Works on any OS (Windows/macOS/Linux) for API and UI work; Linux-only
features degrade gracefully with informative errors.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
PANELPRO_HOME=./runtime python -m panelpro start --dev
```

Then open the printed URL (dev entry path is generated on first run; find it
with `sqlite3 runtime/data/panel.db "select value from settings where key='entry_path'"`).

## Tests & lint

```bash
pytest
ruff check panelpro
```
