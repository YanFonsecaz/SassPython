# SPEC — Ferramenta "Core Web Vitals"

**Status:** a aplicar · **Escopo:** backend (novo workflow + agentes + rota + worker + 2 tabelas novas) + frontend (formulário + dashboard histórico) + cobrança · **Crédito:** modelo por URL analisada
**Reusos:** padrão de `ExecucaoFerramenta` + LangGraph + arq + `BaseAgent` + `credito_service` já estabelecidos em [[SPEC_Ferramenta_Distribuir_Inlinks]]
**Specs irmãs:** [[SPEC_CWV_Base_Conhecimento]] (catálogo curado de problemas) · [[SPEC_CWV_Dashboard_Historico]] (UI de acompanhamento por URL)

## 1. Visão geral

Ferramenta de análise técnica de Core Web Vitals (LCP, CLS, INP, FCP, TTFB) com diagnóstico automatizado e plano de ação documentado por URL.

### 1.1 Problema

Usuários do SaaS (gestores de SEO de e-commerces e blogs) precisam:
- Saber quais URLs do site têm problemas de CWV graves o suficiente para impactar ranking
- Entender **o quê** está causando o problema técnico (sem ter conhecimento de dev)
- Ter um **plano de ação documentado** com solução adaptada à plataforma deles (VTEX, WordPress, Next.js, Shopify, etc.)
- Acompanhar a melhora ao longo do tempo conforme aplicam correções

### 1.2 Fluxo do usuário

1. Acessa `/ferramentas/core-web-vitals`
2. Seleciona cliente
3. Preenche URLs agrupadas por template (home, categoria, produto, blog, blogpost, outros)
4. Confirma custo, dispara análise
5. Aguarda processamento (~1-3 min por URL)
6. Acessa dashboard por URL: vê accordion ordenado por prioridade com problemas + soluções
7. Aplica correções no site
8. Volta no dashboard, clica "Re-analisar agora", compara com análise anterior

### 1.3 Diferenciais frente a ferramentas existentes (PSI, GTMetrix)

- **Solução adaptada à plataforma** (não só "otimize imagens", mas "no VTEX, use `<img-vtex>` com loader `srcset`")
- **Histórico temporal por URL** com diff entre análises
- **Priorização inteligente** (impacto × esforço) — usuário sabe por onde começar
- **Multi-tenant** — gestor de SEO atende N clientes na mesma ferramenta

## 2. Modelo de dados

### 2.1 Tabelas novas (Alembic migration)

```sql
cwv_analise:
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  execucao_id           UUID NOT NULL REFERENCES execucoes_ferramentas(id) ON DELETE CASCADE
  cliente_id            UUID NOT NULL REFERENCES clientes(id)
  usuario_id            UUID NOT NULL REFERENCES usuarios(id)
  url                   TEXT NOT NULL
  url_canonica          TEXT NOT NULL          -- normalizada (sem fragment, sem trailing slash)
  template_tipo         VARCHAR(20) NOT NULL   -- home|categoria|produto|blog|blogpost|outros
  estrategia            VARCHAR(10) NOT NULL DEFAULT 'mobile'  -- mobile|desktop
  plataforma_detectada  VARCHAR(20) NOT NULL DEFAULT 'desconhecida'
  score_performance     INTEGER                -- 0-100, vindo do PSI
  lcp_ms                NUMERIC(10,2)
  cls                   NUMERIC(6,4)
  inp_ms                NUMERIC(10,2)
  fcp_ms                NUMERIC(10,2)
  ttfb_ms               NUMERIC(10,2)
  tbt_ms                NUMERIC(10,2)
  raw_psi_json          JSONB NOT NULL         -- backup completo do payload PSI
  status                VARCHAR(20) NOT NULL   -- sucesso|falhou_psi|falhou_parsing
  erro_msg              VARCHAR(500)
  criado_em             TIMESTAMPTZ NOT NULL DEFAULT now()

  CONSTRAINT cwv_analise_template_check CHECK (template_tipo IN ('home','categoria','produto','blog','blogpost','outros'))
  CONSTRAINT cwv_analise_estrategia_check CHECK (estrategia IN ('mobile','desktop'))

INDEX ix_cwv_analise_cliente_url_data ON cwv_analise (cliente_id, url_canonica, criado_em DESC);
INDEX ix_cwv_analise_execucao ON cwv_analise (execucao_id);
INDEX ix_cwv_analise_usuario ON cwv_analise (usuario_id);
```

```sql
cwv_problema:
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid()
  analise_id            UUID NOT NULL REFERENCES cwv_analise(id) ON DELETE CASCADE
  kb_codigo             VARCHAR(80) NOT NULL   -- ref para entry da base curada
  titulo                TEXT NOT NULL          -- titulo final (pode ser custom da KB)
  severidade            SMALLINT NOT NULL      -- 1-5
  prioridade_ordem      INTEGER NOT NULL       -- 1, 2, 3, ... (ordem final apresentação)
  metricas_afetadas     JSONB NOT NULL         -- ["LCP","CLS"]
  contexto_especifico   JSONB                  -- { "elemento": "img.hero", "tamanho_bytes": 2400000, ... }
  documentacao_md       TEXT NOT NULL          -- markdown renderizado pro accordion
  criado_em             TIMESTAMPTZ NOT NULL DEFAULT now()

  CONSTRAINT cwv_problema_severidade_check CHECK (severidade BETWEEN 1 AND 5)

INDEX ix_cwv_problema_analise ON cwv_problema (analise_id, prioridade_ordem);
```

### 2.2 Reuso de tabelas existentes

- **`execucoes_ferramentas`**: nova entrada `ferramenta='core_web_vitals'`. `entrada_json` guarda `{cliente_id, urls_por_template, estrategia}`. `resultado_json` guarda resumo `{n_urls_analisadas, n_urls_falharam, analise_ids: [...], score_medio}` — detalhe completo fica nas tabelas novas.
- **`creditos`/`transacoes_credito`**: cobrança pelo padrão atual.

### 2.3 Migration

Arquivo novo em `backend/migrations/versions/` seguindo padrão. Inclui:
- `op.create_table` para `cwv_analise` e `cwv_problema`
- Constraints + índices acima
- Downgrade que faz `drop_table` na ordem reversa

## 3. Backend

### 3.1 Schemas Pydantic (`app/schemas/cwv.py`, novo)

```python
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl, field_validator

TemplateTipo = Literal["home", "categoria", "produto", "blog", "blogpost", "outros"]
Estrategia = Literal["mobile", "desktop"]


class UrlsPorTemplate(BaseModel):
    home: list[HttpUrl] = Field(default_factory=list, max_length=10)
    categoria: list[HttpUrl] = Field(default_factory=list, max_length=20)
    produto: list[HttpUrl] = Field(default_factory=list, max_length=20)
    blog: list[HttpUrl] = Field(default_factory=list, max_length=10)
    blogpost: list[HttpUrl] = Field(default_factory=list, max_length=20)
    outros: list[HttpUrl] = Field(default_factory=list, max_length=20)

    @field_validator("*")
    @classmethod
    def dedup(cls, v: list[HttpUrl]) -> list[HttpUrl]:
        seen = set()
        out = []
        for u in v:
            s = str(u)
            if s not in seen:
                seen.add(s)
                out.append(u)
        return out

    def total(self) -> int:
        return sum(len(getattr(self, f)) for f in self.model_fields)

    def itens(self) -> list[tuple[str, str]]:
        result = []
        for template in ("home", "categoria", "produto", "blog", "blogpost", "outros"):
            for url in getattr(self, template):
                result.append((template, str(url)))
        return result


class AnalisarRequest(BaseModel):
    cliente_id: UUID
    urls_por_template: UrlsPorTemplate
    estrategia: Estrategia = "mobile"

    @field_validator("urls_por_template")
    @classmethod
    def pelo_menos_uma_url(cls, v: UrlsPorTemplate) -> UrlsPorTemplate:
        if v.total() == 0:
            raise ValueError("Informe pelo menos uma URL em algum template")
        if v.total() > 50:
            raise ValueError("Máximo de 50 URLs por execução")
        return v


class ProblemaResposta(BaseModel):
    id: UUID
    kb_codigo: str
    titulo: str
    severidade: int
    prioridade_ordem: int
    metricas_afetadas: list[str]
    contexto_especifico: dict
    documentacao_md: str


class AnaliseResposta(BaseModel):
    id: UUID
    url: str
    url_canonica: str
    template_tipo: str
    plataforma_detectada: str
    estrategia: str
    score_performance: int | None
    lcp_ms: float | None
    cls: float | None
    inp_ms: float | None
    fcp_ms: float | None
    ttfb_ms: float | None
    tbt_ms: float | None
    status: str
    erro_msg: str | None
    criado_em: str
    problemas: list[ProblemaResposta]


class AnaliseResumoResposta(BaseModel):
    id: UUID
    url_canonica: str
    template_tipo: str
    score_performance: int | None
    lcp_ms: float | None
    cls: float | None
    inp_ms: float | None
    n_problemas: int
    n_problemas_alta_severidade: int
    criado_em: str


class HistoricoUrlResposta(BaseModel):
    url_canonica: str
    template_tipo: str
    plataforma_detectada: str
    analises: list[AnaliseResumoResposta]  # ordenado desc por data
```

### 3.2 Cliente PSI (`app/services/cwv_psi_client.py`, novo)

```python
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
TIMEOUT_SECONDS = 90  # PSI pode levar até 60s, margem


class PSIError(Exception):
    pass


async def fetch_psi(url: str, estrategia: str = "mobile") -> dict:
    """
    Chama PageSpeed Insights API e retorna o payload Lighthouse completo.
    Levanta PSIError em falha de rede, timeout ou resposta inválida.
    """
    params = {
        "url": url,
        "strategy": estrategia,
        "category": "performance",
    }
    if settings.psi_api_key:
        params["key"] = settings.psi_api_key

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        try:
            resp = await client.get(PSI_ENDPOINT, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning("PSI HTTP %s para url=%s: %s", e.response.status_code, url, e.response.text[:500])
            raise PSIError(f"PSI retornou {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.warning("PSI erro de rede para url=%s: %s", url, e)
            raise PSIError(f"Erro de rede: {e}") from e

    data = resp.json()
    if "lighthouseResult" not in data:
        raise PSIError(f"Resposta PSI sem lighthouseResult: {data.get('error', {}).get('message', 'desconhecido')}")
    return data


def parse_psi(payload: dict) -> dict:
    """
    Extrai métricas estruturadas do payload PSI.
    Retorna dict com: score_performance, lcp_ms, cls, inp_ms, fcp_ms, ttfb_ms, tbt_ms,
                       audits_falhos: list[dict], headers, html_inicial.
    """
    lh = payload["lighthouseResult"]
    categories = lh.get("categories", {})
    audits = lh.get("audits", {})

    def audit_val(key: str, field: str = "numericValue") -> float | None:
        a = audits.get(key, {})
        return a.get(field) if a.get("score") is not None else None

    return {
        "score_performance": int((categories.get("performance", {}).get("score") or 0) * 100),
        "lcp_ms": audit_val("largest-contentful-paint"),
        "cls": audit_val("cumulative-layout-shift"),
        "inp_ms": audit_val("interaction-to-next-paint") or audit_val("max-potential-fid"),
        "fcp_ms": audit_val("first-contentful-paint"),
        "ttfb_ms": audit_val("server-response-time"),
        "tbt_ms": audit_val("total-blocking-time"),
        "audits_falhos": [
            {
                "id": k,
                "title": a.get("title"),
                "description": a.get("description"),
                "score": a.get("score"),
                "displayValue": a.get("displayValue"),
                "details": a.get("details"),
            }
            for k, a in audits.items()
            if a.get("score") is not None and a["score"] < 0.9 and a.get("scoreDisplayMode") not in ("informative", "notApplicable")
        ],
        "html_inicial": lh.get("finalUrl"),
        "user_agent": lh.get("userAgent"),
    }
```

### 3.3 Detector de plataforma (`app/services/cwv_plataforma.py`, novo)

```python
import re
from typing import Literal

Plataforma = Literal["vtex", "wordpress", "nextjs", "shopify", "wix", "magento", "outros", "desconhecida"]


def detectar_plataforma(psi_payload: dict) -> Plataforma:
    """
    Detecta plataforma a partir do payload PSI.
    Examina screenshot, scripts, headers (via diagnosticos do Lighthouse).
    """
    lh = psi_payload.get("lighthouseResult", {})
    audits = lh.get("audits", {})

    # Lighthouse já roda detecção via stack-packs em "stacks"
    stacks = lh.get("stackPacks", [])
    for stack in stacks:
        sid = stack.get("id", "").lower()
        if sid == "wordpress":
            return "wordpress"
        if sid == "magento":
            return "magento"
        if sid == "wix":
            return "wix"
        if sid == "next":
            return "nextjs"

    # Fallback: inspeciona network requests via "network-requests" audit
    network = audits.get("network-requests", {}).get("details", {}).get("items", [])
    urls = [item.get("url", "") for item in network]
    blob = " ".join(urls).lower()

    if "vtexassets.com" in blob or "/vtex/" in blob or "myvtex.com" in blob:
        return "vtex"
    if "wp-content" in blob or "wp-includes" in blob:
        return "wordpress"
    if "_next/static" in blob:
        return "nextjs"
    if "cdn.shopify.com" in blob or "myshopify.com" in blob:
        return "shopify"

    return "desconhecida"
```

### 3.4 Workflow LangGraph (`app/agents/cwv/workflow.py`, novo)

Cria subpasta `app/agents/cwv/` com `__init__.py`, `analisador.py`, `documentador.py`, `priorizador.py`, `workflow.py`.

```python
# app/agents/cwv/workflow.py
import asyncio
import logging
from typing import Any, TypedDict
from langgraph.graph import END, StateGraph
from app.agents.workflow_helpers import workflow_node
from app.config import settings

logger = logging.getLogger(__name__)

SEMAFORO_PSI = asyncio.Semaphore(5)   # cota PSI 240/min — 5 paralelas seguras
SEMAFORO_LLM = asyncio.Semaphore(3)


class EstadoCWV(TypedDict):
    execucao_id: str
    usuario_id: str
    cliente_id: str
    urls_por_template: list[tuple[str, str]]  # [(template, url), ...]
    estrategia: str
    psi_resultados: dict[str, dict]      # url -> {payload, parsed} ou {erro}
    plataformas: dict[str, str]          # url -> plataforma
    problemas_por_url: dict[str, list[dict]]
    analises_persistidas: list[str]      # ids de cwv_analise


@workflow_node("coletar_psi", "Coletando métricas Core Web Vitals...")
async def node_coletar_psi(estado: EstadoCWV, session) -> dict[str, Any]:
    from app.services.cwv_psi_client import PSIError, fetch_psi, parse_psi

    async def coletar_uma(url: str) -> tuple[str, dict]:
        async with SEMAFORO_PSI:
            try:
                payload = await fetch_psi(url, estado["estrategia"])
                parsed = parse_psi(payload)
                return url, {"ok": True, "payload": payload, "parsed": parsed}
            except PSIError as e:
                return url, {"ok": False, "erro": str(e)}

    tarefas = [coletar_uma(url) for _, url in estado["urls_por_template"]]
    resultados = await asyncio.gather(*tarefas)
    return {"psi_resultados": dict(resultados)}


@workflow_node("detectar_plataformas", "Detectando plataformas...")
async def node_detectar_plataformas(estado: EstadoCWV, session) -> dict[str, Any]:
    from app.services.cwv_plataforma import detectar_plataforma

    plataformas = {}
    for url, r in estado["psi_resultados"].items():
        if r["ok"]:
            plataformas[url] = detectar_plataforma(r["payload"])
        else:
            plataformas[url] = "desconhecida"
    return {"plataformas": plataformas}


@workflow_node("analisar_seo", "Identificando problemas técnicos...")
async def node_analisar_seo(estado: EstadoCWV, session) -> dict[str, Any]:
    from app.agents.cwv.analisador import CWVAnalisadorAgent

    agente = CWVAnalisadorAgent(estado["usuario_id"])
    problemas_por_url = {}

    async def analisar_uma(url: str):
        async with SEMAFORO_LLM:
            r = estado["psi_resultados"][url]
            if not r["ok"]:
                return url, []
            problemas = await agente.analisar(
                audits_falhos=r["parsed"]["audits_falhos"],
                plataforma=estado["plataformas"][url],
                metricas=r["parsed"],
            )
            return url, problemas

    resultados = await asyncio.gather(*[analisar_uma(url) for _, url in estado["urls_por_template"]])
    for url, probs in resultados:
        problemas_por_url[url] = probs
    return {"problemas_por_url": problemas_por_url}


@workflow_node("documentar", "Gerando documentação por problema...")
async def node_documentar(estado: EstadoCWV, session) -> dict[str, Any]:
    from app.agents.cwv.documentador import CWVDocumentadorAgent

    agente = CWVDocumentadorAgent(estado["usuario_id"])
    novo = {}

    async def doc_uma(url: str, problemas: list[dict]):
        if not problemas:
            return url, []
        async with SEMAFORO_LLM:
            documentados = await agente.documentar(
                problemas=problemas,
                plataforma=estado["plataformas"][url],
            )
            return url, documentados

    resultados = await asyncio.gather(
        *[doc_uma(url, probs) for url, probs in estado["problemas_por_url"].items()]
    )
    for url, docs in resultados:
        novo[url] = docs
    return {"problemas_por_url": novo}


@workflow_node("priorizar", "Priorizando problemas...")
async def node_priorizar(estado: EstadoCWV, session) -> dict[str, Any]:
    from app.agents.cwv.priorizador import priorizar_problemas

    novo = {}
    for url, problemas in estado["problemas_por_url"].items():
        novo[url] = priorizar_problemas(problemas, metricas=estado["psi_resultados"][url].get("parsed"))
    return {"problemas_por_url": novo}


@workflow_node("persistir", "Salvando análises...")
async def node_persistir(estado: EstadoCWV, session) -> dict[str, Any]:
    from app.services.cwv_persistencia import persistir_analise

    analises_ids = []
    for template, url in estado["urls_por_template"]:
        r = estado["psi_resultados"][url]
        analise_id = await persistir_analise(
            session,
            execucao_id=estado["execucao_id"],
            cliente_id=estado["cliente_id"],
            usuario_id=estado["usuario_id"],
            url=url,
            template=template,
            estrategia=estado["estrategia"],
            plataforma=estado["plataformas"].get(url, "desconhecida"),
            psi_resultado=r,
            problemas=estado["problemas_por_url"].get(url, []),
        )
        analises_ids.append(analise_id)
    return {"analises_persistidas": analises_ids}


def construir_workflow():
    g = StateGraph(EstadoCWV)
    g.add_node("coletar_psi", node_coletar_psi)
    g.add_node("detectar_plataformas", node_detectar_plataformas)
    g.add_node("analisar_seo", node_analisar_seo)
    g.add_node("documentar", node_documentar)
    g.add_node("priorizar", node_priorizar)
    g.add_node("persistir", node_persistir)
    g.set_entry_point("coletar_psi")
    g.add_edge("coletar_psi", "detectar_plataformas")
    g.add_edge("detectar_plataformas", "analisar_seo")
    g.add_edge("analisar_seo", "documentar")
    g.add_edge("documentar", "priorizar")
    g.add_edge("priorizar", "persistir")
    g.add_edge("persistir", END)
    return g.compile()
```

### 3.5 Agentes

#### 3.5.1 Analisador (`app/agents/cwv/analisador.py`)

Mapeia audits falhos do Lighthouse para `kb_codigo` da base curada. Recebe lista de audits + plataforma + métricas. Retorna lista de problemas identificados com contexto extraído.

```python
from app.agents.base import BaseAgent
from app.services.cwv_kb import listar_kb_codigos, mapeamento_audit_kb
from pydantic import BaseModel


class ProblemaIdentificado(BaseModel):
    kb_codigo: str
    contexto_especifico: dict  # ex: {"elemento": "img.hero", "tamanho_bytes": 2400000}
    audits_origem: list[str]   # ids de audits do Lighthouse que originaram


class ListaProblemas(BaseModel):
    problemas: list[ProblemaIdentificado]


class CWVAnalisadorAgent(BaseAgent):
    async def analisar(self, *, audits_falhos: list[dict], plataforma: str, metricas: dict) -> list[dict]:
        # Fast path: muitos audits têm mapeamento 1:1 direto pra kb_codigo via tabela fixa
        diretos = mapeamento_audit_kb()
        identificados: list[ProblemaIdentificado] = []

        # Pega os de mapeamento direto sem chamar LLM
        for audit in audits_falhos:
            if audit["id"] in diretos:
                kb = diretos[audit["id"]]
                contexto = _extrair_contexto(audit)
                identificados.append(ProblemaIdentificado(
                    kb_codigo=kb,
                    contexto_especifico=contexto,
                    audits_origem=[audit["id"]],
                ))

        # Audits sem mapeamento direto: passa por LLM
        audits_residuais = [a for a in audits_falhos if a["id"] not in diretos]
        if audits_residuais:
            prompt = _montar_prompt_analise(audits_residuais, listar_kb_codigos(), plataforma)
            resp: ListaProblemas = await self.invoke_structured(prompt, ListaProblemas)
            identificados.extend(resp.problemas)

        # Dedup por kb_codigo (consolida contextos)
        return _dedup_e_consolidar(identificados)


def _extrair_contexto(audit: dict) -> dict:
    """Extrai elemento + valores específicos do audit details."""
    details = audit.get("details") or {}
    items = details.get("items") or []
    return {
        "display_value": audit.get("displayValue"),
        "items": items[:5],  # limita pra não estourar token
    }


def _montar_prompt_analise(audits_residuais, kb_codigos, plataforma): ...
def _dedup_e_consolidar(lista): ...
```

#### 3.5.2 Documentador (`app/agents/cwv/documentador.py`)

Para cada problema identificado, busca entrada na KB curada e gera markdown final adaptado à plataforma + contexto específico. **Não inventa conteúdo** — só formata KB + contexto.

```python
from app.agents.base import BaseAgent
from app.services.cwv_kb import buscar_entrada


class CWVDocumentadorAgent(BaseAgent):
    async def documentar(self, *, problemas: list[dict], plataforma: str) -> list[dict]:
        # Pra cada problema, busca KB e monta documentação
        # 80% dos casos: formatação determinística direto da KB (sem LLM)
        # 20% dos casos: contexto complexo justifica adaptação via LLM

        documentados = []
        for p in problemas:
            entrada_kb = buscar_entrada(p["kb_codigo"])
            if entrada_kb is None:
                continue  # codigo inválido, descarta

            doc_md = await self._gerar_doc(entrada_kb, plataforma, p["contexto_especifico"])
            documentados.append({
                **p,
                "titulo": entrada_kb["titulo"],
                "severidade": entrada_kb["severidade"],
                "metricas_afetadas": entrada_kb["metricas_afetadas"],
                "documentacao_md": doc_md,
            })
        return documentados

    async def _gerar_doc(self, entrada_kb: dict, plataforma: str, contexto: dict) -> str:
        # Template determinístico, sem LLM:
        partes = [
            f"## Problema\n\n{entrada_kb['descricao']}\n",
        ]
        if contexto.get("display_value"):
            partes.append(f"**Valor medido:** {contexto['display_value']}\n")
        if contexto.get("items"):
            partes.append("**Elementos afetados:**\n")
            for item in contexto["items"][:3]:
                partes.append(f"- `{item.get('url', item.get('node', {}).get('selector', '?'))}`\n")

        partes.append("\n## Solução\n\n")
        solucoes = entrada_kb["solucoes"]
        if plataforma in solucoes:
            partes.append(f"**Para sua plataforma ({plataforma.upper()}):**\n\n{solucoes[plataforma]}\n\n")
        partes.append(f"**Solução geral:**\n\n{solucoes['geral']}\n")
        return "".join(partes)
```

> A chamada LLM no `_gerar_doc` é opcional. Para V1, formatação puramente determinística é suficiente — a KB já tem texto bem escrito por plataforma. LLM só entra se quisermos adaptar contextualmente em V2.

#### 3.5.3 Priorizador (`app/agents/cwv/priorizador.py`)

Rule-based puro (sem LLM), com tiebreak por severidade declarada.

```python
PESO_METRICA = {"LCP": 5, "CLS": 4, "INP": 4, "TBT": 3, "FCP": 2, "TTFB": 2}


def priorizar_problemas(problemas: list[dict], metricas: dict | None) -> list[dict]:
    def score(p: dict) -> float:
        peso = sum(PESO_METRICA.get(m, 1) for m in p["metricas_afetadas"])
        return p["severidade"] * peso

    ordenados = sorted(problemas, key=score, reverse=True)
    for i, p in enumerate(ordenados):
        p["prioridade_ordem"] = i + 1
    return ordenados
```

### 3.6 Serviço de persistência (`app/services/cwv_persistencia.py`, novo)

Função única `persistir_analise(...)` que:
1. Normaliza URL (`url_canonica`)
2. Insere `cwv_analise` com métricas + raw payload + status
3. Insere N `cwv_problema` em batch
4. Retorna `analise_id`

### 3.7 Rota (`app/routers/ferramentas_cwv.py`, novo)

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_user, get_db, rate_limit_autenticado
from app.models.usuario import Usuario
from app.schemas.cwv import (
    AnalisarRequest, AnaliseResposta, HistoricoUrlResposta,
)
from app.services import ferramenta_service

router = APIRouter(prefix="/api/ferramentas/cwv", tags=["core-web-vitals"])


@router.get("/custo")
async def custo(n_urls: int, usuario: Usuario = Depends(get_current_user)):
    return {"custo": ferramenta_service.calcular_custo_cwv(n_urls)}


@router.post("/analisar", status_code=202)
async def analisar(
    body: AnalisarRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("cwv_analisar", max_requests=3, window_seconds=300)),
):
    # 1. Valida cliente pertence ao usuário
    # 2. Calcula custo, reserva créditos
    # 3. Cria ExecucaoFerramenta(ferramenta='core_web_vitals')
    # 4. Enfileira no arq: executar_workflow_cwv(execucao_id)
    # 5. Retorna {id, status: 'enfileirado', n_urls, custo}
    ...


@router.get("/execucao/{execucao_id}")
async def buscar_execucao(execucao_id: str, ...):
    # Retorna {status, etapa_atual, analises_ids: [...] se concluída}
    ...


@router.get("/analise/{analise_id}", response_model=AnaliseResposta)
async def buscar_analise(analise_id: str, ...):
    # Retorna análise completa com problemas[]
    ...


@router.get("/historico", response_model=list[HistoricoUrlResposta])
async def listar_historico(cliente_id: str, ...):
    # Retorna lista agrupada por url_canonica, cada url com analises[] desc
    ...


@router.post("/reanalisar/{analise_id}", status_code=202)
async def reanalisar(analise_id: str, ...):
    # Cria nova execução reusando url + template + estrategia da análise anterior
    ...
```

Registrar em `app/main.py` junto com outros routers de ferramentas.

### 3.8 Worker (`app/worker.py`)

```python
async def executar_workflow_cwv(ctx, execucao_id: str):
    logger.info("Iniciando CWV execucao_id=%s", execucao_id)
    try:
        from app.agents.cwv.workflow import executar_workflow_cwv
        await executar_workflow_cwv(execucao_id)
        logger.info("CWV concluído execucao_id=%s", execucao_id)
    except Exception as e:
        logger.error("CWV falhou execucao_id=%s: %s", execucao_id, e)
        # Marca execucao como erro, libera créditos reservados
```

Adicionar em `WorkerSettings.functions`.

### 3.9 Cobrança (`app/services/ferramenta_service.py`)

```python
CUSTO_CWV_POR_URL = 5  # créditos


def calcular_custo_cwv(n_urls: int) -> int:
    return n_urls * CUSTO_CWV_POR_URL


async def finalizar_sucesso_cwv(execucao: ExecucaoFerramenta) -> int:
    """
    Política: cobra por URL com análise bem-sucedida.
    URLs que falharam no PSI não são cobradas.
    """
    resultado = execucao.resultado_json or {}
    n_sucesso = resultado.get("n_urls_analisadas", 0)
    return n_sucesso * CUSTO_CWV_POR_URL
```

### 3.10 Settings (`app/config.py`)

Adicionar:

```python
psi_api_key: str | None = None  # opcional; sem chave, usa cota anônima (25k/dia)
cwv_workflow_timeout: int = 1200  # 20 min (50 URLs × ~20s PSI + processamento)
cwv_max_urls_por_execucao: int = 50
```

## 4. Frontend

### 4.1 Página de formulário (`/ferramentas/core-web-vitals/page.tsx`)

Layout:

```
┌─────────────────────────────────────────────────────────────┐
│ Core Web Vitals                                              │
│ Analise URLs do site, receba diagnóstico e plano de ação.   │
├─────────────────────────────────────────────────────────────┤
│ Cliente: [select com clientes do usuário]                    │
│ Estratégia: ( ) Desktop  (•) Mobile                          │
├─────────────────────────────────────────────────────────────┤
│ ┌─ Home (1 max) ─────────┐ ┌─ Categoria (20 max) ─────────┐ │
│ │ [textarea uma por      │ │ [textarea]                    │ │
│ │  linha]                │ │                                │ │
│ │ 0 / 1 URLs             │ │ 3 / 20 URLs                   │ │
│ └────────────────────────┘ └───────────────────────────────┘ │
│ ┌─ Produto (20 max) ─────┐ ┌─ Blog (10 max) ──────────────┐ │
│ │ ...                    │ │ ...                            │ │
│ └────────────────────────┘ └───────────────────────────────┘ │
│ ┌─ Blogpost (20 max) ────┐ ┌─ Outros (20 max) ────────────┐ │
│ │ ...                    │ │ ...                            │ │
│ └────────────────────────┘ └───────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ Total: 12 URLs · Custo: 60 créditos                          │
│ [ Cancelar ]                              [ Analisar agora ] │
└─────────────────────────────────────────────────────────────┘
```

Validação client-side: URLs HTTPS, limite por template, máximo total 50.

Ao submeter: POST `/api/ferramentas/cwv/analisar`, recebe `execucao_id`, redireciona para `/ferramentas/core-web-vitals/execucao/{id}` (tela de polling).

### 4.2 Tela de polling (`/ferramentas/core-web-vitals/execucao/[id]/page.tsx`)

Padrão do `gerar-artigo`: barra de progresso por etapa (`coletar_psi`, `detectar_plataformas`, `analisar_seo`, `documentar`, `priorizar`, `persistir`), polling a cada 3s. Ao concluir, redireciona para `/ferramentas/core-web-vitals/historico/{cliente_id}`.

### 4.3 Listagem de histórico (`/ferramentas/core-web-vitals/historico/[clienteId]/page.tsx`)

Lista URLs analisadas para o cliente, agrupadas por template. Cada card:

```
🟢 https://exemplo.com.br/produto/x
   Template: produto · Plataforma: VTEX
   Score: 78 (mobile) · LCP 2.1s · CLS 0.05 · INP 180ms
   Última análise: há 2 horas · 7 problemas (2 críticos)
   [Abrir dashboard]
```

Filtros: por template, por score (faixa), por plataforma.

### 4.4 Dashboard por URL

Ver [[SPEC_CWV_Dashboard_Historico]] para detalhe completo (chart histórico, accordion de problemas, comparador, botão re-analisar).

### 4.5 Navegação

Sidebar: adicionar item **Core Web Vitals** no grupo "Ferramentas", com ícone de gauge/speedometer.

## 5. Performance e limites

### 5.1 Tempo estimado por execução

| Etapa | 10 URLs | 50 URLs |
|---|---|---|
| Coleta PSI (5 paralelas, ~20s/url) | ~40s | ~200s |
| Detecção plataforma (síncrono, <1s) | <1s | <1s |
| Analisador (3 paralelas, ~5s/url) | ~17s | ~85s |
| Documentador (mostly determinístico) | ~5s | ~15s |
| Priorizador (puro python) | <1s | <1s |
| Persistência (batch INSERT) | <2s | <5s |
| **Total** | **~1 min** | **~5 min** |

### 5.2 Caps de segurança

- `cwv_max_urls_por_execucao = 50`
- `cwv_workflow_timeout = 1200` (20 min)
- Se >50% das URLs falharem no PSI, marca execução como `parcialmente_concluida` mas persiste o que funcionou

### 5.3 Cota PSI

- Sem API key: 25.000 queries/dia, 240/min anônimas
- Com API key (recomendado em prod): mesmo limite por padrão, com possibilidade de aumento
- Adicionar contador Redis `cwv:psi:count:{YYYY-MM-DD}` pra observabilidade

## 6. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Cota PSI estourada | Contador Redis + alerta Sentry quando >80% diário; semáforo de 5 paralelas evita burst |
| Timeout PSI em URL específica | `try/except` por URL — falha individual não aborta lote |
| LLM alucina kb_codigo inexistente | Validação no Documentador: ignora códigos inválidos com log warning |
| Plataforma detectada errada | Sempre cai em "desconhecida" no pior caso, KB tem `geral` como fallback |
| URL com auth/firewall | PSI retorna erro claro, persiste com `status='falhou_psi'` e `erro_msg` visível |
| Custo LLM em escala | Analisador usa fast-path determinístico pra audits mapeados (esperado: 70% sem LLM) |
| Estado "concluida_em" sem persistencia | Marcação atômica no node `persistir` antes do END |
| Resultado_json estourar (raw PSI é grande) | raw_psi_json fica na `cwv_analise`, não em `execucao.resultado_json` (só ids) |

## 7. Plano de execução em fases

### Fase 1 — Backbone de dados (1 dia)

1. Migration Alembic com `cwv_analise` + `cwv_problema`
2. Models SQLAlchemy
3. Schemas Pydantic
4. Serviço `cwv_persistencia.py`
5. Settings (`psi_api_key`, timeouts)
6. Testes unitários de model + schema

### Fase 2 — Coleta PSI + KB inicial (1 dia)

1. `cwv_psi_client.py` com mock + testes (httpx mock)
2. `cwv_plataforma.py` com fixtures de payloads
3. Carregar KB inicial — depende de [[SPEC_CWV_Base_Conhecimento]]
4. Loader `cwv_kb.py` com cache lru
5. Smoke test: chamar PSI em URL real, parsear, persistir

### Fase 3 — Agentes + Workflow (2 dias)

1. `CWVAnalisadorAgent` (fast-path + LLM fallback)
2. `CWVDocumentadorAgent` (determinístico V1)
3. `priorizar_problemas` (rule-based)
4. `workflow.py` LangGraph com 6 nodes
5. Worker `executar_workflow_cwv`
6. Testes de integração com PSI mockado

### Fase 4 — Rota + cobrança (0.5 dia)

1. `routers/ferramentas_cwv.py` (analisar, execucao, analise, historico, reanalisar, custo)
2. `ferramenta_service.calcular_custo_cwv` + `finalizar_sucesso_cwv`
3. Registrar em `app/main.py`

### Fase 5 — Frontend formulário + polling (1 dia)

1. Página `/ferramentas/core-web-vitals/page.tsx`
2. Componente `formulario-cwv.tsx` (6 textareas + validação)
3. Página de polling reusando padrão de `gerar-artigo`
4. Item na sidebar
5. Cliente API em `lib/api.ts`

### Fase 6 — Frontend dashboard (2 dias)

Ver [[SPEC_CWV_Dashboard_Historico]] — fase própria.

### Fase 7 — E2E + ajustes (1 dia)

1. Restart backend + worker
2. Build frontend, copiar pra `backend/static`
3. Teste real: cliente + 3 URLs (1 home, 1 produto, 1 blog)
4. Validar: PSI rodou, problemas identificados, accordion renderiza, re-análise funciona, chart aparece após 2ª execução

**Esforço total estimado: ~8 dias de implementação** (sem contar manutenção contínua da KB).

## 8. Não-objetivos (V1)

- Execução agendada/recorrente (cron de re-análise automática) — V2
- Crawl automático do site a partir do sitemap — V2
- Análise de URLs autenticadas/atrás de login — V2
- Integração direta com CMS para aplicar correções (ex: trocar imagem via API VTEX) — V3
- Alertas por email quando score cair abaixo de threshold — V2
- Comparativo entre clientes (benchmark) — V2
- Field data CrUX além do lab data — V2 (Lighthouse traz quando disponível)

## 9. Critério de pronto (V1)

- Migration aplicada, tabelas `cwv_analise` e `cwv_problema` existem em prod
- POST `/api/ferramentas/cwv/analisar` aceita request válido, cria execução, enfileira
- Worker processa: logs mostram cada etapa
- Para URL real: PSI roda, plataforma detectada, problemas identificados, documentação gerada, persistência completa
- GET `/historico` lista análises agrupadas por URL
- GET `/analise/{id}` retorna análise com problemas ordenados por prioridade
- POST `/reanalisar/{id}` cria nova execução com mesmos params
- Frontend: formulário valida e submete; polling mostra etapas; histórico lista URLs; dashboard por URL renderiza chart + accordion
- Cobrança: créditos cobrados conforme `n_urls_analisadas` (URLs com falha PSI não cobram)
- Teste E2E: 3 URLs reais, 2+ problemas identificados em pelo menos 1 URL, documentação em markdown legível
