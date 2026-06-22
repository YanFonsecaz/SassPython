from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import BaseAgent
from app.config import settings
from app.core.agent_tools import buscar_docs_lib, buscar_web, fetch_url

FRAMEWORKS_SUPORTADOS_CTX7 = {
    "nextjs", "react", "vue", "nuxtjs", "svelte", "sveltekit",
    "shopify", "hydrogen", "tailwind", "astro", "remix", "angular",
}

SYSTEM = """Voce documenta problemas de Core Web Vitals que nao tem entrada na nossa
base de conhecimento. Use as tools `buscar_web` e `fetch_url` para encontrar a melhor
documentacao oficial (web.dev, MDN, docs da plataforma) e produzir uma documentacao
acionavel em PT-BR.

Se a plataforma e um framework conhecido (Next.js, Shopify Hydrogen, Tailwind, etc.) e
o audit envolve API/feature dessa lib, prefira `buscar_docs_lib` em vez de `buscar_web`.

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
    def __init__(self, usuario_id: str, plataforma: str):
        tools = [buscar_web, fetch_url]
        if plataforma.lower() in FRAMEWORKS_SUPORTADOS_CTX7 and settings.api_context7_key:
            tools.append(buscar_docs_lib)

        model = settings.cwv_pesquisador_llm_model if settings.llm_provider == "openai" else None
        super().__init__(
            usuario_id,
            tools=tools,
            model=model,
            temperature=settings.cwv_pesquisador_llm_temperature,
        )
        self.plataforma = plataforma

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
        except Exception:
            return None
        return getattr(resp, "content", None)
