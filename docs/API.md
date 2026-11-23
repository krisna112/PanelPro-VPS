# REST API Overview

The panel serves its own API under `/api/*` (same origin). A full,
always-up-to-date schema is available at **`/docs`** (OpenAPI/Swagger) on
your panel URL — protected by the same entry-path gate as the UI.

Response envelope:

```json
{ "ok": true, "data": { ... } }
{ "ok": false, "message": "human readable error" }
```

## Authentication

* **Browser session** — `POST /api/auth/login` sets an HttpOnly cookie.
  All mutating browser requests must carry the `X-PP-Request: 1` header
  (the SPA adds it automatically) as CSRF protection.
* **API keys** — `Authorization: Bearer ppk_…` header. Create keys under
  *Users → API Keys*; each key carries a role (admin/operator/viewer).

Roles: `viewer` (read-only) < `operator` (manage) < `admin` (everything).

## Endpoint map

| Module | Endpoints |
| --- | --- |
| auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `GET/DELETE /auth/sessions…`, `POST /auth/password`, `POST /auth/2fa/{setup,enable,disable}` |
| dashboard | `GET /dashboard/summary` |
| system | `GET /system/info`, `GET /system/services`, `POST /system/services/{unit}/{action}`, `GET /system/services/{unit}/journal`, `GET /system/processes`, `POST /system/processes/kill`, `POST /system/panel/update` |
| files | `GET /files/list|read|search|download`, `POST /files/write|mkdir|rename|copy|delete|chmod|chown|compress|extract|upload|trash-empty` |
| sites | `GET /sites`, `POST /sites`, `POST /sites/{id}/{delete,toggle,conf,domains,domains/remove,proxy,php,https,ssl,logs,reload}`, `GET /sites/server-status` |
| databases | `GET /databases`, `GET /databases/engines`, `POST /databases`, `POST /databases/{name}/delete`, `GET/POST /databases/users…`, `GET /databases/redis/info`, `POST /databases/redis/password`, `POST /databases/root-password` |
| php | `GET /php/versions`, `GET/POST /php/versions/{v}/…` (extensions, ini, pool, restart), `POST /php/install` |
| ftp | `GET/POST /ftp`, `POST /ftp/{id}/{password,delete}` |
| ssl | `GET /ssl`, `POST /ssl/{letsencrypt,selfsigned,custom,renew}`, `POST /ssl/{id}/{deploy,delete,verify}` |
| security | `GET /security/status|ssh-port`, `POST /security/firewall/{allow,remove,enable,disable}`, `POST /security/{block,unblock,ping,ssh-port}` |
| cron | `GET/POST /cron`, `POST /cron/{id}/{update,toggle,delete,run}`, `GET /cron/{id}/log` |
| monitor | `GET /monitor/{realtime,history,disks,processes}` |
| logs | `GET /logs/sources`, `GET /logs/tail`, `GET /logs/download` |
| apps | `GET /apps`, `POST /apps/install`, `POST /apps/{id}/{uninstall,status}` |
| docker | `GET /docker/{status,containers,images,volumes,networks,stats}`, `POST /docker/containers/{name}/{action}`, `GET /docker/containers/{name}/logs`, `POST /docker/containers/{name}/exec`, `POST /docker/images/{pull,remove,prune}` |
| backup | `GET /backup/{jobs,runs,files,archive-members}`, `POST /backup/jobs…`, `POST /backup/jobs/{id}/{run,toggle,delete,update}`, `POST /backup/restore`, `GET /backup/download` |
| terminal | `GET /api/terminal/status`, `WS /api/terminal/ws` (send `{username,password,cols,rows}` first) |
| settings | `GET/POST /settings`, `POST /settings/panel-ssl` |
| users | `GET/POST /users`, `POST /users/{id}/{update,delete}`, `GET/POST /users/keys`, `POST /users/keys/{id}/delete` |
| notifications | `GET /notifications/{events,channels}`, `POST /notifications/channels…`, `POST /notifications/channels/{id}/{update,delete,test}` |
| plugins | `GET /plugins` |

Health check (no auth): `GET /api/health`.

## Rate limits

Per IP, sliding window: 300 req/min general, 10 req/min on
`/api/auth/login`. Exceeding returns HTTP 429.
