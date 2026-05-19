import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import FileResponse, RedirectResponse

from app.config import settings
from app.core.middleware import CSRFMiddleware, SecurityHeadersMiddleware
from app.routers import (
    auth,
    auth_mfa_dispositivos,
    billing,
    clientes,
    creditos,
    ferramentas,
    ferramentas_inlinks,
    ferramentas_inlinks_reversos,
    health,
    imagens,
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "out"
logger = logging.getLogger(__name__)


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
application.include_router(creditos.router, prefix="/api/creditos", tags=["creditos"])
application.include_router(billing.router, prefix="/api/billing", tags=["billing"])
application.include_router(health.router, tags=["health"])
application.include_router(imagens.router, prefix="/api", tags=["imagens"])

if FRONTEND_DIR.is_dir():
    application.mount("/_next", StaticFiles(directory=str(FRONTEND_DIR / "_next")), name="next-static")

    _DYNAMIC_SEGMENTS = [
        (re.compile(r"^ferramentas/historico/[\w-]+$"), "ferramentas/historico/placeholder.html"),
        (re.compile(r"^clientes/[\w-]+$"), "clientes/placeholder.html"),
    ]

    @application.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    async def serve_spa(request: Request, full_path: str):
        if full_path == "":
            return RedirectResponse("/login", status_code=302)
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        html_path = FRONTEND_DIR / (full_path + ".html")
        if html_path.is_file():
            return FileResponse(str(html_path))
        for pattern, fallback in _DYNAMIC_SEGMENTS:
            if pattern.match(full_path):
                fallback_path = FRONTEND_DIR / fallback
                if fallback_path.is_file():
                    return FileResponse(str(fallback_path))
        dir_path = FRONTEND_DIR / full_path
        if dir_path.is_dir():
            index_path = dir_path / "index.html"
            if index_path.is_file():
                if not full_path.endswith("/"):
                    return RedirectResponse(f"/{full_path}/", status_code=301)
                return FileResponse(str(index_path))
        return FileResponse(str(FRONTEND_DIR / "index.html"))

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
