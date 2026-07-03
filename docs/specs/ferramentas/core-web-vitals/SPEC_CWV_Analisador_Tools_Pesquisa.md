# SPEC #3 — Tools de pesquisa no analisador (SerpAPI + fetch_url)

**Status:** ✅ implementado · **Escopo:** backend (`agents/base.py`, `agents/cwv/analisador.py` ou novo `pesquisador.py`, `core/agent_tools.py` novo)
**Dependências:** [[SPEC_CWV_Analisador_Prompt_Enriquecido]] (prompt enriquecido vira input das tools), [[SPEC_CWV_KB_Expansao_Gaps]] (reduz o volume que precisa de pesquisa).
**Esforço estimado:** ~2 dias
**Prioridade:** média — só compensa após KB estar bem coberta.

## 1. Contexto e problema

Hoje o analisador (`agents/cwv/analisador.py`) chama o LLM uma única vez via `invoke_structured` sem nenhuma ferramenta. Para audits residuais sem entrada na KB, o LLM responde "outros" porque não tem como buscar a documentação real do audit nem inspecionar elementos afetados.

`BaseAgent` (`backend/app/agents/base.py:22`) instancia `ChatOpenAI(...)` sem `bind_tools` — toda a infra está pronta para receber tools (langchain-openai já suporta), só precisa do canal.

A consequência prática: o **`documentador.py`** depende inteiramente da KB pré-escrita. Quando uma entrada não cobre 100% do caso (ex.: solução genérica para Shopify mas o site está em Shopify Hydrogen), o usuário recebe documentação subótima.

## 2. Solução

Adicionar **duas tools** ao agente analisador (mais um agente novo "pesquisador" que documenta audits residuais com pesquisa):

| Tool | Quando o LLM usa |
|---|---|
| `buscar_web(query: str, num: int = 5)` | obter URLs candidatas de docs/blogs/web.dev sobre o audit ou problema |
| `fetch_url(url: str, max_chars: int = 8000)` | ler o conteúdo de uma das URLs encontradas (markdown extraído, limitado) |

Fluxo no agente:

```
analisador.analisar()
  ├── fast-path KB                       (sem LLM)
  ├── fallback LLM (com prompt enriquecido)  ← SPEC #1
  └── para problemas com kb_codigo='outros'  ← NOVO
      └── PesquisadorAgent.documentar(audit, plataforma)
           └── LLM com tools [buscar_web, fetch_url]
              → retorna documentacao_md customizada
```

### 2.1 Camada de tools genérica em `backend/app/core/agent_tools.py`

```python
"""Tools reusaveis para agentes LLM. Cada tool retorna string (formato esperado pelo LangChain)."""
import asyncio
import logging
from typing import Annotated

import httpx
from langchain_core.tools import tool

from app.config import settings

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15.0
_MAX_CONCURRENT_FETCHES = 3
_fetch_sem = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)


@tool
async def buscar_web(
    query: Annotated[str, "Termo de busca em ingles ou portugues, especifico"],
    num: Annotated[int, "Numero de resultados (1-10)"] = 5,
) -> str:
    """Busca na web via SerpAPI. Retorna lista de URLs + snippets em formato Markdown.

    Use para encontrar documentacao oficial, posts de blog tecnico, ou web.dev.
    Prefira queries em INGLES para temas tecnicos (mais resultados de qualidade).
    """
    if not settings.serpapi_key:
        return "ERRO: SerpAPI nao configurada."
    num = max(1, min(10, num))
    params = {
        "engine": "google",
        "q": query,
        "num": num,
        "api_key": settings.serpapi_key,
    }
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get("https://serpapi.com/search", params=params)
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("buscar_web falhou: %s", e)
        return f"ERRO: busca falhou ({type(e).__name__})"

    organicos = data.get("organic_results", [])[:num]
    if not organicos:
        return f"Nenhum resultado para: {query}"

    linhas = [f"# Resultados para: {query}\n"]
    for i, item in enumerate(organicos, 1):
        titulo = item.get("title", "")
        url = item.get("link", "")
        snippet = item.get("snippet", "")[:200]
        linhas.append(f"{i}. **{titulo}**\n   {url}\n   {snippet}\n")
    return "\n".join(linhas)


@tool
async def fetch_url(
    url: Annotated[str, "URL completa (https://...) a buscar"],
    max_chars: Annotated[int, "Limite de caracteres da resposta (1000-15000)"] = 8000,
) -> str:
    """Busca o conteudo de uma URL e retorna o texto extraido em Markdown.

    Use APOS `buscar_web` para ler em detalhe uma URL relevante.
    Limita resposta a max_chars (default 8000) para nao estourar contexto.
    HTML e simplificado para texto.
    """
    if not url.startswith(("http://", "https://")):
        return "ERRO: URL invalida (precisa http/https)"
    max_chars = max(1000, min(15000, max_chars))

    async with _fetch_sem:
        try:
            async with httpx.AsyncClient(
                timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "SEO-SaaS-CWV-Analyzer/1.0"},
            ) as client:
                r = await client.get(url)
                r.raise_for_status()
                content_type = r.headers.get("content-type", "")
                if "html" not in content_type and "text" not in content_type:
                    return f"ERRO: content-type nao suportado ({content_type})"
                html = r.text
        except httpx.HTTPError as e:
            logger.warning("fetch_url falhou para %s: %s", url, e)
            return f"ERRO: fetch falhou ({type(e).__name__})"

    # Extrair texto principal (lazy import — só carrega se a tool for chamada)
    from readability import Document  # readability-lxml
    from markdownify import markdownify

    try:
        doc = Document(html)
        title = doc.short_title()
        content_html = doc.summary()
        md = markdownify(content_html, heading_style="ATX").strip()
    except Exception as e:
        logger.warning("Extracao de readability falhou: %s", e)
        md = html  # fallback bruto
    if len(md) > max_chars:
        md = md[:max_chars] + f"\n\n[...truncado em {max_chars} chars]"
    return f"# {title}\n\n{md}"
```

### 2.2 `BaseAgent` aceitando tools

Em `backend/app/agents/base.py`:

```python
class BaseAgent:
    def __init__(self, usuario_id: str, tools: list | None = None):
        self.usuario_id = usuario_id
        self.llm = _get_chat_model(...)
        self._tools = tools or []
        if self._tools:
            self.llm = self.llm.bind_tools(self._tools)
```

E adicionar método `invoke_with_tools` que faz o loop ReAct manual (LangChain):

```python
async def invoke_with_tools(self, messages: list, max_iter: int = 4):
    """Loop ReAct simples: LLM responde, se houver tool_call executa e re-injeta."""
    from langchain_core.messages import ToolMessage

    for _ in range(max_iter):
        resp = await chamada_llm_com_retry(self.llm, messages, self.usuario_id)
        tool_calls = getattr(resp, "tool_calls", None) or []
        if not tool_calls:
            return resp
        messages.append(resp)
        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool_fn = next((t for t in self._tools if t.name == tool_name), None)
            if not tool_fn:
                content = f"ERRO: tool {tool_name} nao existe"
            else:
                try:
                    content = await tool_fn.ainvoke(tool_args)
                except Exception as e:
                    content = f"ERRO ao executar {tool_name}: {e}"
            messages.append(ToolMessage(content=str(content), tool_call_id=tc["id"]))
    return resp  # ultima resposta mesmo sem cobertura completa
```

### 2.3 Novo `CWVPesquisadorAgent`

Em `backend/app/agents/cwv/pesquisador.py`:

```python
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import BaseAgent
from app.core.agent_tools import buscar_web, fetch_url


SYSTEM = """Voce documenta problemas de Core Web Vitals que nao tem entrada na nossa
base de conhecimento. Use as tools `buscar_web` e `fetch_url` para encontrar a melhor
documentacao oficial (web.dev, MDN, docs da plataforma) e produzir uma documentacao
acionavel em PT-BR.

Plano:
1. `buscar_web` com o id do audit + plataforma (ex: "lighthouse third-party-summary shopify")
2. Escolher 1-2 URLs mais relevantes e usar `fetch_url`
3. Sintetizar em PT-BR: PROBLEMA + SOLUCOES (geral + plataforma) + 2 LINKS
4. Maximo 4 chamadas de tool. Depois disso responda mesmo que incompleto.

Formato OBRIGATORIO da resposta final (Markdown):
## Problema
<paragrafo curto>

## Solucao

**Para sua plataforma ({PLATAFORMA}):**
- ...

**Solucao geral:**
- ...

## Referencias
- [titulo](url)
- [titulo](url)
"""


class CWVPesquisadorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        super().__init__(usuario_id, tools=[buscar_web, fetch_url])

    async def documentar(self, *, audit: dict, plataforma: str) -> str | None:
        prompt_user = (
            f"Plataforma: {plataforma.upper()}\n"
            f"Audit ID: {audit.get('id')}\n"
            f"Titulo: {audit.get('title')}\n"
            f"Descricao Lighthouse: {audit.get('description')}\n"
            f"Valor: {audit.get('displayValue')}\n"
            f"Ganho potencial: {audit.get('savings_ms') or audit.get('savings_bytes') or '—'}\n"
        )
        messages = [
            SystemMessage(content=SYSTEM.replace("{PLATAFORMA}", plataforma.upper())),
            HumanMessage(content=prompt_user),
        ]
        try:
            resp = await self.invoke_with_tools(messages, max_iter=4)
        except Exception as e:
            return None
        return getattr(resp, "content", None)
```

### 2.4 Integração no workflow

Em `backend/app/agents/cwv/workflow.py`, após o `documentador` rodar, para cada problema com `kb_codigo == "outros"` chamar `CWVPesquisadorAgent.documentar(...)` e substituir `documentacao_md` com o resultado (se não-nulo). Limitar a **máximo 3 audits pesquisados por análise** (custo e tempo).

Pseudo-código:

```python
problemas_outros = [p for p in documentados if p["kb_codigo"] == "outros"][:3]
if problemas_outros:
    pesquisador = CWVPesquisadorAgent(usuario_id)
    for p in problemas_outros:
        # `contexto_especifico` já tem audit_id, title, description (via SPEC #1)
        ctx = p["contexto_especifico"]
        audit_dict = {
            "id": ctx.get("audit_id"),
            "title": ctx.get("title"),
            "description": ctx.get("description"),
            "displayValue": ctx.get("display_value"),
            "savings_ms": ctx.get("savings_ms"),
            "savings_bytes": ctx.get("savings_bytes"),
        }
        nova_doc = await pesquisador.documentar(audit=audit_dict, plataforma=plataforma)
        if nova_doc:
            p["documentacao_md"] = nova_doc
            p["pesquisado"] = True
```

Adicionar campo `pesquisado: bool` ao schema do problema (`schemas/cwv.py:CwvProblemaResposta`) e renderizar um badge "🔍 Pesquisado em tempo real" no frontend (`cwv-plano-acao.tsx`) para o usuário saber que aquela seção não veio da KB.

### 2.5 Custo, limites e observabilidade

| Item | Limite | Razão |
|---|---|---|
| Concorrência `fetch_url` | 3 simultâneos | proteger memória/banda |
| Timeout HTTP | 15s | balancear latência |
| Max iters do loop ReAct | 4 | cap de custo |
| Max audits pesquisados por análise | 3 | usuário paga por análise, mas custo extra deve ser limitado |
| Total de chamadas SerpAPI extras | ~3 por análise com fallback | SerpAPI já cobrada por crédito |

**Telemetria:** adicionar log estruturado em cada chamada:

```python
logger.info("CWV pesquisa: audit=%s iters=%d tokens_in=%d tokens_out=%d", ...)
```

E novas chaves em `stats` retornadas para o caller: `pesquisador_usado: bool`, `pesquisas_concluidas: int`.

### 2.6 Dependências Python

Adicionar em `backend/pyproject.toml`:

```toml
readability-lxml = "^0.8.1"
markdownify = "^0.13"
```

## 3. Critérios de aceitação

1. **Tools registradas:** `BaseAgent(... tools=[buscar_web, fetch_url])` faz tool-calling sem erro contra OpenAI gpt-4o-mini ou similar.
2. **Loop ReAct termina:** `invoke_with_tools` nunca passa de `max_iter`; sempre devolve uma `AIMessage`.
3. **Pesquisador melhora doc:** em E2E para uma URL onde o audit cai em `outros`, a documentação renderizada no plano de ação contém URL real de web.dev/MDN + lista acionável em PT-BR (versus o texto genérico atual).
4. **Tempo total não regride >40%:** análise CWV com 0 audits residuais mantém tempo atual (~30s). Análise com 3 audits residuais e pesquisa fica ≤90s.
5. **Falha graceful:** SerpAPI fora do ar / fetch quebrado → pesquisador retorna `None` → mantém doc original da KB.
6. **Frontend mostra badge:** problemas com `pesquisado=true` exibem indicador visual no plano de ação.

## 4. Arquivos afetados

- `backend/app/core/agent_tools.py` (novo) — tools.
- `backend/app/agents/base.py` — aceitar tools + `invoke_with_tools`.
- `backend/app/agents/cwv/pesquisador.py` (novo) — agente pesquisador.
- `backend/app/agents/cwv/workflow.py` — integrar pesquisador após documentador.
- `backend/app/schemas/cwv.py` — campo `pesquisado` em `CwvProblemaResposta`.
- `backend/pyproject.toml` — `readability-lxml`, `markdownify`.
- `backend/tests/unit/test_agent_tools.py` (novo) — mock httpx, validar formato.
- `backend/tests/integration/test_cwv_pesquisador.py` (novo) — VCR ou mock contra SerpAPI.
- `frontend/src/components/cwv/cwv-plano-acao.tsx` — badge "Pesquisado".
- `frontend/src/lib/api/cwv.ts` — campo `pesquisado?: boolean`.

## 5. Fora de escopo

- Tools além de busca/fetch (vai em [[SPEC_CWV_Analisador_Context7]] para docs de libs específicas).
- Cache persistente de resultados de pesquisa (interessante futuramente — mesmo audit pesquisado em 100 análises = 100x custo SerpAPI; primeira versão sem cache).
- Filtrar SSRF de forma estrita (`fetch_url` aceita qualquer URL pública; em produção considerar bloquear IPs privados/localhost — adicionar em iteração futura ou via lib `httpx-ssrf-protect`).
- Streaming progressivo da pesquisa para o frontend.

## 6. Riscos

- **Custo OpenAI sobe:** tool-calling adiciona uma chamada por iteração. Mitigação: cap `max_iter=4` + cap `3 audits pesquisados`.
- **Custo SerpAPI sobe:** ~3 buscas adicionais por análise com fallback. Mitigação: o `serpapi_key` é graceful — sem ele, `buscar_web` retorna erro e o pesquisador devolve `None`, mantendo a doc original.
- **Latência percebida:** análise pode passar de ~30s para ~60-90s quando o pesquisador roda. Mitigação: frontend já tem polling; mostrar "Buscando solução para 2 problemas adicionais…" na barra de progresso (ver `cwv-execucao-client.tsx`).
- **SSRF:** `fetch_url` permite ataque se LLM for induzido a buscar IP interno. Hoje o LLM só recebe descrições de audits do nosso pipeline (não input do usuário direto), risco baixo. Documentar como TODO de hardening.
