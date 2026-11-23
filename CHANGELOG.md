# Changelog

All notable changes to PanelPro are documented here.
Format based on Keep a Changelog; versioning: SemVer.

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
