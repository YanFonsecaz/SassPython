# SPEC #4 — Tool context7 para docs de framework no analisador CWV

**Status:** ✅ implementado · **Escopo:** backend (nova tool em `core/agent_tools.py`, integração no `CWVPesquisadorAgent`)
**Dependências:** [[SPEC_CWV_Analisador_Tools_Pesquisa]] (essa spec assume o canal `bind_tools` + `CWVPesquisadorAgent` já implementados).
**Esforço estimado:** ~0,5 dia (só a tool + ativação condicional)
**Prioridade:** baixa — só vale depois das specs #1-#3. Útil em casos específicos de framework.

## 1. Contexto e problema

[Context7](https://context7.com) é um serviço que entrega documentação atualizada de bibliotecas/frameworks via HTTP API. Já temos chave configurada em `backend/.env`:

```
API_CONTEXT7_KEY=ctx7sk-7fa1e469-...
```

Casos onde context7 ajuda no CWV:

- Audit menciona problema em Next.js (`next/image`, `next/script`, `app router`) → context7 entrega doc atualizada de como usar `priority`, `placeholder=blur`, `<Script strategy>` etc.
- Audit aponta `js-bundle-grande` num site Shopify Hydrogen → context7 entrega doc atualizada sobre code-splitting em Hydrogen.
- Audit `non-composited-animations` num site React/Vue → fetch da doc da lib de animação (Framer Motion, GSAP) sobre `will-change` e composição.

Casos onde context7 NÃO ajuda (cobertos por SerpAPI da SPEC #3):

- Audits genéricos do Lighthouse (não envolvem framework).
- Conteúdo de web.dev / MDN.
- Blogs de performance.

A diferença chave: **context7 indexa docs de libs/frameworks** com qualidade alta e atualização recente; SerpAPI varre a web inteira. São complementares, não substitutos.

## 2. Solução

### 2.1 Tool `buscar_docs_lib`

Em `backend/app/core/agent_tools.py` (criado em [[SPEC_CWV_Analisador_Tools_Pesquisa]]):

```python
import httpx
from langchain_core.tools import tool
from app.config import settings

_CTX7_BASE = "https://context7.com/api/v1"
_CTX7_TIMEOUT = 15.0


@tool
async def buscar_docs_lib(
    biblioteca: Annotated[str, "Nome da lib/framework (ex: 'nextjs', 'shopify hydrogen', 'tailwind')"],
    pergunta: Annotated[str, "O que voce quer saber (ex: 'lazy load images', 'preload font')"],
    tokens: Annotated[int, "Tamanho aproximado da doc retornada (500-5000)"] = 2000,
) -> str:
    """Busca documentacao oficial atualizada de uma biblioteca/framework via Context7.

    Use APENAS quando o audit envolve uma lib/framework especifico (Next.js, Shopify,
    Tailwind, React, etc.). Para audits genericos de Lighthouse use `buscar_web`.

    Retorna trechos da doc oficial em texto.
    """
    if not settings.api_context7_key:
        return "ERRO: Context7 nao configurado."
    tokens = max(500, min(5000, tokens))
    headers = {"Authorization": f"Bearer {settings.api_context7_key}"}

    # 1) Resolver biblioteca → library_id
    try:
        async with httpx.AsyncClient(timeout=_CTX7_TIMEOUT, headers=headers) as client:
            r = await client.get(f"{_CTX7_BASE}/search", params={"query": biblioteca})
            r.raise_for_status()
            search = r.json()
    except httpx.HTTPError as e:
        return f"ERRO ao resolver biblioteca: {type(e).__name__}"

    results = search.get("results") or []
    if not results:
        return f"Biblioteca '{biblioteca}' nao encontrada no Context7."

    library_id = results[0].get("id")  # ex: "/vercel/next.js"
    if not library_id:
        return "ERRO: resposta sem library_id."

    # 2) Buscar docs com topic = pergunta
    try:
        async with httpx.AsyncClient(timeout=_CTX7_TIMEOUT, headers=headers) as client:
            r = await client.get(
                f"{_CTX7_BASE}{library_id}",
                params={"type": "txt", "tokens": tokens, "topic": pergunta},
            )
            r.raise_for_status()
            docs = r.text
    except httpx.HTTPError as e:
        return f"ERRO ao buscar docs ({library_id}): {type(e).__name__}"

    if len(docs) > tokens * 8:  # safety belt — ~4 chars/token
        docs = docs[: tokens * 8] + "\n\n[...truncado]"
    return f"# Docs: {biblioteca} — {pergunta}\n\n{docs}"
```

### 2.2 `settings.api_context7_key`

Em `backend/app/config.py` (já há campos similares como `serpapi_key`), adicionar:

```python
api_context7_key: str | None = None
```

A Pydantic Settings já lê de env via `env_file=".env"` (ver topo do arquivo).

### 2.3 Ativação condicional no `CWVPesquisadorAgent`

A tool só faz sentido quando há framework detectado. Em `agents/cwv/pesquisador.py` (criado em SPEC #3):

```python
FRAMEWORKS_SUPORTADOS_CTX7 = {
    "nextjs", "react", "vue", "nuxtjs", "svelte", "sveltekit",
    "shopify", "hydrogen", "tailwind", "astro", "remix", "angular",
}


class CWVPesquisadorAgent(BaseAgent):
    def __init__(self, usuario_id: str, plataforma: str):
        tools = [buscar_web, fetch_url]
        if plataforma in FRAMEWORKS_SUPORTADOS_CTX7 and settings.api_context7_key:
            tools.append(buscar_docs_lib)
        super().__init__(usuario_id, tools=tools)
        self.plataforma = plataforma
```

E o `SYSTEM` ganha uma linha:

```text
Se a plataforma e um framework conhecido (Next.js, Shopify Hydrogen, Tailwind, etc.) e
o audit envolve API/feature dessa lib, prefira `buscar_docs_lib` em vez de `buscar_web`.
```

### 2.4 Caching curto-prazo (opcional mas recomendado)

Context7 cobra por requisição (cota mensal). Mesmo audit + plataforma em N análises ≠ N chamadas. Adicionar cache simples baseado em Redis (já temos `redis_pool`):

```python
import hashlib, json

async def _cache_get(key: str) -> str | None:
    r = await get_redis_pool()
    val = await r.get(f"ctx7:{key}")
    return val.decode() if val else None

async def _cache_set(key: str, value: str, ttl: int = 86400):
    r = await get_redis_pool()
    await r.set(f"ctx7:{key}", value, ex=ttl)


@tool
async def buscar_docs_lib(biblioteca, pergunta, tokens=2000):
    cache_key = hashlib.sha256(f"{biblioteca}|{pergunta}|{tokens}".encode()).hexdigest()[:16]
    cached = await _cache_get(cache_key)
    if cached:
        return cached
    # ... lógica acima ...
    await _cache_set(cache_key, result)
    return result
```

TTL 24h é razoável (docs de lib não mudam tanto). Se cota da chave estourar, cache evita degradação total.

### 2.5 Observabilidade

Log estruturado em cada chamada:

```python
logger.info(
    "ctx7_query lib=%s topic=%s tokens=%d hit=%s",
    biblioteca, pergunta, tokens, "cache" if cached else "live",
)
```

Métrica agregada em `stats` retornado para o caller:

```python
stats["ctx7_chamadas"] = int  # quantas calls live (não cache)
```

## 3. Critérios de aceitação

1. **Tool registrada condicionalmente:** com `plataforma=shopify` a tool é incluída; com `plataforma=geral` não.
2. **Resposta válida:** chamada manual `await buscar_docs_lib("nextjs", "next/image priority")` retorna texto com mention de `priority` prop em <30s.
3. **Falha graceful:** se `API_CONTEXT7_KEY` ausente ou inválida, tool retorna `"ERRO: ..."` e o `CWVPesquisadorAgent` continua com `buscar_web`+`fetch_url`.
4. **Cache:** segunda chamada idêntica em <24h retorna do Redis (log mostra `hit=cache`).
5. **E2E:** análise CWV de URL em Next.js com audit residual produz doc que cita conceito real de Next.js (`<Image priority>`, `next/script strategy`, etc.).

## 4. Arquivos afetados

- `backend/app/core/agent_tools.py` — nova tool `buscar_docs_lib` + helpers de cache.
- `backend/app/config.py` — campo `api_context7_key`.
- `backend/app/agents/cwv/pesquisador.py` — incluir tool condicionalmente.
- `backend/tests/unit/test_agent_tools.py` — mock httpx para context7.

## 5. Fora de escopo

- Integrar context7 via cliente MCP (mais complexo, exige sidecar npx). HTTP direto é suficiente.
- Usar context7 fora do CWV (gerador de artigo, inlinks). Pode ser feito depois reusando a tool.
- Resolver library_id ambíguo (ex: "react" pode ser React core ou react-native). Primeiro resultado é a heurística atual.

## 6. Riscos

- **Cota Context7:** sem cache, custo escala linear com volume. Cache Redis (item 2.4) é praticamente obrigatório em produção.
- **Latência:** 2 chamadas HTTP encadeadas (`search` + fetch doc) podem somar 5-10s. Limitar `tokens` a 2000 ajuda.
- **Conteúdo desatualizado:** Context7 indexa docs públicas; pode estar desatualizado vs. release recente de uma lib. Aceito — é melhor que nada.
- **Dependência externa:** Context7 fora do ar → `buscar_docs_lib` retorna erro, mas SerpAPI cobre. Aceitável.

## 7. Custo aproximado

| Cenário | Chamadas Context7/análise | Latência adicional |
|---|---|---|
| Análise sem audits residuais | 0 | 0 |
| Análise com 3 audits residuais, plataforma=shopify | 0-3 (LLM decide) | 0-15s |
| Mesma análise, segunda vez em <24h | 0 (cache) | <100ms |
