"""Agente analisador SEOTEC (SPEC_SEOTEC_Agentes_IA, nó `analisar_ia`).

Gera o "Diagnóstico SEO" de cada item Reprovado/Atenção a partir do resultado
determinístico do motor de regras — com os números reais do site ("X de Y páginas
sem title…"). KB não entra aqui (é recomendação); o diagnóstico é sempre LLM em
lote. Padrão: agents/cwv/analisador.py + BaseAgent.invoke_structured.

LLM indisponível/erro => itens do lote ficam pendentes (sem diagnóstico); a
auditoria NÃO falha (SPEC §2, último critério).
"""
import logging

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.config import settings

logger = logging.getLogger(__name__)

# Só estes status recebem diagnóstico de IA.
STATUS_DIAGNOSTICAVEL = {"reprovado", "atencao"}
AMOSTRA_NO_PROMPT = 5


class DiagnosticoOut(BaseModel):
    slug: str
    diagnostico: str = Field(default="")


class ListaDiagnosticos(BaseModel):
    itens: list[DiagnosticoOut] = Field(default_factory=list)


def montar_contexto_itens(checklist, resultados: dict) -> list[dict]:
    """Contexto compacto dos itens diagnosticáveis (reprovado/atenção com regra)."""
    por_slug = checklist.itens_por_slug()
    ctx: list[dict] = []
    for slug, resultado in resultados.items():
        if resultado.status not in STATUS_DIAGNOSTICAVEL:
            continue
        item = por_slug.get(slug)
        if item is None:
            continue
        ctx.append({
            "slug": slug,
            "nome": item.nome,
            "categoria": item.categoria,
            "prioridade": item.prioridade,
            "descricao": (item.descricao or "").strip(),
            "importancia": (item.importancia or "").strip(),
            "status": resultado.status,
            "total_avaliadas": resultado.total_avaliadas,
            "total_afetadas": resultado.total_afetadas,
            "amostra": resultado.amostra[:AMOSTRA_NO_PROMPT],
        })
    return ctx


class SeotecAnalisadorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        model = (
            settings.seotec_analisador_llm_model
            if settings.llm_provider == "openai"
            else None
        )
        super().__init__(
            usuario_id,
            model=model,
            temperature=settings.seotec_analisador_llm_temperature,
        )

    async def diagnosticar(
        self, itens_ctx: list[dict], site: dict
    ) -> tuple[dict[str, str], list[str]]:
        """Retorna ({slug: diagnóstico}, [slugs_pendentes])."""
        diagnosticos: dict[str, str] = {}
        pendentes: list[str] = []
        lote = max(1, settings.seotec_ia_lote)

        for inicio in range(0, len(itens_ctx), lote):
            bloco = itens_ctx[inicio:inicio + lote]
            slugs_bloco = {i["slug"] for i in bloco}
            try:
                prompt = _montar_prompt(bloco, site)
                resp: ListaDiagnosticos = await self.invoke_structured(
                    prompt, ListaDiagnosticos
                )
                for d in resp.itens:
                    if d.slug in slugs_bloco and d.diagnostico.strip():
                        diagnosticos[d.slug] = d.diagnostico.strip()
                pendentes.extend(sorted(slugs_bloco - diagnosticos.keys()))
            except Exception as exc:
                logger.warning("SEOTEC analisador LLM falhou no lote: %s", exc)
                pendentes.extend(sorted(slugs_bloco))

        return diagnosticos, pendentes


def _fmt_amostra(amostra: list[dict]) -> str:
    if not amostra:
        return "  (sem amostra)"
    linhas = []
    for row in amostra:
        campos = ", ".join(f"{k}={v}" for k, v in row.items() if v is not None)
        linhas.append(f"  - {campos}")
    return "\n".join(linhas)


def _fmt_item(item: dict) -> str:
    return "\n".join([
        f"### {item['slug']}",
        f"- Item: {item['nome']} (categoria: {item['categoria']}, prioridade: {item['prioridade']})",
        f"- Status: {item['status']}",
        f"- Afetadas: {item['total_afetadas']} de {item['total_avaliadas']} páginas avaliadas",
        f"- O que é: {item['descricao'][:400]}",
        f"- Por que importa: {item['importancia'][:400]}",
        "- Amostra de páginas afetadas:",
        _fmt_amostra(item["amostra"]),
    ])


def _montar_prompt(bloco: list[dict], site: dict) -> str:
    itens_str = "\n\n".join(_fmt_item(i) for i in bloco)
    return (
        "Você é um consultor de SEO técnico redigindo o campo 'Diagnóstico' de uma "
        "auditoria para um cliente não técnico.\n\n"
        f"Site auditado: {site.get('dominio', '(domínio não informado)')} "
        f"(plataforma: {site.get('plataforma', 'geral')})\n\n"
        "Para CADA item abaixo, escreva um diagnóstico curto (1-3 frases) que:\n"
        "- Diga o que está errado NESTE site usando os números reais "
        "(ex.: '18 de 240 páginas estão sem title').\n"
        "- Explique de forma didática o impacto, sem jargão desnecessário.\n"
        "- NÃO proponha a solução (isso é outro campo) — só o diagnóstico.\n"
        "- Use o mesmo `slug` recebido; não invente itens.\n\n"
        "## Itens\n\n"
        f"{itens_str}\n"
    )
