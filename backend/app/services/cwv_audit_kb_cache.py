"""SPEC_CWV_Cache_Classificacao_Audit_KB: cache determinístico
``audit_id → kb_codigo``.

O LLM classifica cada audit_id UMA vez na vida; depois é lookup puro.
Sem TTl — invalidação por recarga da KB (entradas cobertas por mapeamento
direto somem) ou rota admin.
"""
from __future__ import annotations

import logging
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cwv_audit_kb_cache import CwvAuditKbCache

logger = logging.getLogger(__name__)

OrigemCache = Literal["llm", "manual"]


async def buscar_classificacoes(
    db: AsyncSession, audit_ids: list[str]
) -> dict[str, str | None]:
    """Retorna ``{audit_id: kb_codigo_ou_None}`` para os audits já cacheados.

    Entradas ausentes da resposta NÃO estão no cache (chamar LLM e gravar).
    ``None`` no valor significa "classificado como sem KB catalogada" — usa direto.
    """
    if not audit_ids:
        return {}
    res = await db.execute(
        select(CwvAuditKbCache.audit_id, CwvAuditKbCache.kb_codigo).where(
            CwvAuditKbCache.audit_id.in_(set(audit_ids))
        )
    )
    return {aid: kb for aid, kb in res.all()}


async def salvar_classificacao(
    db: AsyncSession,
    *,
    audit_id: str,
    kb_codigo: str | None,
    origem: OrigemCache = "llm",
    modelo: str | None = None,
) -> None:
    """Upsert idempotente (ON CONFLICT DO UPDATE).

    ``kb_codigo=None`` é válido (audit catalogado como "sem KB"). Atualiza
    ``atualizado_em`` via onupdate do SQLAlchemy.
    """
    stmt = pg_insert(CwvAuditKbCache)
    stmt = stmt.values(
        audit_id=audit_id,
        kb_codigo=kb_codigo,
        origem=origem,
        modelo=modelo,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["audit_id"],
        set_={
            "kb_codigo": stmt.excluded.kb_codigo,
            "origem": stmt.excluded.origem,
            "modelo": stmt.excluded.modelo,
            "atualizado_em": stmt.excluded.atualizado_em,
        },
    )
    await db.execute(stmt)


async def invalidar(db: AsyncSession, audit_id: str) -> bool:
    """Deleta uma entrada — próxima análise reclassifica via LLM. True se removeu."""
    from sqlalchemy import delete

    res = await db.execute(
        delete(CwvAuditKbCache).where(CwvAuditKbCache.audit_id == audit_id)
    )
    return (res.rowcount or 0) > 0


async def invalidar_cobertos_por_direto(
    db: AsyncSession, diretos: dict[str, str]
) -> int:
    """Remove entradas cujo ``audit_id`` passou a ter mapeamento direto na KB.

    Chamado por ``recarregar_kb`` após reload — o mapeamento direto sempre vence.
    """
    if not diretos:
        return 0
    from sqlalchemy import delete

    res = await db.execute(
        delete(CwvAuditKbCache).where(CwvAuditKbCache.audit_id.in_(set(diretos.keys())))
    )
    return res.rowcount or 0


async def listar_tudo(
    db: AsyncSession, *, offset: int = 0, limit: int = 100
) -> tuple[list[dict], int]:
    """Para a rota admin GET /admin/cwv/audit-kb-cache."""
    from sqlalchemy import func

    base = select(CwvAuditKbCache)
    total_res = await db.execute(select(func.count()).select_from(base.subquery()))
    total = int(total_res.scalar() or 0)

    rows_res = await db.execute(
        base.order_by(CwvAuditKbCache.atualizado_em.desc()).offset(offset).limit(limit)
    )
    items = [
        {
            "audit_id": r.audit_id,
            "kb_codigo": r.kb_codigo,
            "origem": r.origem,
            "modelo": r.modelo,
            "criado_em": r.criado_em.isoformat() if r.criado_em else "",
            "atualizado_em": r.atualizado_em.isoformat() if r.atualizado_em else "",
        }
        for r in rows_res.scalars().all()
    ]
    return items, total
