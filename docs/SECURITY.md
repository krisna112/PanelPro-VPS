# Security Model & Hardening Checklist

## Built-in protections

| Layer | Mechanism |
| --- | --- |
| Passwords | bcrypt (per-user salt), min length 8, change revokes sessions |
| Sessions | opaque 32-byte tokens, HttpOnly + SameSite=Strict cookies, 12h expiry, server-side revocation |
| CSRF | mutating browser requests require `X-PP-Request: 1` (cross-site forms/fetches cannot set custom headers) |
| Brute force | 5 failed logins per IP per 10 min → 429; failed logins trigger notifications |
| Rate limiting | per-IP sliding window (300/min general, 10/min login) |
| URL obscurity | panel + API masked with anonymous 404 until the signed entry-path cookie is set by visiting `/<entry>` |
| 2FA | TOTP (RFC 6238) per user; login requires a valid code when enabled |
| Authorization | roles: viewer < operator < admin; enforced per-endpoint |
| Audit | every mutating request logged (user, IP, method, path, status, duration) |
| Secrets at rest | DB root password, Redis password encrypted (Fernet, key file 0600) |
| Shell safety | subprocess uses argument lists (no shell interpolation); app install scripts are the explicit exception, rendered by the panel |
| File manager | absolute paths only, `..` rejected, archive extraction blocks path escapes, trash instead of hard delete |
| Headers | nosniff, DENY frames, no-referrer, restrictive permissions-policy |
| Uploads | 2 GB cap, streamed to disk in 1 MB chunks |
| API keys | stored as SHA-256 hashes, shown once, scoped by role, revocable |

## Recommended hardening (operator checklist)

1. Serve the panel behind HTTPS: upload a cert in *Settings → Panel SSL*
   (secure cookie flag activates automatically) or put nginx/Caddy with TLS
   in front and set `trust_proxy`.
2. Keep the **entry path secret**; treat it as a first defense layer, not
   the only one — enable 2FA for all admin users.
3. Restrict panel access with the firewall / `ip_allowlist` setting when
   only certain networks need the panel.
4. Delete `data/admin_credentials.txt` right after the first login.
5. Schedule backups (Backups module) and verify restore once.
6. Keep the host patched; run `panelpro doctor` after major system changes.

## Known trade-offs (documented on purpose)

* The file manager runs with the panel's privileges (root) by design —
  panels are root-level tools; use roles to reduce who can operate.
* App-store install scripts execute as root (like any one-click installer);
  manifests ship in-repo so they are reviewable before use.
* `X-Frame-Options: DENY` and strict cookies mean the panel must be used
  directly (no iframe embedding).
