"""Consolidador Cross-URL (SPEC_CWV_Consolidador_Cross_URL).

Fase 1 — determinística: agrupa problemas idênticos por chave canônica,
agrega evidências (savings somados, top recursos), escopo (urls/estratégias).
Fase 2 — LLM (1 chamada, kill-switch): mescla grupos de causa raiz comum e
redige causa raiz + escopo + recomendação. Fail-open: resposta inválida →
degrada para 100% determinística.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.services.cwv_auditoria_service import chave_problema

logger = logging.getLogger(__name__)

_ESFORCO_ORDEM = {"baixo": 1, "medio": 2, "alto": 3}
_PESO_METRICA = {"LCP": 5, "CLS": 4, "INP": 4, "TBT": 3, "FCP": 2, "TTFB": 2}
_MAX_GRUPOS_LLM = 50


class GrupoConsolidadoOut(BaseModel):
    grupos_origem: list[int] = Field(description="grupo_id da fase 1 (>= 1)")
    titulo: str
    causa_raiz: str
    escopo_descricao: str
    recomendacao_resumo: str


class ConsolidacaoOut(BaseModel):
    grupos: list[GrupoConsolidadoOut]
    observacoes_gerais: str | None = None


def _max_esforco(esforcos: list[str | None]) -> str | None:
    validos = [e for e in esforcos if e in _ESFORCO_ORDEM]
    return max(validos, key=lambda e: _ESFORCO_ORDEM[e]) if validos else None


def agrupar_problemas(problemas: list[dict]) -> list[dict]:
    """Fase 1 — agrupamento determinístico por chave canônica.

    Cada grupo vira um dict com: grupo_id, kb_codigo, audit_ids, titulo,
    severidade (max), esforco (max), metricas_afetadas (união), urls,
    estrategias, savings_total_ms/bytes, top_recursos (3 maiores),
    problemas_ids.
    """
    grupos: dict[str, list[dict]] = {}
    for p in problemas:
        ch = chave_problema(p)
        grupos.setdefault(ch, []).append(p)

    resultado = []
    for grupo_id, (chave, probs) in enumerate(grupos.items(), start=1):
        primeiro = probs[0]
        urls = sorted({p.get("url_canonica", "") for p in probs if p.get("url_canonica")})
        estrategias = sorted({p.get("estrategia", "") for p in probs if p.get("estrategia")})
        metricas: set[str] = set()
        audit_ids: set[str] = set()
        savings_ms = 0.0
        savings_bytes = 0.0
        for p in probs:
            metricas.update(p.get("metricas_afetadas", []))
            if p.get("audit_id"):
                audit_ids.add(p["audit_id"])
            ctx = p.get("contexto_especifico") or {}
            sm = ctx.get("savings_ms")
            sb = ctx.get("savings_bytes")
            if sm:
                savings_ms += float(sm)
            if sb:
                savings_bytes += float(sb)

        # Top recursos (3 maiores desperdícios).
        todos_items = []
        for p in probs:
            ctx = p.get("contexto_especifico") or {}
            items = ctx.get("items") or ctx.get("details", {}).get("items") or []
            for it in items:
                wasted = it.get("wastedMs") or it.get("wastedBytes") or 0
                todos_items.append((float(wasted), (it.get("url") or it.get("label") or "")[:80]))
        todos_items.sort(key=lambda x: x[0], reverse=True)
        top_recursos = [{"recurso": r, "wasted": w} for w, r in todos_items[:3]]

        resultado.append({
            "grupo_id": grupo_id,
            "chave": chave,
            "kb_codigo": primeiro.get("kb_codigo"),
            "audit_ids": sorted(audit_ids),
            "titulo": primeiro.get("titulo", chave),
            "severidade": max(p.get("severidade", 1) for p in probs),
            "esforco": _max_esforco([p.get("esforco") for p in probs]),
            "metricas_afetadas": sorted(metricas),
            "urls": urls,
            "estrategias": estrategias,
            "savings_total_ms": savings_ms,
            "savings_total_bytes": savings_bytes,
            "top_recursos": top_recursos,
            "problemas_ids": [p.get("id") for p in probs if p.get("id")],
            "documentacao_md": primeiro.get("documentacao_md", ""),
        })
    return resultado


def _score_consolidado(grupo: dict) -> float:
    """Score para ordenação: severidade x soma de pesos de métricas."""
    peso = sum(_PESO_METRICA.get(m, 1) for m in grupo.get("metricas_afetadas", []))
    return grupo.get("severidade", 1) * peso


def _validar_e_aplicar_llm(
    grupos_fase1: list[dict],
    resposta: ConsolidacaoOut,
) -> list[dict] | None:
    """Valida a resposta do LLM (fail-open). Retorna grupos mesclados ou None.

    Regras: todo grupo_id referenciado deve existir e aparecer no máximo 1 vez.
    Violação → descarta a resposta inteira (retorna None → caller degrada).
    """
    grupos_by_id = {g["grupo_id"]: g for g in grupos_fase1}
    vistos: set[int] = set()
    mesclados: list[dict] = []

    for out in resposta.grupos:
        # Validação: grupos_origem devem existir e não repetir.
        if not out.grupos_origem:
            continue
        if any(gid not in grupos_by_id for gid in out.grupos_origem):
            logger.warning("consolidador: grupo_id inexistente %s — descartando resposta LLM", out.grupos_origem)
            return None
        if any(gid in vistos for gid in out.grupos_origem):
            logger.warning("consolidador: grupo_id repetido %s — descartando resposta LLM", out.grupos_origem)
            return None
        vistos.update(out.grupos_origem)

        # Mescla os grupos de origem.
        origens = [grupos_by_id[gid] for gid in out.grupos_origem]
        probs_ids: list = []
        urls: set = set()
        estrategias: set = set()
        for o in origens:
            probs_ids.extend(o.get("problemas_ids", []))
            urls.update(o.get("urls", []))
            estrategias.update(o.get("estrategias", []))

        mesclados.append({
            **origens[0],  # herda campos determinísticos do primeiro
            "titulo": out.titulo,
            "causa_raiz": out.causa_raiz,
            "escopo_descricao": out.escopo_descricao,
            "recomendacao_md": out.recomendacao_resumo,
            "problemas_ids": probs_ids,
            "urls": sorted(urls),
            "estrategias": sorted(estrategias),
        })

    # Grupos não citados pelo LLM viram consolidados determinísticos individuais.
    for gid, g in grupos_by_id.items():
        if gid not in vistos:
            mesclados.append({
                **g,
                "causa_raiz": "",
                "escopo_descricao": "",
                "recomendacao_md": "",
            })

    return mesclados


class CWVConsolidadorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        from app.config import settings

        model = settings.cwv_consolidador_llm_model if settings.llm_provider == "openai" else None
        super().__init__(
            usuario_id,
            model=model,
            temperature=settings.cwv_consolidador_llm_temperature,
        )

    async def consolidar(self, grupos_fase1: list[dict]) -> list[dict]:
        """Fase 2 — LLM opcional. Retorna grupos mesclados (ou determinísticos)."""
        from app.config import settings
        from app.core.metrics import cwv_consolidador_fallback_total

        if not settings.cwv_consolidador_llm_habilitado or len(grupos_fase1) < 2:
            cwv_consolidador_fallback_total.labels(motivo="kill_switch_ou_poucos_grupos").inc()
            return [{**g, "causa_raiz": "", "escopo_descricao": "", "recomendacao_md": ""} for g in grupos_fase1]

        grupos_para_llm = grupos_fase1[:_MAX_GRUPOS_LLM]
        excedentes = grupos_fase1[_MAX_GRUPOS_LLM:]

        try:
            prompt = _montar_prompt_consolidacao(grupos_para_llm)
            resp: ConsolidacaoOut = await self.invoke_structured(prompt, ConsolidacaoOut)
            mesclados = _validar_e_aplicar_llm(grupos_para_llm, resp)
            if mesclados is None:
                cwv_consolidador_fallback_total.labels(motivo="resposta_invalida").inc()
                return [{**g, "causa_raiz": "", "escopo_descricao": "", "recomendacao_md": ""} for g in grupos_fase1]
            # Excedentes ficam determinísticos.
            for g in excedentes:
                mesclados.append({**g, "causa_raiz": "", "escopo_descricao": "", "recomendacao_md": ""})
            return mesclados
        except Exception:
            logger.warning("consolidador: LLM falhou — degradando para determinístico", exc_info=True)
            cwv_consolidador_fallback_total.labels(motivo="excecao_llm").inc()
            return [{**g, "causa_raiz": "", "escopo_descricao": "", "recomendacao_md": ""} for g in grupos_fase1]


def _montar_prompt_consolidacao(grupos: list[dict]) -> str:
    """Prompt compacto pt-BR para o LLM juiz (sem documentacao_md/items brutos)."""
    linhas = ["Você é um consultor de Core Web Vitals consolidando problemas idênticos entre URLs."]
    linhas.append("Agrupe apenas grupos com causa raiz comum. NUNCA invente grupo_id.")
    linhas.append("Redija causa raiz citando recursos reais. Responda em pt-BR.\n")
    linhas.append("Grupos (id | título | kb | métricas | urls | estratégias | savings_ms | top recursos):")
    for g in grupos:
        recursos = ", ".join(r["recurso"] for r in g.get("top_recursos", [])[:3]) or "—"
        linhas.append(
            f"  #{g['grupo_id']} | {g['titulo'][:60]} | {g.get('kb_codigo', '—')} | "
            f"{','.join(g.get('metricas_afetadas', []))} | {len(g.get('urls', []))} urls | "
            f"{','.join(g.get('estrategias', []))} | {g.get('savings_total_ms', 0):.0f}ms | {recursos}"
        )
    linhas.append("\nPara cada grupo consolidado, forneça: grupos_origem (ids), título, causa_raiz, escopo_descricao, recomendacao_resumo.")
    return "\n".join(linhas)


async def executar_consolidacao(auditoria_id: str) -> None:
    """Job ARQ: executa a consolidação completa de uma auditoria.

    Fail-open total: qualquer exceção → consolidacao_status='falhou'.
    """
    import logging

    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.cwv_analise import CwvAnalise
    from app.models.cwv_auditoria import CwvAuditoria
    from app.models.cwv_checklist_item import CwvChecklistItem
    from app.models.cwv_problema import CwvProblema
    from app.models.cwv_problema_consolidado import CwvProblemaConsolidado

    log = logging.getLogger(__name__)

    try:
        async with async_session_factory() as session:
            aud_result = await session.execute(
                select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id)
            )
            auditoria = aud_result.scalar_one_or_none()
            if not auditoria or not auditoria.execucao_before_id:
                log.warning("executar_consolidacao: auditoria %s sem execucao_before", auditoria_id)
                return

            auditoria.consolidacao_status = "executando"
            await session.commit()

            # Carrega problemas da execução before (serializados para a fase 1).
            analises_result = await session.execute(
                select(CwvAnalise).where(
                    CwvAnalise.execucao_id == auditoria.execucao_before_id,
                    CwvAnalise.status == "sucesso",
                )
            )
            analises = list(analises_result.scalars().all())

            probs_result = await session.execute(
                select(CwvProblema).where(
                    CwvProblema.analise_id.in_([a.id for a in analises])
                )
            )
            problemas_orm = list(probs_result.scalars().all())

            # Serializa para dict (com url/estrategia da análise de origem).
            analise_map = {a.id: a for a in analises}
            problemas_dict = []
            for p in problemas_orm:
                a = analise_map.get(p.analise_id)
                problemas_dict.append({
                    "id": str(p.id),
                    "kb_codigo": p.kb_codigo,
                    "audit_id": p.audit_id,
                    "titulo": p.titulo,
                    "severidade": p.severidade,
                    "esforco": p.esforco,
                    "metricas_afetadas": p.metricas_afetadas or [],
                    "contexto_especifico": p.contexto_especifico or {},
                    "documentacao_md": p.documentacao_md or "",
                    "url_canonica": a.url_canonica if a else "",
                    "estrategia": a.estrategia if a else "",
                })

            # Fase 1.
            grupos_fase1 = agrupar_problemas(problemas_dict)

            # Fase 2 (LLM opcional).
            agente = CWVConsolidadorAgent(usuario_id=str(auditoria.usuario_id))
            mesclados = await agente.consolidar(grupos_fase1)

            # Ordena por prioridade (score desc, desempate por nº de urls).
            mesclados.sort(key=lambda g: (-_score_consolidado(g), -len(g.get("urls", []))))

            # Idempotência: apaga consolidados antigos.
            old_result = await session.execute(
                select(CwvProblemaConsolidado).where(CwvProblemaConsolidado.auditoria_id == auditoria_id)
            )
            for old in old_result.scalars().all():
                await session.delete(old)
            await session.flush()

            # Insere novos + vincula checklist items.
            for ordem, g in enumerate(mesclados, start=1):
                consol = CwvProblemaConsolidado(
                    auditoria_id=auditoria_id,
                    titulo=g["titulo"],
                    causa_raiz=g.get("causa_raiz", ""),
                    kb_codigo=g.get("kb_codigo"),
                    audit_ids=g.get("audit_ids", []),
                    problemas_origem_ids=g.get("problemas_ids", []),
                    evidencias_json={
                        "top_recursos": g.get("top_recursos", []),
                        "savings_total_ms": g.get("savings_total_ms", 0),
                        "savings_total_bytes": g.get("savings_total_bytes", 0),
                    },
                    severidade=g["severidade"],
                    prioridade_ordem=ordem,
                    esforco=g.get("esforco"),
                    metricas_afetadas=g.get("metricas_afetadas", []),
                    escopo_json={
                        "urls": g.get("urls", []),
                        "estrategias": g.get("estrategias", []),
                        "descricao": g.get("escopo_descricao", ""),
                    },
                    recomendacao_md=g.get("recomendacao_md", ""),
                )
                session.add(consol)
                await session.flush()

                # Vincula checklist items fail (match por item_codigo == chave do grupo).
                chave_grupo = g.get("chave") or (
                    g.get("kb_codigo") or (f"audit:{g['audit_ids'][0]}" if g.get("audit_ids") else f"titulo:{g['titulo']}")
                )
                items_result = await session.execute(
                    select(CwvChecklistItem).where(
                        CwvChecklistItem.auditoria_id == auditoria_id,
                        CwvChecklistItem.item_codigo == chave_grupo,
                        CwvChecklistItem.status_before == "fail",
                    )
                )
                for item in items_result.scalars().all():
                    item.problema_consolidado_id = consol.id

            auditoria.consolidacao_status = "concluida"
            await session.commit()
            log.info("executar_consolidacao auditoria=%s: %d consolidados", auditoria_id, len(mesclados))

    except Exception:
        log.exception("executar_consolidacao falhou para auditoria %s", auditoria_id)
        async with async_session_factory() as session:
            aud = await session.get(CwvAuditoria, auditoria_id)
            if aud:
                aud.consolidacao_status = "falhou"
                await session.commit()

