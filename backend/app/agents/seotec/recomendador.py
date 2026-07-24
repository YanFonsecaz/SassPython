"""Agente recomendador SEOTEC (SPEC_SEOTEC_Agentes_IA, nó `recomendar_ia`).

Para cada item:
  1. KB primeiro: ``seotec_kb.buscar(slug, plataforma)`` → hit renderiza a
     recomendação canônica (com variação por plataforma quando existe). Sem LLM.
  2. Miss → LLM em lote gera a recomendação (fallback enriquecido com
     descrição/importância do item do checklist).

Itens ``Aprovado`` sem entrada na KB recebem texto curto padrão ("Item OK.")
— também sem LLM.

Itens marcados ``recomendada_ia: true`` (e Reprovado/Atenção) geram sugestões
para uma amostra de até ``settings.seotec_ia_amostra_max`` URLs — nunca o site
inteiro (SPEC §2). Saída por URL opcional; miss de KB já é coberta pelo fluxo
principal, então este método só roda quando a flag existe.

LLM indisponível/erro => item fica sem recomendação (pendente); auditoria NÃO
falha (SPEC §2, último critério). Padrão: agents/cwv/analisador.py + base.py.
"""
import logging

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.config import settings
from app.services import seotec_kb

logger = logging.getLogger(__name__)

# Estes status recebem recomendação acionável. Aprovado pega texto curto da KB.
STATUS_RECOMENDACAO = {"reprovado", "atencao"}
AMOSTRA_NO_PROMPT = 5
APROVADO_SEM_KB = "Item aprovado nesta auditoria — mantenha a prática atual."


class RecomendacaoOut(BaseModel):
    slug: str
    recomendacao: str = Field(default="")


class ListaRecomendacoes(BaseModel):
    itens: list[RecomendacaoOut] = Field(default_factory=list)


class SugestaoUrlOut(BaseModel):
    url: str
    sugestao: str = Field(default="")


class ListaSugestoesOut(BaseModel):
    slug: str
    sugestoes: list[SugestaoUrlOut] = Field(default_factory=list)


def montar_contexto_recomendacao(checklist, resultados: dict) -> list[dict]:
    """Contexto de todos os itens avaliados (aprovado + reprovado + atencao).

    Itens `sem_dados`/`na` não recebem recomendação (nada a dizer).
    """
    por_slug = checklist.itens_por_slug()
    ctx: list[dict] = []
    for slug, resultado in resultados.items():
        if resultado.status not in STATUS_RECOMENDACAO | {"aprovado"}:
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
            "avaliacao_ia": item.avaliacao_ia,
            "recomendada_ia": item.recomendada_ia,
        })
    return ctx


class SeotecRecomendadorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        model = (
            settings.seotec_recomendador_llm_model
            if settings.llm_provider == "openai"
            else None
        )
        super().__init__(
            usuario_id,
            model=model,
            temperature=settings.seotec_recomendador_llm_temperature,
        )

    async def recomendar(
        self, itens_ctx: list[dict], plataforma: str
    ) -> tuple[dict[str, str], list[str]]:
        """Retorna ({slug: recomendação}, [slugs_pendentes]).

        Fluxo KB→LLM (padrão CWV). Aprovados sem KB recebem texto curto fixo.
        """
        recomendacoes: dict[str, str] = {}
        pendentes: list[str] = []
        kb = seotec_kb.carregar_kb()
        entradas = kb.por_slug()

        sem_kb: list[dict] = []
        for item in itens_ctx:
            slug = item["slug"]
            entrada = entradas.get(slug)
            if entrada is not None:
                recomendacoes[slug] = seotec_kb.render_recomendacao(entrada, plataforma)
                continue
            if item["status"] == "aprovado":
                # SPEC §2: aprovado sem KB → texto curto padrão, sem LLM.
                recomendacoes[slug] = APROVADO_SEM_KB
                continue
            sem_kb.append(item)

        if not sem_kb:
            return recomendacoes, pendentes

        lote = max(1, settings.seotec_ia_lote)
        for inicio in range(0, len(sem_kb), lote):
            bloco = sem_kb[inicio:inicio + lote]
            slugs_bloco = {i["slug"] for i in bloco}
            try:
                prompt = _montar_prompt(bloco, plataforma)
                resp: ListaRecomendacoes = await self.invoke_structured(
                    prompt, ListaRecomendacoes
                )
                for r in resp.itens:
                    if r.slug in slugs_bloco and r.recomendacao.strip():
                        recomendacoes[r.slug] = r.recomendacao.strip()
                pendentes.extend(sorted(slugs_bloco - recomendacoes.keys()))
            except Exception as exc:
                logger.warning("SEOTEC recomendador LLM falhou no lote: %s", exc)
                pendentes.extend(sorted(slugs_bloco))

        return recomendacoes, pendentes

    async def sugerir_amostra(
        self, itens_recomendada_ia: list[dict], plataforma: str
    ) -> dict[str, list[dict]]:
        """Para itens com ``recomendada_ia=true``: gera sugestão por URL de amostra.

        Amostra limitada a ``settings.seotec_ia_amostra_max`` URLs por item.
        Falha de LLM => item sem sugestões (fail-open). Retorna
        ``{slug: [{url, sugestao}, ...]}``.
        """
        out: dict[str, list[dict]] = {}
        if not itens_recomendada_ia:
            return out

        limite = max(1, settings.seotec_ia_amostra_max)
        for item in itens_recomendada_ia:
            amostra = item.get("amostra") or []
            if not amostra:
                continue
            amostra_cortada = amostra[:limite]
            try:
                prompt = _montar_prompt_sugestoes(item, amostra_cortada, plataforma)
                resp: ListaSugestoesOut = await self.invoke_structured(
                    prompt, ListaSugestoesOut
                )
                validas = [
                    {"url": s.url, "sugestao": s.sugestao.strip()}
                    for s in resp.sugestoes
                    if s.url and s.sugestao.strip()
                ]
                if validas:
                    out[item["slug"]] = validas
            except Exception as exc:
                logger.warning(
                    "SEOTEC recomendador.sugerir_amostra falhou (%s): %s",
                    item["slug"], exc,
                )
        return out


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


def _montar_prompt(bloco: list[dict], plataforma: str) -> str:
    itens_str = "\n\n".join(_fmt_item(i) for i in bloco)
    return (
        "Você é um consultor de SEO técnico redigindo o campo 'Recomendação' de "
        "uma auditoria para um cliente não técnico.\n\n"
        f"Plataforma detectada do site: {plataforma}\n\n"
        "Para CADA item abaixo, escreva uma recomendação curta e acionável "
        "(2-5 frases) que:\n"
        "- Diga COMO corrigir o problema (passos concretos, não genéricos).\n"
        "- Cite a plataforma detectada quando fizer sentido (ex.: plugin, CMS, "
        "campo no admin).\n"
        "- Priorize as páginas de maior impacto quando não for possível corrigir "
        "tudo de uma vez.\n"
        "- NÃO repita o diagnóstico — só a recomendação de correção.\n"
        "- Use o mesmo `slug` recebido; não invente itens.\n\n"
        "## Itens\n\n"
        f"{itens_str}\n"
    )


def _montar_prompt_sugestoes(item: dict, amostra: list[dict], plataforma: str) -> str:
    urls_str = "\n".join(
        f"- {row.get('address', row)}"
        for row in amostra
    )
    return (
        f"Você é um consultor de SEO técnico. Para o item '{item['slug']}' "
        f"({item['nome']}) no site {plataforma}, gere uma sugestão curta e "
        "específica para CADA URL abaixo.\n\n"
        f"O que é o item: {item['descricao'][:300]}\n\n"
        "## URLs\n"
        f"{urls_str}\n\n"
        "Retorne uma sugestão por URL (máx. 1 frase), focada no que mudar "
        "naquela página específica. Use exatamente as URLs fornecidas.\n"
        f"slug: {item['slug']}\n"
    )
