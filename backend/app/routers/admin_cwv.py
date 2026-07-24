"""Endpoints administrativos do CWV. Gated por X-Admin-Token."""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db
from app.models.cwv_analise import CwvAnalise
from app.services.cwv_kb import (
    AUDIT_ALIASES,
    listar_kb_codigos,
    mapeamento_audit_kb_com_aliases,
    recarregar_kb,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_admin_token(x_admin_token: str | None) -> None:
    if not settings.cwv_admin_reload_token:
        raise HTTPException(status_code=403, detail="Endpoint admin desabilitado")
    if x_admin_token != settings.cwv_admin_reload_token:
        raise HTTPException(status_code=403, detail="Token invalido")


@router.post("/admin/cwv/kb/reload")
async def reload_kb(
    x_admin_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin_token(x_admin_token)
    recarregar_kb()
    codigos = listar_kb_codigos()
    # SPEC_CWV_Cache_Classificacao_Audit_KB: invalida cache coberto por novo direto.
    diretos = mapeamento_audit_kb_com_aliases()
    n_invalidados = 0
    try:
        from app.services.cwv_audit_kb_cache import invalidar_cobertos_por_direto

        n_invalidados = await invalidar_cobertos_por_direto(db, diretos)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("Falha ao invalidar cache na recarga da KB", exc_info=True)
    logger.info(
        "CWV KB recarregada: %d codigos, %d entradas de cache invalidadas",
        len(codigos), n_invalidados,
    )
    return {"reloaded": True, "n_codigos": len(codigos), "n_cache_invalidados": n_invalidados}


@router.get("/admin/cwv/audit-kb-cache")
async def listar_audit_kb_cache(
    x_admin_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    offset: int = 0,
    limit: int = 100,
) -> dict:
    """SPEC_CWV_Cache_Classificacao_Audit_KB: lista o cache LLM→KB."""
    _require_admin_token(x_admin_token)
    from app.services.cwv_audit_kb_cache import listar_tudo

    items, total = await listar_tudo(db, offset=offset, limit=limit)
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.delete("/admin/cwv/audit-kb-cache/{audit_id}")
async def invalidar_audit_kb_cache(
    audit_id: str,
    x_admin_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """SPEC_CWV_Cache_Classificacao_Audit_KB: invalida UMA entrada — próxima
    análise reclassifica via LLM."""
    _require_admin_token(x_admin_token)
    from app.services.cwv_audit_kb_cache import invalidar

    removido = await invalidar(db, audit_id)
    await db.commit()
    return {"audit_id": audit_id, "invalidado": removido}


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
    # Health check não pode estourar 500 quando o banco cai — reporta "down".
    db_disponivel = True
    total = n_ok = n_falhas = 0
    try:
        total, n_ok, n_falhas = (await db.execute(stmt)).one()
        total = int(total)
        n_ok = int(n_ok)
        n_falhas = int(n_falhas)
    except Exception:
        db_disponivel = False
        logger.warning("cwv_health: banco indisponivel", exc_info=True)
    taxa_sucesso = round(n_ok / total, 3) if (db_disponivel and total) else None

    overall = "ok"
    if not db_disponivel or (not psi_status["key1_available"] and not psi_status["key2_available"]):
        overall = "down"
    elif (total > 0 and taxa_sucesso is not None and taxa_sucesso < 0.8) or not llm_status["openai_configured"]:
        overall = "degraded"

    return {
        "status": overall,
        "db_disponivel": db_disponivel,
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
