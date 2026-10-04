"""Security headers, request IDs and audit logging middleware."""

from __future__ import annotations

import time
import uuid

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from backend.security.rate_limit import rate_limit_key
from backend.utils.logging import get_logger, request_id_ctx
from backend.utils.metrics import HTTP_LATENCY, HTTP_REQUESTS

log = get_logger("suraksha.access")

_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
_SKIP_AUDIT = ("/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=(self)")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if request.url.path.startswith(_DOCS_PATHS):
            # Swagger UI loads its assets from jsdelivr.
            h.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com",
            )
        else:
            h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if request.url.scheme == "https":
            h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, logs access and writes audit rows for state-changing calls."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        rid = rid[:64]
        token = request_id_ctx.set(rid)
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            elapsed = time.perf_counter() - start
            elapsed_ms = round(elapsed * 1000, 1)
            route = getattr(request.scope.get("route"), "path", None) or "unmatched"
            if route != "/metrics":
                HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
                HTTP_LATENCY.labels(request.method, route).observe(elapsed)
            log.info("%s %s -> %s (%sms)", request.method, request.url.path, status_code, elapsed_ms)
            path = request.url.path
            if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not path.startswith(_SKIP_AUDIT):
                await run_in_threadpool(_write_audit, request, status_code, rid, elapsed_ms)
            request_id_ctx.reset(token)


def _write_audit(request: Request, status_code: int, rid: str, elapsed_ms: float) -> None:
    from backend.services.audit_service import record_audit

    key = rate_limit_key(request)
    user_id = key.split(":", 1)[1] if key.startswith("user:") else None
    record_audit(
        action="http_request",
        user_id=user_id,
        method=request.method,
        path=request.url.path,
        status_code=status_code,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=rid,
        details={"elapsed_ms": elapsed_ms},
    )
