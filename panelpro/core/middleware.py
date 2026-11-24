"""HTTP middlewares: security headers, entry-path gate, rate limit, audit.

Request flow (outermost first):

    SecurityHeaders -> EntryGate -> RateLimit -> Audit -> routes
"""

from __future__ import annotations

import threading
import time
from collections import deque

from starlette.responses import JSONResponse

from panelpro.constants import ENTRY_COOKIE
from panelpro.core import keyvault, settings_store
from panelpro.core.database import SessionLocal
from panelpro.models.tables import AuditLog

# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]


class SecurityHeadersMiddleware:
    """Adds hardened response headers to every HTTP response."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(SECURITY_HEADERS)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ---------------------------------------------------------------------------
# Entry-path gate ("URL obscurity" defence layer)
# ---------------------------------------------------------------------------

ENTRY_COOKIE_MAX_AGE = 12 * 3600


class EntryGateMiddleware:
    """Masks the panel unless the visitor knows the secret entry path.

    * ``/api/health``, ``/assets/*`` and ``/favicon.svg`` are always served.
    * ``GET /<entry>`` (and anything under it) sets a signed entry cookie.
    * Every other request without the cookie gets an anonymous 404.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        if (
            path == "/api/health"
            or path.startswith("/assets/")
            or path == "/favicon.svg"
        ):
            return await self.app(scope, receive, send)

        cookie_value = ""
        has_api_key_header = False
        for raw_key, raw_val in scope.get("headers", []):
            if raw_key.lower() == b"cookie":
                for part in raw_val.decode("latin-1").split(";"):
                    k, _, v = part.strip().partition("=")
                    if k == ENTRY_COOKIE:
                        cookie_value = v
                        break
            elif raw_key.lower() == b"authorization":
                # Headless API clients (and fleet nodes) authenticate with a
                # Bearer key; the gate only checks the prefix — the real key
                # check happens in deps.authenticate.
                if raw_val.decode("latin-1").strip().startswith("Bearer ppk_"):
                    has_api_key_header = True
        if cookie_value and keyvault.verify_signature("entry-ok", cookie_value):
            return await self.app(scope, receive, send)
        if has_api_key_header and path.startswith("/api/"):
            return await self.app(scope, receive, send)

        entry = str(settings_store.get_setting("entry_path") or "")
        is_entry_path = bool(entry) and (
            path == f"/{entry}" or path.startswith(f"/{entry}/")
        )
        if is_entry_path and scope.get("method") == "GET":
            secure = "; Secure" if scope.get("scheme") == "https" else ""
            cookie_header = (
                f"{ENTRY_COOKIE}={keyvault.sign('entry-ok')}; Path=/; HttpOnly; "
                f"SameSite=Strict; Max-Age={ENTRY_COOKIE_MAX_AGE}{secure}"
            ).encode("latin-1")

            async def send_with_cookie(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"set-cookie", cookie_header))
                    message["headers"] = headers
                await send(message)

            return await self.app(scope, receive, send_with_cookie)

        response = JSONResponse({"ok": False, "message": "Not found"}, status_code=404)
        await response(scope, receive, send)


# ---------------------------------------------------------------------------
# Rate limiting (per IP, in-memory sliding window)
# ---------------------------------------------------------------------------

GENERAL_LIMIT = 300        # requests per minute, everything else
LOGIN_LIMIT = 10           # requests per minute, /api/auth/login


class RateLimitMiddleware:
    def __init__(self, app) -> None:
        self.app = app
        self._buckets: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _allow(self, key: str, limit: int) -> bool:
        now = time.time()
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] < now - 60:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            if len(self._buckets) > 5000:  # keep memory bounded
                self._buckets.clear()
            return True

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        client = scope.get("client") or ("unknown", 0)
        ip = str(client[0])
        path = scope.get("path", "")

        if not path.startswith("/api") or path == "/api/health":
            return await self.app(scope, receive, send)

        limit = LOGIN_LIMIT if path == "/api/auth/login" else GENERAL_LIMIT
        if not self._allow(f"{ip}:{'login' if path == '/api/auth/login' else 'api'}", limit):
            response = JSONResponse(
                {"ok": False, "message": "Too many requests, slow down."},
                status_code=429,
            )
            return await response(scope, receive, send)

        return await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Audit log for mutating API calls
# ---------------------------------------------------------------------------


class AuditMiddleware:
    """Persists every mutating /api call into the audit_logs table."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")
        if method not in ("POST", "PUT", "DELETE", "PATCH") or not path.startswith("/api"):
            return await self.app(scope, receive, send)

        start = time.time()
        status_code = 0

        async def send_capture(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        await self.app(scope, receive, send_capture)

        db = SessionLocal()
        try:
            db.add(
                AuditLog(
                    username=str(scope.get("pp_user") or ""),
                    ip=str((scope.get("client") or ("unknown", 0))[0]),
                    method=method,
                    path=path[:255],
                    status=status_code,
                    duration_ms=int((time.time() - start) * 1000),
                    detail="",
                )
            )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
