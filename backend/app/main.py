import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, RedirectResponse
from starlette.staticfiles import StaticFiles as StarletteStaticFiles
from starlette.types import Receive, Scope, Send

from app.config import settings
from app.core.middleware import CSRFMiddleware, SecurityHeadersMiddleware
from app.routers import (
    admin_cwv,
    auth,
    auth_mfa_dispositivos,
    billing,
    clientes,
    creditos,
    ferramentas,
    ferramentas_cwv,
    ferramentas_cwv_auditoria,
    ferramentas_inlinks,
    ferramentas_inlinks_reversos,
    ferramentas_parecer,
    ferramentas_seo_tecnico,
    health,
    imagens,
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "out"
logger = logging.getLogger(__name__)


class CachedStaticFiles(StarletteStaticFiles):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and path.startswith("/_next/static/"):
            scope = dict(scope)
            scope["headers"] = [
                (k, v) if k.lower() != b"cache-control"
                else (b"cache-control", b"public, max-age=31536000, immutable")
                for k, v in scope.get("headers", [])
            ]
        await super().__call__(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.logging import setup_logging

    setup_logging(settings.log_level)

    if settings.langsmith_api_key:
        import os

        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        logger.info("langsmith.enabled", extra={"event_type": "observability.langsmith", "project": settings.langsmith_project})

    if settings.sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
            profiles_sample_rate=0.05,
            environment=settings.ambiente,
        )
        logger.info("sentry.enabled", extra={"event_type": "observability.sentry"})

    logger.info("api_startup", extra={"event_type": "api.start", "ambiente": settings.ambiente})
    yield


application = FastAPI(title="SEO SaaS IA", version="1.0.0", lifespan=lifespan)

application.include_router(auth.router, prefix="/api/auth", tags=["auth"])
application.include_router(auth_mfa_dispositivos.router, prefix="/api/auth", tags=["auth"])
application.include_router(clientes.router, prefix="/api/clientes", tags=["clientes"])
application.include_router(ferramentas.router, prefix="/api/ferramentas", tags=["ferramentas"])
application.include_router(ferramentas_inlinks.router, prefix="/api/ferramentas", tags=["ferramentas"])
application.include_router(ferramentas_inlinks_reversos.router, prefix="/api/ferramentas", tags=["ferramentas"])
application.include_router(ferramentas_cwv.router, prefix="/api/ferramentas", tags=["ferramentas"])
application.include_router(ferramentas_cwv_auditoria.router, prefix="/api/ferramentas", tags=["ferramentas"])
application.include_router(ferramentas_parecer.router, prefix="/api/ferramentas", tags=["ferramentas"])
application.include_router(ferramentas_seo_tecnico.router, prefix="/api/ferramentas", tags=["ferramentas"])
application.include_router(admin_cwv.router, prefix="/api", tags=["admin"])
application.include_router(creditos.router, prefix="/api/creditos", tags=["creditos"])
application.include_router(billing.router, prefix="/api/billing", tags=["billing"])
application.include_router(health.router, tags=["health"])
application.include_router(imagens.router, prefix="/api", tags=["imagens"])

if FRONTEND_DIR.is_dir():
    application.mount("/_next", CachedStaticFiles(directory=str(FRONTEND_DIR / "_next")), name="next-static")

    _DYNAMIC_SEGMENTS = [
        (re.compile(r"^ferramentas/historico/[\w-]+$"), "ferramentas/historico/placeholder.html"),
        (re.compile(r"^ferramentas/parecer/[\w-]+$"), "ferramentas/parecer/placeholder.html"),
        (re.compile(r"^clientes/[\w-]+$"), "clientes/placeholder.html"),
        (re.compile(r"^ferramentas/core-web-vitals/execucao/[\w-]+$"), "ferramentas/core-web-vitals/execucao/placeholder.html"),
        (re.compile(r"^ferramentas/core-web-vitals/historico/[\w-]+$"), "ferramentas/core-web-vitals/historico/placeholder.html"),
        (re.compile(r"^ferramentas/core-web-vitals/url/[\w-]+$"), "ferramentas/core-web-vitals/url/placeholder.html"),
        # SPEC_CWV_Auditoria_UI_V2: deep-link/refresh da página da auditoria
        # (bug capturado no e2e — rota existia no front mas faltava o fallback).
        (re.compile(r"^ferramentas/core-web-vitals/auditoria/[\w-]+$"), "ferramentas/core-web-vitals/auditoria/placeholder.html"),
        # SEOTec: deep-link para página de detalhe da auditoria.
        (re.compile(r"^ferramentas/auditoria-seo-tecnico/[\w-]+$"), "ferramentas/auditoria-seo-tecnico/placeholder.html"),
    ]

    # HTML e payloads RSC (.txt) mudam a cada deploy e referenciam chunks com
    # hash — se o browser cachear, usuários ficam presos ao bundle antigo até
    # hard-refresh. no-cache = sempre revalidar (chunks em /_next/static seguem
    # immutable, então o custo é só o HTML).
    _NO_CACHE = {"Cache-Control": "no-cache"}

    def _spa_file(path, status_code: int = 200) -> FileResponse:
        p = str(path)
        if p.endswith((".html", ".txt")):
            return FileResponse(p, status_code=status_code, headers=_NO_CACHE)
        return FileResponse(p, status_code=status_code)

    @application.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    async def serve_spa(request: Request, full_path: str):
        if full_path == "":
            return RedirectResponse("/login", status_code=302)
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return _spa_file(file_path)
        html_path = FRONTEND_DIR / (full_path + ".html")
        if html_path.is_file():
            return _spa_file(html_path)
        for pattern, fallback in _DYNAMIC_SEGMENTS:
            if pattern.match(full_path):
                fallback_path = FRONTEND_DIR / fallback
                if fallback_path.is_file():
                    return _spa_file(fallback_path)
        dir_path = FRONTEND_DIR / full_path
        if dir_path.is_dir():
            index_path = dir_path / "index.html"
            if index_path.is_file():
                if not full_path.endswith("/"):
                    return RedirectResponse(f"/{full_path}/", status_code=301)
                return _spa_file(index_path)
        # Arquivos internos de dados/prefetch do Next (RSC) não são páginas: devolver
        # o SPA (200) em vez de 404, senão o prefetch de rotas dinâmicas loga 404 no console.
        if "__next" in full_path or "_rsc" in request.url.query:
            return _spa_file(FRONTEND_DIR / "index.html")

        # Rota não-casada: servir a página 404 estática (not-found.tsx) com status 404,
        # em vez de devolver index.html (que mascarava o 404 e caía no início).
        not_found = FRONTEND_DIR / "404.html"
        if not_found.is_file():
            return _spa_file(not_found, status_code=404)
        return _spa_file(FRONTEND_DIR / "index.html", status_code=404)

    @application.head("/{full_path:path}")
    async def serve_spa_head(request: Request, full_path: str):
        return await serve_spa(request, full_path)

wrapped = SecurityHeadersMiddleware(CSRFMiddleware(application))

app = CORSMiddleware(
    wrapped,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    max_age=600,
)
