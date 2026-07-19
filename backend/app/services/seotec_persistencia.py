"""Persistência dos resultados SEOTEC (upsert por (auditoria_id, item_slug))."""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.seo_auditoria import SeoAuditoria
from app.models.seo_crawl import SeoCrawl
from app.models.seo_item_resultado import SeoItemResultado
from app.services.seotec_checklist import carregar_checklist
from app.services.seotec_motor import ResultadoItem
from app.services.seotec_score import ScoreResultado


async def persistir_resultados(
    db: AsyncSession,
    auditoria: SeoAuditoria,
    crawl: SeoCrawl,
    resultados: dict[str, ResultadoItem],
    score: ScoreResultado,
    faltantes: list[str],
) -> None:
    ck = carregar_checklist()
    existentes = {
        i.item_slug: i
        for i in (await db.execute(
            select(SeoItemResultado).where(SeoItemResultado.auditoria_id == auditoria.id)
        )).scalars()
    }
    campo_status = "status_antes" if crawl.fase_destino == "before" else "status_depois"

    for item in ck.itens():
        linha = existentes.get(item.slug)
        if linha is None:
            linha = SeoItemResultado(
                auditoria_id=auditoria.id,
                item_slug=item.slug,
                modo="auto" if item.fonte == "sf" else "manual",
            )
            db.add(linha)
        resultado = resultados.get(item.slug)
        if resultado is not None:
            setattr(linha, campo_status, resultado.status)
            linha.evidencias_json = {
                "total_avaliadas": resultado.total_avaliadas,
                "total_afetadas": resultado.total_afetadas,
                "amostra": resultado.amostra,
                "truncada": resultado.truncada,
            }

    if crawl.fase_destino == "before":
        auditoria.score_antes = score.score
        if auditoria.data_inicial is None:
            auditoria.data_inicial = datetime.now(UTC)
    else:
        auditoria.score_depois = score.score

    crawl.status = "parcial" if faltantes else "processado"
    crawl.contadores_json = {
        "faltantes": faltantes,
        "score": score.score,
        "por_prioridade": score.por_prioridade,
        "por_categoria": score.por_categoria,
        "itens_avaliados": len(resultados),
    }
    await db.flush()
