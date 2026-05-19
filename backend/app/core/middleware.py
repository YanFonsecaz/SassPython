import secrets
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.core.seguranca import gerar_csrf_nonce

STATE_CHANGING_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        try:
            ip_obj = ip_address(request.client.host)
            if isinstance(ip_obj, (IPv4Address, IPv6Address)):
                return request.client.host
        except ValueError:
            pass
    return "unknown"


def is_private_ip(ip_str: str) -> bool:
    try:
        addr = ip_address(ip_str)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    except ValueError:
        return True


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        nonce = secrets.token_urlsafe(16)

        async def send_with_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"strict-transport-security", b"max-age=63072000; includeSubDomains; preload"))
                headers.append((b"referrer-policy", b"strict-origin-when-cross-origin"))
                headers.append((b"permissions-policy", b"camera=(), microphone=(), geolocation=()"))
                headers.append((b"x-csp-nonce", nonce.encode()))
                # /api/* retorna JSON. Frontend Next.js (export estatico) tem
                # scripts/styles inline sem nonce — precisa CSP mais permissivo.
                if path.startswith("/api/"):
                    csp_api = (
                        b"frame-ancestors 'none'; "
                        b"default-src 'self'; "
                        b"script-src 'self' 'nonce-" + nonce.encode() + b"' 'strict-dynamic'; "
                        b"style-src 'self' 'nonce-" + nonce.encode() + b"'; "
                        b"img-src 'self' data: https:; "
                        b"connect-src 'self'; "
                        b"font-src 'self' data:"
                    )
                    headers.append((b"content-security-policy", csp_api))
                else:
                    csp_html = (
                        b"frame-ancestors 'none'; "
                        b"default-src 'self'; "
                        b"script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                        b"style-src 'self' 'unsafe-inline'; "
                        b"img-src 'self' data: https: blob:; "
                        b"connect-src 'self'; "
                        b"font-src 'self' data:"
                    )
                    headers.append((b"content-security-policy", csp_html))
                if path.startswith("/api/"):
                    headers.append((b"cache-control", b"no-store, no-cache, must-revalidate, max-age=0"))
                has_ct = any(h[0].lower() == b"content-type" for h in headers)
                if not has_ct:
                    headers.append((b"content-type", b"application/json; charset=utf-8"))
                headers = [h for h in headers if h[0].lower() not in (b"server", b"x-powered-by")]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class CSRFMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        if request.method in SAFE_METHODS:
            nonce = gerar_csrf_nonce()

            async def send_with_nonce(message: dict[str, Any]) -> None:
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-csrf-nonce", nonce.encode()))
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_with_nonce)
            return

        if request.method in STATE_CHANGING_METHODS:
            if request.headers.get("authorization", "").startswith("Bearer "):
                await self.app(scope, receive, send)
                return

            path = request.url.path
            if path in (
                "/api/auth/login",
                "/api/auth/cadastro",
                "/api/auth/mfa/verificar",
                "/api/auth/refresh",
                "/api/auth/recuperar-senha",
                "/api/auth/resetar-senha",
            ):
                await self.app(scope, receive, send)
                return

            csrf_token = request.headers.get("x-csrf-token", "")
            csrf_cookie = request.cookies.get("csrf_token", "")
            if csrf_cookie and (not csrf_token or csrf_token != csrf_cookie):
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token invalido"},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
