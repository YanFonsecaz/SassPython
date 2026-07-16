"""Redator do relatório executivo da auditoria (SPEC_CWV_Relatorio_Executivo).

1 chamada LLM estruturada que produz sumário executivo, diagnóstico técnico e
plano faseado. Validação em lista fechada de item_codigo + fallback determinístico
por esforço se o LLM falhar/inventar códigos. Fail-open total.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class FaseOut(BaseModel):
    titulo: str
    justificativa: str
    itens_codigos: list[str] = Field(default_factory=list)


class RelatorioOut(BaseModel):
    sumario_executivo_md: str
    diagnostico_tecnico_md: str
    plano_fases: list[FaseOut] = Field(default_factory=list)


class CWVRedatorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        from app.config import settings

        model = settings.cwv_redator_llm_model if settings.llm_provider == "openai" else None
        super().__init__(
            usuario_id,
            model=model,
            temperature=settings.cwv_redator_llm_temperature,
        )

    async def redigir(
        self,
        *,
        cliente_nome: str,
        health_before: float | None,
        health_after: float | None,
        consolidados: list[dict],
        checklist_items: list[dict],
    ) -> dict:
        """Redige o relatório. Retorna dict com sumario/diagnostico/plano_fases/gerado_em/modelo."""
        from app.config import settings

        codigos_validos = {i["item_codigo"] for i in checklist_items if i.get("status_before") == "fail"}

        if not settings.cwv_redator_llm_habilitado or not consolidados:
            return _fallback_deterministico(codigos_validos, checklist_items, motivo="kill_switch_ou_sem_consolidados")

        try:
            prompt = _montar_prompt(cliente_nome, health_before, health_after, consolidados, checklist_items)
            resp: RelatorioOut = await self.invoke_structured(prompt, RelatorioOut)

            # Validação: filtra item_codigos inexistentes; remove fases vazias.
            plano_validado: list[dict] = []
            for fase in resp.plano_fases:
                codigos_filtrados = [c for c in fase.itens_codigos if c in codigos_validos]
                if codigos_filtrados:
                    plano_validado.append({
                        "titulo": fase.titulo,
                        "justificativa": fase.justificativa,
                        "itens_codigos": codigos_filtrados,
                    })

            if not plano_validado:
                # Todas as fases ficaram vazias → fallback determinístico.
                fb = _fallback_deterministico(codigos_validos, checklist_items, motivo="plano_vazio")
                plano_validado = fb["plano_fases"]

            return {
                "sumario_executivo_md": resp.sumario_executivo_md,
                "diagnostico_tecnico_md": resp.diagnostico_tecnico_md,
                "plano_fases": plano_validado,
                "gerado_em": datetime.now(UTC).isoformat(),
                "modelo": settings.cwv_redator_llm_model,
            }
        except Exception:
            logger.warning("redator: LLM falhou — fallback determinístico", exc_info=True)
            return _fallback_deterministico(codigos_validos, checklist_items, motivo="excecao_llm")


def _fallback_deterministico(codigos_validos: set[str], checklist_items: list[dict], *, motivo: str) -> dict:
    """Plano faseado determinístico por esforço (baixo=quick wins, medio=estruturais, alto=projetos)."""
    logger.info("redator: fallback determinístico (%s)", motivo)
    por_esforco: dict[str, list[str]] = {"baixo": [], "medio": [], "alto": []}
    for item in checklist_items:
        if item.get("status_before") != "fail":
            continue
        codigo = item["item_codigo"]
        esforco = item.get("esforco", "medio") or "medio"
        if esforco in por_esforco:
            por_esforco[esforco].append(codigo)

    fases = []
    labels = [
        ("baixo", "Prioridade 1 — Quick wins", "Correções de baixo esforço e alto impacto rápido."),
        ("medio", "Prioridade 2 — Ajustes estruturais", "Mudanças pontuais em tema/infra que exigem planejamento."),
        ("alto", "Prioridade 3 — Projetos de refactor", "Reescritas de arquitetura que exigem desenvolvimento dedicado."),
    ]
    for esforco, titulo, justificativa in labels:
        if por_esforco[esforco]:
            fases.append({"titulo": titulo, "justificativa": justificativa, "itens_codigos": por_esforco[esforco]})

    return {
        "sumario_executivo_md": "_Relatório gerado em modo determinístico (LLM indisponível). Revise manualmente os itens do checklist._",
        "diagnostico_tecnico_md": "_Diagnóstico técnico não gerado pelo LLM. Consulte os consolidados para causas raiz._",
        "plano_fases": fases,
        "gerado_em": datetime.now(UTC).isoformat(),
        "modelo": "fallback-deterministico",
    }


def _montar_prompt(
    cliente_nome: str,
    health_before: float | None,
    health_after: float | None,
    consolidados: list[dict],
    checklist_items: list[dict],
) -> str:
    """Prompt compacto pt-BR — NÃO envia documentacao_md nem items brutos."""
    linhas = [
        f"Você é um consultor sênior redigindo o relatório executivo de Core Web Vitals para o cliente '{cliente_nome}'.",
        "Tom profissional, voltado para o dono do negócio (sumário) e para o dev (diagnóstico). pt-BR.",
        "NÃO invente dados — cite apenas os números fornecidos.\n",
    ]
    if health_before is not None:
        linhas.append(f"Health Score Before: {health_before}%")
    if health_after is not None:
        linhas.append(f"Health Score After: {health_after}%")

    linhas.append(f"\nTop {min(len(consolidados), 10)} problemas consolidados:")
    for c in consolidados[:10]:
        linhas.append(
            f"  - {c.get('titulo', '?')[:60]} | sev {c.get('severidade', '?')} | "
            f"esforço {c.get('esforco', '?')} | métricas {','.join(c.get('metricas_afetadas', []))} | "
            f"{len((c.get('escopo_json') or {}).get('urls', []))} urls"
        )
        if c.get("causa_raiz"):
            linhas.append(f"    causa: {c['causa_raiz'][:100]}")

    fails = [i for i in checklist_items if i.get("status_before") == "fail"]
    linhas.append("\nItens do checklist (fail) para o plano faseado — use APENAS estes item_codigo:")
    for item in fails[:30]:
        linhas.append(f"  {item['item_codigo']} | {item.get('titulo', '')[:50]} | esforço {item.get('esforco', '?')}")

    linhas.append("\nForneça: sumario_executivo_md (3-5 parágrafos), diagnostico_tecnico_md, plano_fases (2-4 fases com itens_codigos válidos).")
    linhas.append("Não use títulos markdown (linhas começando com #) — escreva apenas parágrafos e listas; os títulos das seções já existem no documento.")
    return "\n".join(linhas)


async def executar_relatorio(auditoria_id: str) -> None:
    """Job ARQ: gera o relatório executivo de uma auditoria."""
    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.cliente import Cliente
    from app.models.cwv_auditoria import CwvAuditoria
    from app.models.cwv_checklist_item import CwvChecklistItem
    from app.models.cwv_problema_consolidado import CwvProblemaConsolidado

    try:
        async with async_session_factory() as session:
            aud_result = await session.execute(
                select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id)
            )
            auditoria = aud_result.scalar_one_or_none()
            if not auditoria:
                return

            # Status transitório.
            auditoria.relatorio_json = {"status": "gerando"}
            await session.commit()

            # Carrega consolidados.
            consol_result = await session.execute(
                select(CwvProblemaConsolidado)
                .where(CwvProblemaConsolidado.auditoria_id == auditoria_id)
                .order_by(CwvProblemaConsolidado.prioridade_ordem)
            )
            consolidados_orm = list(consol_result.scalars().all())
            consolidados = [{
                "titulo": c.titulo,
                "causa_raiz": c.causa_raiz,
                "severidade": c.severidade,
                "esforco": c.esforco,
                "metricas_afetadas": c.metricas_afetadas or [],
                "escopo_json": c.escopo_json or {},
            } for c in consolidados_orm]

            # Carrega checklist items.
            itens_result = await session.execute(
                select(CwvChecklistItem).where(CwvChecklistItem.auditoria_id == auditoria_id)
            )
            checklist_items = [{
                "item_codigo": i.item_codigo,
                "titulo": i.titulo,
                "status_before": i.status_before,
                "esforco": i.esforco,
            } for i in itens_result.scalars().all()]

            # Nome do cliente.
            cliente_nome = ""
            if auditoria.cliente_id:
                cliente = await session.get(Cliente, auditoria.cliente_id)
                cliente_nome = cliente.nome if cliente else ""

            # Redige.
            agente = CWVRedatorAgent(usuario_id=str(auditoria.usuario_id))
            relatorio = await agente.redigir(
                cliente_nome=cliente_nome,
                health_before=float(auditoria.health_score_before) if auditoria.health_score_before is not None else None,
                health_after=float(auditoria.health_score_after) if auditoria.health_score_after is not None else None,
                consolidados=consolidados,
                checklist_items=checklist_items,
            )

            auditoria.relatorio_json = relatorio
            await session.commit()
            logger.info("executar_relatorio auditoria=%s: relatório gerado", auditoria_id)

    except Exception:
        logger.exception("executar_relatorio falhou para auditoria %s", auditoria_id)
        async with async_session_factory() as session:
            aud = await session.get(CwvAuditoria, auditoria_id)
            if aud:
                aud.relatorio_json = {"status": "falhou"}
                await session.commit()
