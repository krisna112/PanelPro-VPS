# Changelog

All notable changes to PanelPro are documented here.
Format based on Keep a Changelog; versioning: SemVer.

## [1.1.0] - 2026-11-23

Pro feature pack (9 modules) + security hardening from the full audit.

### Added — Pro modules
- **Daemon Guard** (`/api/daemon`): watchdog tasks for systemd units,
  pidfiles, TCP ports and commands; auto-restart + cooldown alerts.
- **Traffic Stats** (`/api/traffic`): combined-format access-log parser,
  incremental byte-offset collection, daily PV/UV/bytes/spider/errors
  aggregation with top IPs/URLs, canvas chart UI.
- **WAF** (`/api/waf`): per-site nginx CC rate-limit zones + IP/UA
  blocklists, generated conf files validated with `nginx -t`, vhost
  template include, strict IP/regex whitelisting.
- **Load Balancer** (`/api/lb`): nginx upstream pools rendered to
  conf.d, `upstream:<name>` proxy targets, weight tuning.
- **Tamper Protection** (`/api/tamper`): SHA-256 baselines + file
  snapshots per site, scheduled scans, optional auto-restore.
- **Migration** (`/api/migration`): single-bundle export (sites + DB
  dumps + certs + manifest) and guided import; async with status polling
  and download.
- **MySQL Replication** (`/api/replication`): master setup with encrypted
  replication credentials, CHANGE MASTER slave onboarding, live
  lag/status.
- **Fleet / Multi-Server** (`/api/fleet`): control other PanelPro nodes
  via API keys; aggregated CPU/mem/disk overview, connection tests.
- **Wildcard SSL via DNS-01** (`/api/ssl/dns-accounts`): Let's Encrypt
  certificates for `*.domain` using Cloudflare/DigitalOcean/DNSPod/
  Aliyun/GoDaddy; credentials encrypted at rest (Fernet), temp creds
  file 0600 and removed after issuance.
- File manager opens in `/www/wwwroot` (aaPanel parity) with a shortcut.

### Security (audit fixes)
- Whitelisted charsets for `CREATE DATABASE` (blocks SQL injection via
  the charset parameter on MySQL root / postgres superuser).
- Cron tasks: `shlex.quote()`d URL/script commands, newline/empty
  command and multiline schedule rejection (blocks crontab + shell
  injection), graceful error when `crontab` is missing.
- Self-signed certificates: fixed `random_serial_number()` (feature was
  broken) and strict domain validation (blocks path traversal into the
  ssl store and letsencrypt live dir).
- Entry gate now admits `Authorization: Bearer ppk_…` API-key clients,
  making the REST API usable headless (CI, fleet, monitoring).
- Hardened tar/zip extraction: symlink/hardlink target validation and
  exact-prefix path checks (zip-slip/tar-slip).

### Changed
- 8 new UI pages (PanelPro Pro menu group), i18n ID/EN for all of them.
- Site deletion now cleans up WAF profiles, tamper watches and traffic
  stats.
- 36 new API routes; 21 new unit tests (62 total).

## [1.0.0] - 2026-11-23

Initial release. Original project, written from scratch.

### Added
- Backend: FastAPI app with 21 API modules (auth/2FA/API keys, dashboard,
  system/services, file manager, sites (nginx+Apache), databases
  (MySQL/PostgreSQL/Redis/MongoDB), PHP multi-version, FTP, SSL (LE +
  self-signed + custom), security (firewall/SSH/ping/fail2ban), cron,
  monitor, logs, app store, Docker, backups, web terminal (WS+SSH),
  settings, users/roles, notifications, plugin loader).
- Security: bcrypt, session cookies, CSRF header, rate limiting,
  entry-path gate, audit log, encrypted secrets, security headers.
- Frontend: Vue 3 no-build SPA, original CSS design system (dark/light),
  original canvas charts, i18n ID/EN, ~20 pages.
- Ops: install/update/uninstall scripts, systemd unit, `panelpro` CLI,
  vendor script for offline assets.
- Tests (pytest) and CI (ruff + pytest).
