"""Endpoints administrativos do CWV. Gated por X-Admin-Token."""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db
from app.models.cwv_analise import CwvAnalise
from app.services.cwv_kb import AUDIT_ALIASES, listar_kb_codigos, recarregar_kb

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_admin_token(x_admin_token: str | None) -> None:
    if not settings.cwv_admin_reload_token:
        raise HTTPException(status_code=403, detail="Endpoint admin desabilitado")
    if x_admin_token != settings.cwv_admin_reload_token:
        raise HTTPException(status_code=403, detail="Token invalido")


@router.post("/admin/cwv/kb/reload")
async def reload_kb(x_admin_token: str | None = Header(default=None)) -> dict:
    _require_admin_token(x_admin_token)
    recarregar_kb()
    codigos = listar_kb_codigos()
    logger.info("CWV KB recarregada: %d codigos", len(codigos))
    return {"reloaded": True, "n_codigos": len(codigos)}


@router.get("/admin/cwv/health")
async def cwv_health(
    x_admin_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin_token(x_admin_token)

    psi_keys = [settings.api_psi_key, settings.api_psi_key2]
    psi_status = {
        "key1_available": bool(psi_keys[0]),
        "key2_available": bool(psi_keys[1]) if len(psi_keys) > 1 else False,
        "quota_remaining_estimate": "unknown",
        "last_error": None,
    }

    llm_status = {
        "openai_configured": bool(settings.openai_api_key),
        "analisador_model": settings.cwv_analisador_llm_model,
        "pesquisador_model": settings.cwv_pesquisador_llm_model,
    }

    kb_codigos = listar_kb_codigos()

    janela = datetime.now(UTC) - timedelta(hours=24)
    stmt = select(
        func.count(CwvAnalise.id),
        func.coalesce(
            func.sum(case((CwvAnalise.status == "sucesso", 1), else_=0)), 0,
        ),
        func.coalesce(
            func.sum(case((CwvAnalise.status == "falhou_psi", 1), else_=0)), 0,
        ),
    ).where(CwvAnalise.criado_em >= janela)
    total, n_ok, n_falhas = (await db.execute(stmt)).one()
    total = int(total)
    n_ok = int(n_ok)
    n_falhas = int(n_falhas)
    taxa_sucesso = round(n_ok / total, 3) if total else None

    overall = "ok"
    if not psi_status["key1_available"] and not psi_status["key2_available"]:
        overall = "down"
    elif total > 0 and taxa_sucesso is not None and taxa_sucesso < 0.8:
        overall = "degraded"
    elif not llm_status["openai_configured"]:
        overall = "degraded"

    return {
        "status": overall,
        "psi": psi_status,
        "llm": llm_status,
        "kb": {
            "entries_loaded": len(kb_codigos),
            "aliases": len(AUDIT_ALIASES),
        },
        "ultimas_24h": {
            "analises_total": total,
            "analises_sucesso": n_ok,
            "analises_falhou_psi": n_falhas,
            "taxa_sucesso": taxa_sucesso,
        },
        "alerta_webhook_configurado": bool(settings.cwv_alerta_webhook_url),
    }
