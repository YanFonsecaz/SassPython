import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


def workflow_node(node_name: str, descricao: str):
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(estado: dict[str, Any]) -> dict[str, Any]:
            from app.core.workflow_events import publish_event

            eid = estado["execucao_id"]
            await publish_event(eid, "node_start", node_name, descricao)

            async with async_session_factory() as session:
                await _atualizar_etapa(eid, node_name, session)
                resultado = await func(estado, session)
                await session.commit()

            resumo = _resumir(node_name, resultado, descricao)
            await publish_event(eid, "node_complete", node_name, resumo)
            return resultado
        return wrapper
    return decorator


async def _atualizar_etapa(execucao_id: str, etapa: str, session=None) -> None:
    from app.services import ferramenta_service

    await ferramenta_service.atualizar_execucao(session, execucao_id, etapa_atual=etapa)


def _resumir(node_name: str, resultado: dict[str, Any], descricao: str) -> str:
    if node_name == "pesquisar":
        pr = resultado.get("pesquisa_resultados", {})
        n_web = len(pr.get("resultados_web", []))
        n_trends = len(pr.get("tendencias", []))
        return f"Pesquisa concluida ({n_web} fontes web, {n_trends} tendencias)"
    if node_name == "analisar":
        n = len(resultado.get("conteudos_selecionados", []))
        return f"Analise concluida ({n} conteudos selecionados)"
    if node_name == "criar_brief":
        n = len(resultado.get("brief", {}).get("outline", []))
        return f"Brief criado ({n} secoes no outline)"
    if node_name == "redigir":
        palavras = resultado.get("artigo", {}).get("contagem_palavras", 0)
        versao = resultado.get("versao_atual", 1)
        return f"Versao {versao} redigida ({palavras} palavras)"
    if node_name == "revisar":
        score = resultado.get("revisao", {}).get("score_qualidade", 0)
        aprovado = resultado.get("aprovado_revisor", False)
        tentativa = resultado.get("tentativas_revisao", 1)
        status = "aprovado" if aprovado else f"score {score}/100"
        return f"Revisao {tentativa} — {status}"
    if node_name == "gerar_imagem":
        return resultado.get("imagem_url", descricao)
    return descricao
