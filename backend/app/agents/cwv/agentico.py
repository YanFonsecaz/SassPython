"""Agente de geração de artefatos agênticos (SPEC_CWV_Navegacao_Agentica_Geracao_IA).

Dois métodos: ``gerar_llms_txt`` (avalia coerência + gera a versão ideal) e
``gerar_webmcp`` (scaffold + explicação + como aplicar). Segue o padrão da casa:
``invoke_structured(prompt, Schema)``. O endpoint aplica kill-switch, fail-open,
rate-limit e anti-SSRF; aqui só a geração.
"""
from __future__ import annotations

import logging
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.config import settings

logger = logging.getLogger(__name__)

# Versão-alvo da spec WebMCP, fixada no prompt e no cabeçalho do artefato — o
# código gerado é scaffold para revisão, não production-certified (spec é draft).
WEBMCP_SPEC_VERSION = "WebMCP draft (W3C Web Machine Learning Community Group, 2026)"


class LlmsTxtOut(BaseModel):
    diagnostico: Literal["ausente", "incoerente", "coerente"]
    conteudo_llms_txt: str  # Markdown com H1 garantido (validado pós-LLM)
    justificativa: str


class WebMcpOut(BaseModel):
    detectado: bool
    ferramentas_sugeridas: list[str] = Field(default_factory=list)
    codigo: str
    linguagem: str = "javascript"
    explicacao_md: str
    como_aplicar_md: str


def _fmt_lista(itens: list[str], vazio: str = "(nenhum)") -> str:
    return "\n".join(f"- {i}" for i in itens) if itens else vazio


def _montar_prompt_llms_txt(site: dict, llms_txt_atual: str | None) -> str:
    atual = llms_txt_atual or "(nenhum arquivo llms.txt encontrado)"
    return (
        "Você é um especialista em otimização de sites para agentes de IA. Sua tarefa é "
        "avaliar e gerar o arquivo `llms.txt` (Markdown com um H1 obrigatório) que descreve "
        "o site para modelos de linguagem, seguindo a convenção llmstxt.org.\n\n"
        f"SITE (origem: {site.get('origem')})\n"
        f"Título: {site.get('title')}\n"
        f"Descrição: {site.get('meta_description')}\n"
        f"H1 da home:\n{_fmt_lista(site.get('h1') or [])}\n"
        f"H2 da home:\n{_fmt_lista(site.get('h2') or [])}\n"
        f"Navegação:\n{_fmt_lista(site.get('nav_links') or [])}\n"
        f"URLs do sitemap (amostra):\n{_fmt_lista((site.get('sitemap_urls') or [])[:20])}\n\n"
        f"llms.txt ATUAL:\n{atual}\n\n"
        "Responda:\n"
        "- diagnostico: 'ausente' se não há arquivo; 'incoerente' se existe mas não condiz "
        "com o site; 'coerente' se já está bom.\n"
        "- conteudo_llms_txt: o arquivo llms.txt IDEAL em Markdown, começando com '# <Nome do site>' "
        "(H1 obrigatório), com uma breve descrição e uma lista de seções/links importantes. Se o "
        "atual já é coerente, faça melhorias incrementais preservando o que está bom.\n"
        "- justificativa: por que gerou/o que faltava (1-3 frases em pt-BR)."
    )


def _montar_prompt_webmcp(site: dict, plataforma: str, sinais: dict) -> str:
    detectado = sinais.get("detectado", False)
    sinais_txt = ", ".join(k for k, v in (sinais.get("sinais") or {}).items() if v) or "(nenhum)"
    return (
        "Você é um engenheiro especialista em WebMCP (Model Context Protocol para a Web), "
        f"versão-alvo: {WEBMCP_SPEC_VERSION}. WebMCP permite que uma página exponha 'tools' "
        "(ações) para agentes de IA via `navigator.modelContext.registerTool`.\n\n"
        f"SITE (origem: {site.get('origem')}, plataforma: {plataforma})\n"
        f"Título: {site.get('title')}\n"
        f"Navegação: {_fmt_lista(site.get('nav_links') or [], '(sem nav)')}\n"
        f"Sinais de WebMCP encontrados no HTML estático: {sinais_txt} "
        f"(detectado={detectado}).\n\n"
        "IMPORTANTE: a detecção é heurística sobre HTML estático; o registro real do WebMCP é "
        "em runtime via JS. 'Não detectado' NÃO prova ausência. O código é um SCAFFOLD para "
        "revisão humana, não production-certified (a spec é draft).\n\n"
        "Responda:\n"
        f"- detectado: {str(detectado).lower()} (repita o sinal recebido).\n"
        "- ferramentas_sugeridas: 2-5 tools úteis derivadas da navegação/formulários do site "
        "(ex.: buscar_produto, adicionar_ao_carrinho, contato).\n"
        "- codigo: scaffold JavaScript com `navigator.modelContext.registerTool(...)` para as "
        "tools sugeridas. O cabeçalho do código DEVE citar a versão da spec assumida em comentário.\n"
        "- linguagem: 'javascript'.\n"
        "- explicacao_md: em Markdown, o que cada parte do código faz.\n"
        "- como_aplicar_md: em Markdown, passos para aplicar na plataforma detectada "
        f"('{plataforma}'). Se detectado=true, foque em validar/complementar em vez de recriar."
    )


class CWVAgenticoAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        model = settings.cwv_agentico_llm_model if settings.llm_provider == "openai" else None
        super().__init__(
            usuario_id,
            model=model,
            temperature=settings.cwv_agentico_llm_temperature,
        )

    async def gerar_llms_txt(self, site: dict, llms_txt_atual: str | None) -> LlmsTxtOut:
        prompt = _montar_prompt_llms_txt(site, llms_txt_atual)
        resp: LlmsTxtOut = await self.invoke_structured(prompt, LlmsTxtOut)
        # Validação pós-LLM: nunca retornar artefato que reprova o próprio check
        # de detecção (precisa de um H1 Markdown).
        if not any(linha.startswith("# ") for linha in resp.conteudo_llms_txt.splitlines()):
            h1 = site.get("title") or urlsplit(site.get("origem") or "").netloc or "Site"
            resp.conteudo_llms_txt = f"# {h1}\n\n{resp.conteudo_llms_txt}"
        return resp

    async def gerar_webmcp(self, site: dict, plataforma: str, sinais: dict) -> WebMcpOut:
        prompt = _montar_prompt_webmcp(site, plataforma, sinais)
        resp: WebMcpOut = await self.invoke_structured(prompt, WebMcpOut)
        return resp
