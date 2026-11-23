# Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  Browser SPA (web/) — Vue 3 global build, no build step            │
│  hash-router + PP.* namespace: api, store, ui, charts, i18n        │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ fetch /api/*  (cookie or Bearer key)
┌──────────────────────────────▼─────────────────────────────────────┐
│  FastAPI (panelpro/main.py)                                        │
│  middlewares: SecurityHeaders → EntryGate → RateLimit → Audit      │
│  api/ routers (21 modules) — auth, roles, pydantic validation      │
└──────────┬───────────────────────────────┬─────────────────────────┘
           │                               │
┌──────────▼──────────┐         ┌──────────▼──────────────────────┐
│ core/               │         │ services/                       │
│ security (bcrypt,   │         │ webservers (nginx/apache jinja2)│
│ sessions, TOTP)     │         │ dbmgr (mysql/pg/redis/mongo)    │
│ keyvault (Fernet)   │         │ phpmgr, ftpmgr, firewall        │
│ monitor (psutil)    │         │ cronsvc (crontab markers)       │
│ scheduler (threads) │         │ sslmgr (certbot/self-signed)    │
│ notify (webhook/tg/ │         │ dockermgr, apps, backupsvc      │
│ smtp) syscmd, fsutil│         │ systemd                         │
└──────────┬──────────┘         └──────────┬──────────────────────┘
           │                               │
      ┌────▼─────┐                   ┌─────▼─────────────┐
      │ SQLite   │                   │ OS: systemctl,    │
      │ panel.db │                   │ crontab, docker,  │
      └──────────┘                   │ nginx, mysql…     │
                                     └───────────────────┘
```

## Key decisions

* **Single process, daemon threads** — the panel runs as one uvicorn
  process; monitoring and scheduled jobs are daemon threads started in the
  app lifespan. Simple, robust, easy to package.
* **DB is the source of truth for sites/users/crons**; the OS is updated
  through service adapters, and config files are rendered from original
  Jinja2 templates (`panelpro/templates/`).
* **Crontab markers** (`# pp:<id>`) let the panel coexist with manual
  crontab entries without clobbering them.
* **Secrets** (DB root passwords, Redis password) are encrypted with a
  Fernet key stored in `data/secret.key` (0600).
* **No build step frontend** — plain scripts on a `PP.*` namespace served
  statically by FastAPI; optional local vendor copies for offline use.
* **Graceful degradation** — on non-Linux/dev environments, OS-specific
  endpoints return clear errors instead of crashing; unit tests skip
  OS-specific parts automatically.

## Request lifecycle (example: create site)

1. `POST /api/sites` → EntryGate (cookie) → RateLimit → Audit middleware.
2. `require_role("operator")` resolves session/API key, enforces CSRF
   header, stamps the user into the scope for the audit row.
3. Router validates the domain, creates `Site` row, creates the web root,
   renders `nginx_site.conf.j2` via `services/webservers.py`, runs
   `nginx -t`, reloads, notifies `site_created`.
4. Audit middleware records user/ip/method/path/status/duration.
