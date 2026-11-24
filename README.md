# PanelPro

**PanelPro** is an open-source Linux server control panel — manage websites,
databases, files, SSL certificates, cron jobs, firewalls, Docker and more
from one clean web interface.

> This project is **written entirely from scratch** as an original work.
> It is *category-similar* to other hosting panels (website/db/SSL/FTP
> management is a common product category), but every line of code, the
> architecture, the UI design, all templates and all documentation are
> original to this repository. Licensed under MIT.

![stack](https://img.shields.io/badge/python-3.10%2B-blue)
![stack](https://img.shields.io/badge/backend-FastAPI-teal)
![stack](https://img.shields.io/badge/frontend-Vue%203%20no--build-42b883)
![license](https://img.shields.io/badge/license-MIT-green)

---

## ✨ Feature Overview

| Module | Highlights |
| --- | --- |
| 🌐 **Websites** | nginx **and** Apache vhosts, alias domains, reverse proxy, per-site PHP version, vhost editor, per-site logs, force HTTPS |
| 🗄️ **Databases** | MySQL/MariaDB, PostgreSQL, Redis, MongoDB — create/delete DBs & users, grants, encrypted root password |
| 🐘 **PHP** | Multi-version detection/install, extensions, php.ini editor per SAPI, FPM pool tuning |
| 📂 **Files** | Full file manager: browse, editor, upload/download, zip/tar.gz, chmod/chown, safe trash, search, archive-extract path protection |
| 🔒 **SSL** | Let's Encrypt (certbot webroot), self-signed (cryptography), custom upload with key-match verification, expiry monitor + auto-renew, one-click deploy to sites or the panel itself |
| 🛡️ **Security** | ufw / firewalld / iptables adapter, IP blocking, ICMP toggle, SSH port changer, fail2ban status, secret entry path, login throttling, 2FA |
| ⏰ **Cron** | Marker-based crontab engine, shell/URL/script tasks, run-now, per-job logs, next-run preview |
| 📈 **Monitor** | psutil realtime + 7-day history (CPU/mem/disk/net/load), top processes, threshold alerts |
| 🐳 **Docker** | Containers, images, volumes, networks, stats, exec, logs, compose support |
| 🛍️ **App Store** | Manifest-driven one-click installers: WordPress, phpMyAdmin, Nextcloud, Portainer, Uptime Kuma, n8n, Redis Commander, Grafana |
| 💾 **Backups** | Scheduled jobs (sites + DB dumps → tar.gz), retention, targets: local / SFTP / rclone, safe restore |
| ⌨️ **Terminal** | WebSocket SSH (paramiko) + xterm.js |
| 🔔 **Notifications** | Webhook, Telegram, SMTP; events: login fail, disk/CPU thresholds, SSL expiry, backups |
| 👥 **Users** | Multi-user with roles (admin/operator/viewer) + scoped API keys |
| 🧩 **Plugins** | Drop-in FastAPI router plugins with a sample plugin and docs |
| 🩺 **Daemon Guard** | Process/port/pidfile/service watchdog with auto-restart + Telegram/webhook alerts |
| 📊 **Traffic Stats** | Per-site access-log analytics: PV/UV, bandwidth, spiders, top IPs/URLs, daily charts |
| 🧱 **WAF** | Per-site nginx rules: CC rate limiting, IP and user-agent blocklists, generated conf with `nginx -t` rollback |
| 🔐 **Tamper Protection** | SHA-256 file-integrity baselines per site, scheduled scans, optional auto-restore from snapshot |
| ⚖️ **Load Balancer** | nginx upstream pools (`upstream:<name>` proxy targets) with weight tuning |
| 🚚 **Migration** | One-bundle export (sites + DB dumps + certs) and import on a new server |
| 🗃️ **Replication** | MySQL master→slave setup wizard with live lag/status monitoring |
| 🖥️ **Multi-Server** | Fleet: monitor multiple PanelPro nodes from one master via API keys |
| 🌐 **Wildcard SSL** | Let's Encrypt DNS-01 (Cloudflare, DigitalOcean, DNSPod, Aliyun, GoDaddy) for `*.domain` certificates |

**Panel security design**: bcrypt passwords, HttpOnly + SameSite=Strict
sessions, CSRF header protection, per-IP rate limiting + brute-force
lockout, secret entry URL, audit log of every mutating request, encrypted
secrets at rest (DNS API credentials, fleet API keys, DB passwords),
security headers. Headless API clients authenticate with `Authorization:
Bearer ppk_…` and work without the entry cookie. See
[docs/SECURITY.md](docs/SECURITY.md).

## 🚀 Quick Start (Linux server)

```bash
sudo bash scripts/install.sh --stack nginx --port 21000
```

Run from the project checkout on an Ubuntu or Debian VPS. Use `--stack php`
for PHP-FPM and MariaDB. The panel listens on loopback by default. Connect with
`ssh -N -L 21000:127.0.0.1:21000 user@server`, then open the URL printed by
the installer. Initial credentials are stored in
`/usr/local/panelpro/data/admin_credentials.txt`.

From **Websites → Add Website**, choose **Static website**, **PHP-FPM**, or
**Reverse proxy**. Once DNS points at the VPS, open **SSL / HTTPS** on the site
to issue a Let's Encrypt certificate.

Dev mode (any OS, for API/frontend work):

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
PANELPRO_HOME=./runtime PANELPRO_WWW_ROOT=./runtime/www python -m panelpro start --dev
```

## 🧭 Documentation

| Doc | Content |
| --- | --- |
| [docs/INSTALL.md](docs/INSTALL.md) | Install, update, uninstall, CLI reference |
| [docs/API.md](docs/API.md) | REST API overview + OpenAPI `/docs` |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Backend/frontend layout, data flow |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model & hardening checklist |
| [docs/PLUGINS.md](docs/PLUGINS.md) | Writing plugins |

## 🧪 Development

```bash
pip install -e ".[dev]"
pytest                  # unit tests (OS-specific tests skip automatically)
ruff check panelpro     # lint
scripts/vendor_assets.sh  # optional: vendor Vue/xterm for offline UI
```

## ⚖️ Originality & License

Nothing in this repository is copied from any other control panel. The
feature *category* (web/DB/SSL management for servers) is generic; all
implementation, naming, design and text are original. Third-party runtime
dependencies (FastAPI, psutil, paramiko, Vue, xterm.js, …) are used under
their own open-source licenses.

Released under the [MIT License](LICENSE).
