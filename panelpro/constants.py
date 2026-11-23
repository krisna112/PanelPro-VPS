"""Project-wide constants for PanelPro."""

APP_NAME = "PanelPro"
VERSION = "1.0.0"
DESCRIPTION = "Open-source Linux server control panel — manage sites, databases, files, SSL and more from one place."

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
# Higher number = more privileges.
ROLES = {"viewer": 0, "operator": 1, "admin": 2}

# ---------------------------------------------------------------------------
# Network / install defaults
# ---------------------------------------------------------------------------
DEFAULT_PANEL_PORT = 21000
DEFAULT_WWW_ROOT = "/www/wwwroot"
DEFAULT_BACKUP_DIR = "/www/backup"
KNOWN_SERVICES = [
    "nginx", "apache2", "httpd", "mysqld", "mariadb", "mysql",
    "postgresql", "redis-server", "redis", "mongod", "docker",
    "sshd", "ssh", "pure-ftpd", "pure-ftpd-mysql", "proftpd",
    "fail2ban", "ufw", "firewalld", "crond", "cron",
]

# ---------------------------------------------------------------------------
# Sessions / security
# ---------------------------------------------------------------------------
SESSION_COOKIE = "pp_sid"
ENTRY_COOKIE = "pp_entry"
CSRF_HEADER = "x-pp-request"
SESSION_TTL_HOURS = 12
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 10
API_KEY_PREFIX = "ppk_"

# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------
MONITOR_SAMPLE_INTERVAL = 10   # seconds between live samples
MONITOR_FLUSH_INTERVAL = 60    # seconds between database flushes
MONITOR_RETENTION_DAYS = 7
MONITOR_HISTORY_POINTS = 8640  # ~24h of samples kept in memory

# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
MAX_TEXT_EDIT_BYTES = 5 * 1024 * 1024      # 5 MB text editor cap
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB upload cap
SEARCH_MAX_RESULTS = 500

# ---------------------------------------------------------------------------
# Notification events
# ---------------------------------------------------------------------------
NOTIFY_EVENTS = [
    "login_failed",
    "login_success",
    "ssl_expiry",
    "disk_high",
    "cpu_high",
    "backup_done",
    "backup_failed",
    "site_created",
    "site_deleted",
    "app_installed",
]
