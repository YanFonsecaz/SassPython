# SPEC #17 — Paridade total com PageSpeed Insights (1 audit = 1 problema)

**Status:** a aplicar · **Escopo:** backend (analisador + documentador + workflow + persistência + migration) + frontend (plano de ação)
**Dependências:** [[SPEC_CWV_Analisador_Tools_Pesquisa]] (#13) e [[SPEC_CWV_KB_Expansao_Gaps]] (#12) — aproveita pesquisador e KB existentes.
**Esforço estimado:** ~1,5 dia (backend ~1 dia + frontend ~0,5 dia)
**Prioridade:** **alta** — gap de paridade reportado pelo usuário em E2E de 2026-05-27 (PSI mostra 17 problemas, nossa UI mostra 7).

## 1. Contexto e problema

### 1.1 Sintoma observado

E2E em `https://www.olx.com.br/` (análise `cc21c1dc-...`):

| Origem | Problemas mostrados |
|---|---|
| PSI direto (`https://pagespeed.web.dev/`) | **17** (9 em "INSIGHTS" + 8 em "DIAGNÓSTICO") |
| Nossa ferramenta | **7** (5 da KB + 1 "outros" agregando 7 audits + 1 mapeado pelo LLM) |

Usuário não consegue agir sobre os 10 problemas que somem entre o PSI e a UI.

### 1.2 Causa-raiz (3 perdas no pipeline)

| # | Onde | Lógica atual | Efeito |
|---|---|---|---|
| **1. Filtro agressivo** | `services/cwv_kb.py:53` (`AUDITS_IGNORADOS` com 17 itens) e `analisador.py:42` | Filtra audits classificados como "métricas/scores" antes do mapeamento | Remove items que aparecem no PSI (ex.: `largest-contentful-paint` aparece como "Detalhamento da LCP" na UI do PSI) |
| **2. Consolidação em 'outros'** | `analisador.py:90-103` + `_dedup_e_consolidar:273-292` | LLM mapeia audits residuais para `kb_codigo`; os que não cabem viram 1 problema único `outros` (todos os audits agregados em `audits_origem`) | 7 audits da PSI Insights API viraram **1** problema "outros" na UI |
| **3. Drift de IDs PSI vs KB** | KB mapeia audits clássicos (`uses-long-cache-ttl`, `render-blocking-resources`, `legacy-javascript`, `modern-image-formats`); PSI agora retorna `*-insight` (`cache-insight`, `render-blocking-insight`, `legacy-javascript-insight`, `image-delivery-insight`) | `mapeamento_audit_kb()` não casa → fallback LLM → 'outros' | Audits com KB pronta na verdade nunca atingem o fast-path |

Diagnóstico do raw_psi_json (47 audits no payload, 18 falhos):

```
em_KB  audit_id                          score  titulo PSI
─────  ────────────────────────────────  ─────  ──────────────────────
  ✓    bootup-time                       0.00   Reduce JavaScript execution time
  ✓    mainthread-work-breakdown         0.00   Minimize main-thread work
  ✓    total-byte-weight                 0.50   Avoid enormous network payloads
  ✓    unminified-javascript             0.50   Minify JavaScript
  ✓    unused-css-rules                  0.00   Reduce unused CSS
  ✓    unused-javascript                 0.50   Reduce unused JavaScript
  ✗    cache-insight                     0.00   Use efficient cache lifetimes        ← drift
  ✗    forced-reflow-insight             0.00   Forced reflow                        ← drift / novo
  ✗    image-delivery-insight            0.00   Improve image delivery               ← drift
  ✗    legacy-javascript-insight         0.50   Legacy JavaScript                    ← drift
  ✗    max-potential-fid                 0.00   Max Potential First Input Delay
  ✗    network-dependency-tree-insight   0.00   Network dependency tree              ← novo
  ✗    render-blocking-insight           0.00   Render-blocking requests             ← drift
 IGN   first-contentful-paint            0.85   First Contentful Paint
 IGN   interactive                       0.00   Time to Interactive                  ← PSI mostra
 IGN   largest-contentful-paint          0.69   Largest Contentful Paint             ← PSI mostra
 IGN   speed-index                       0.35   Speed Index
 IGN   total-blocking-time               0.00   Total Blocking Time                  ← PSI mostra
```

## 2. Solução: 1 audit falho = 1 problema na UI

Mudar o paradigma: a partir do PSI, cada audit falho gera **um** problema no plano de ação. A KB deixa de ser a fonte **única** da existência do problema e passa a ser **enriquecimento opcional** (quando há doc curada).

### 2.1 Cascata de documentação por problema

```
audit falho do PSI (score < 0.9, scoreDisplayMode em {numeric, binary, metric})
  │
  ├─ KB tem este audit_id em `audits_lighthouse`?
  │      └─ SIM → kb_codigo=<x> · doc curada (KB)                        [caminho atual, expandido com aliases]
  │
  ├─ KB tem alias clássico (ex: cache-insight → cache-eficiente)?
  │      └─ SIM → kb_codigo=<x> · doc curada (KB)                        [novo — via tabela de aliases]
  │
  ├─ NÃO TEM KB:
  │      ├─ análise ainda tem orçamento de pesquisa? (cap configurável)
  │      │      └─ SIM → pesquisador (SerpAPI + fetch + context7)         [SPEC #13, ampliado]
  │      │                → doc gerada · pesquisado=true · kb_codigo=null
  │      └─ NÃO → skeleton: title + description + savings_ms vindos do Lighthouse
  │                → doc mínima · pesquisado=false · kb_codigo=null
  │
  └─ (consolidação em 'outros' é REMOVIDA)
```

Resultado: a UI mostra todos os audits falhos do PSI, com doc de qualidade variável mas **nada some**.

### 2.2 Mudanças no modelo de dados

Coluna `cwv_problema.kb_codigo` precisa virar **nullable** (hoje é `String(80) NOT NULL`). Migration nova:

```python
# backend/migrations/versions/0018_cwv_problema_kb_codigo_nullable.py
def upgrade() -> None:
    op.alter_column("cwv_problema", "kb_codigo", nullable=True)

def downgrade() -> None:
    op.execute("UPDATE cwv_problema SET kb_codigo='outros' WHERE kb_codigo IS NULL")
    op.alter_column("cwv_problema", "kb_codigo", nullable=False)
```

E ajustar `models/cwv_problema.py`:

```python
kb_codigo: Mapped[str | None] = mapped_column(String(80), nullable=True)
```

Adicionar campo opcional `audit_id` para rastrear de qual audit Lighthouse o problema veio (hoje vive em `contexto_especifico['audit_id']` quando é 'outros', mas vira pesquisa cara):

```python
audit_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
```

Indexado para auditoria/observabilidade:

```python
__table_args__ = (
    CheckConstraint("severidade BETWEEN 1 AND 5", name="cwv_problema_severidade_check"),
    Index("ix_cwv_problema_analise", "analise_id", "prioridade_ordem"),
    Index("ix_cwv_problema_audit_id", "audit_id"),
)
```

### 2.3 Tabela de aliases `*-insight` ↔ clássico

Nova função em `services/cwv_kb.py`, aplicada antes do `mapeamento_audit_kb()`:

```python
AUDIT_ALIASES: dict[str, str] = {
    # PSI Insights API → audit clássico equivalente
    "cache-insight": "uses-long-cache-ttl",
    "render-blocking-insight": "render-blocking-resources",
    "legacy-javascript-insight": "legacy-javascript",
    "image-delivery-insight": "modern-image-formats",
    "third-parties-insight": "third-party-summary",
    "dom-size-insight": "dom-size",
    "lcp-discovery-insight": "prioritize-lcp-image",
    "viewport-insight": "viewport",
    "font-display-insight": "font-display",
    "duplicated-javascript-insight": "duplicated-javascript",
    # max-potential-fid: proxy de INP, mapear para o handler pesado
    "max-potential-fid": "total-blocking-time",
}


def mapeamento_audit_kb_com_aliases() -> dict[str, str]:
    """Como mapeamento_audit_kb() mas resolvendo aliases primeiro."""
    base = mapeamento_audit_kb()
    out = dict(base)
    for alias, clasico in AUDIT_ALIASES.items():
        if alias not in out and clasico in base:
            out[alias] = base[clasico]
    return out
```

Não modifica YAML — fica em código (pequeno, evolui rápido conforme Google muda IDs).

Audits sem clássico equivalente (`forced-reflow-insight`, `network-dependency-tree-insight`) ficam SEM mapeamento direto → caem na cascata "sem KB" (pesquisador ou skeleton). Pode-se criar entradas YAML específicas no futuro, mas não é bloqueante.

### 2.4 Reduzir `AUDITS_IGNORADOS` ao mínimo

Hoje o set tem 17 itens. Manter **apenas** os que são literalmente meta (não acionáveis nem mostrados em "Diagnóstico" do PSI):

```python
AUDITS_IGNORADOS = {
    # Resultado de auditoria interna, não problema
    "metrics",
    "diagnostics",
    # Screenshots e dados brutos
    "screenshot-thumbnails",
    "final-screenshot",
    "full-page-screenshot",
    # Dumps de dados Lighthouse
    "network-requests",
    "network-rtt",
    "main-thread-tasks",
    "script-treemap-data",
    "network-server-latency",
}
```

**Removidos do filtro** (passam a virar problemas):

- `interactive`, `speed-index`, `first-contentful-paint`, `largest-contentful-paint`, `cumulative-layout-shift`, `experimental-interaction-to-next-paint`, `total-blocking-time` — são métricas, mas o PSI mostra como cards de "Diagnóstico" e o usuário precisa ver os valores e ter contexto.

Para essas métricas-resumo, adicionar entradas na KB que documentem **o que é a métrica + como interpretar valores** (não "como resolver", pois resolver é função dos outros audits causais). Exemplo:

```yaml
- codigo: metrica-lcp-info
  titulo: Largest Contentful Paint
  severidade: 1
  metricas_afetadas: [LCP]
  audits_lighthouse: [largest-contentful-paint]
  descricao: |
    Tempo até o maior elemento visível ser renderizado.
  solucoes:
    geral: |
      Esta é uma métrica de resultado. Para melhorar, atue nas causas: imagens grandes,
      CSS bloqueante, TTFB alto, lazy-loading errado.
```

Severidade 1 garante que apareça no fim do plano de ação, sem competir com problemas acionáveis.

### 2.5 Refator do analisador (`agents/cwv/analisador.py`)

Mudanças cirúrgicas em `analisar()`:

```python
async def analisar(
    self, *, audits_falhos: list[dict], plataforma: str, metricas: dict
) -> tuple[list[dict], dict]:
    diretos = mapeamento_audit_kb_com_aliases()   # ← aliases
    audits_falhos = [a for a in audits_falhos if a.get("id") not in AUDITS_IGNORADOS]

    identificados: list[dict] = []
    sem_kb: list[dict] = []

    for audit in audits_falhos:
        aid = audit.get("id", "")
        if aid in diretos:
            identificados.append({
                "kb_codigo": diretos[aid],
                "audit_id": aid,
                "contexto_especifico": _extrair_contexto(audit),
                "audits_origem": [aid],
            })
        else:
            sem_kb.append(audit)

    stats = {"llm_usado": False, "processados": 0, "descartados": 0, "sem_kb": len(sem_kb)}

    # LLM ainda tenta mapear residuais — mas se MAPEAR vira KB; se NÃO mapear, fica como sem_kb (não vira 'outros' agregado)
    if sem_kb:
        kb_descritos = listar_kb_codigos_descritos()
        kb_codigos_validos = {c["codigo"] for c in kb_descritos}
        stats["llm_usado"] = True
        stats["processados"] = len(sem_kb)
        try:
            prompt = _montar_prompt_analise(sem_kb, kb_descritos, plataforma, metricas)
            resp: ListaProblemas = await self.invoke_structured(prompt, ListaProblemas)
            validos = [p for p in resp.problemas if p.kb_codigo in kb_codigos_validos]
            stats["descartados"] += len(resp.problemas) - len(validos)
            cobertos = set()
            for p in validos:
                cobertos.update(p.audits_origem)
                # IMPORTANTE: um problema do LLM = um audit (sem dedup global)
                for aid in p.audits_origem:
                    audit_obj = next((a for a in sem_kb if a.get("id") == aid), {})
                    identificados.append({
                        "kb_codigo": p.kb_codigo,
                        "audit_id": aid,
                        "contexto_especifico": {
                            **p.contexto_especifico,
                            **_extrair_contexto(audit_obj),
                        },
                        "audits_origem": [aid],
                    })
            # Audits que o LLM não cobriu → vão como kb_codigo=null
            for a in sem_kb:
                aid = a.get("id", "")
                if aid not in cobertos:
                    _emit_kb_miss(a)
                    identificados.append({
                        "kb_codigo": None,
                        "audit_id": aid,
                        "contexto_especifico": _extrair_contexto(a),
                        "audits_origem": [aid],
                    })
        except Exception as e:
            logger.warning("CWV analisador LLM fallback falhou: %s", e)
            for a in sem_kb:
                identificados.append({
                    "kb_codigo": None,
                    "audit_id": a.get("id", ""),
                    "contexto_especifico": _extrair_contexto(a),
                    "audits_origem": [a.get("id", "")],
                })

    return identificados, stats
```

**Remover:**

- `MAX_AUDITS_RESIDUAIS_LLM = 15` — não há mais corte; todos viram problemas.
- `_dedup_e_consolidar(...)` — não consolida mais. Cada audit vira 1 problema próprio (a UI lida com múltiplos sob mesmo kb_codigo sem precisar mesclar).
- Lógica `if "outros" in kb_codigos_validos` — não usa mais; `outros` pode até ser removido do YAML (deixar opcional).

### 2.6 Documentador com fallback "skeleton"

Em `agents/cwv/documentador.py`:

```python
class CWVDocumentadorAgent:
    async def documentar(self, *, problemas: list[dict], plataforma: str) -> list[dict]:
        documentados = []
        for p in problemas:
            kb_codigo = p.get("kb_codigo")
            entrada_kb = buscar_entrada(kb_codigo) if kb_codigo else None

            if entrada_kb:
                doc_md = self._gerar_doc(entrada_kb, plataforma, p.get("contexto_especifico", {}))
                titulo = entrada_kb["titulo"]
                severidade = entrada_kb["severidade"]
                metricas = entrada_kb["metricas_afetadas"]
            else:
                ctx = p.get("contexto_especifico", {})
                titulo = ctx.get("title") or p.get("audit_id", "Problema sem nome")
                severidade = _severidade_por_savings(ctx)
                metricas = _metricas_por_audit(p.get("audit_id"))
                doc_md = self._gerar_doc_skeleton(p)

            documentados.append({
                "kb_codigo": kb_codigo,             # pode ser None
                "audit_id": p.get("audit_id"),
                "titulo": titulo,
                "severidade": severidade,
                "metricas_afetadas": metricas,
                "contexto_especifico": p.get("contexto_especifico", {}),
                "documentacao_md": doc_md,
            })
        return documentados

    @staticmethod
    def _gerar_doc_skeleton(p: dict) -> str:
        ctx = p.get("contexto_especifico", {})
        partes = [
            "## Problema",
            "",
            ctx.get("description") or "Audit retornado pelo Lighthouse sem documentação curada.",
            "",
        ]
        dv = ctx.get("display_value")
        if dv:
            partes.append(f"**Valor medido:** {dv}")
        sms = ctx.get("savings_ms")
        sby = ctx.get("savings_bytes")
        if sms:
            partes.append(f"**Ganho potencial:** {sms / 1000:.1f}s")
        elif sby:
            partes.append(f"**Ganho potencial:** {sby / 1024:.1f} KB")
        items = ctx.get("items") or []
        if items:
            partes.append("")
            partes.append("**Elementos afetados:**")
            for it in items[:3]:
                token = it.get("url") or it.get("selector") or it.get("label")
                if token:
                    partes.append(f"- `{token}`")
        partes.extend([
            "",
            "## Solucao",
            "",
            "Documentacao acionavel ainda nao disponivel para este audit. "
            "Veja a [pagina oficial do Lighthouse](https://developer.chrome.com/docs/lighthouse/performance/) "
            "ou ative o pesquisador para gerar uma solucao automatica.",
        ])
        return "\n".join(partes)


def _severidade_por_savings(ctx: dict) -> int:
    """Heuristica para problemas sem KB."""
    sms = ctx.get("savings_ms") or 0
    sby = ctx.get("savings_bytes") or 0
    if sms >= 1000 or sby >= 200_000:
        return 5
    if sms >= 500 or sby >= 100_000:
        return 4
    if sms >= 200 or sby >= 50_000:
        return 3
    if sms >= 100 or sby >= 20_000:
        return 2
    return 1


def _metricas_por_audit(audit_id: str | None) -> list[str]:
    """Heuristica grosseira por substring no audit_id."""
    if not audit_id:
        return []
    out = []
    if any(k in audit_id for k in ("lcp", "lighthouse", "image", "render-blocking", "ttfb")):
        out.append("LCP")
    if "cls" in audit_id or "layout" in audit_id:
        out.append("CLS")
    if any(k in audit_id for k in ("inp", "fid", "interactive", "bootup", "javascript", "main-thread", "long")):
        out.append("INP")
        out.append("TBT")
    if "fcp" in audit_id:
        out.append("FCP")
    return out or ["LCP"]
```

### 2.7 Pesquisador rodando para todos sem KB (não só 'outros')

Em `agents/cwv/workflow.py:node_pesquisar_outros`:

```python
async def node_pesquisar_outros(estado: EstadoCWV) -> dict[str, Any]:
    from app.agents.cwv.pesquisador import CWVPesquisadorAgent

    cap = settings.cwv_pesquisador_max_por_analise  # novo campo (default 5)
    eid = estado["execucao_id"]
    novo: dict[str, list[dict]] = {}

    for url, problemas in estado["problemas_por_url"].items():
        # AGORA: prioriza por savings_ms/savings_bytes, não só kb_codigo=='outros'
        sem_kb = [p for p in problemas if p.get("kb_codigo") is None]
        sem_kb.sort(
            key=lambda p: -(
                (p.get("contexto_especifico", {}).get("savings_ms") or 0)
                + (p.get("contexto_especifico", {}).get("savings_bytes") or 0) / 1000
            ),
        )
        para_pesquisar = sem_kb[:cap]
        if not para_pesquisar:
            novo[url] = problemas
            continue

        plataforma = estado["plataformas"].get(url, "outros")
        pesquisador = CWVPesquisadorAgent(usuario_id=estado["usuario_id"], plataforma=plataforma)

        for p in para_pesquisar:
            ctx = p.get("contexto_especifico", {})
            audit_dict = {
                "id": p.get("audit_id"),
                "title": ctx.get("title"),
                "description": ctx.get("description"),
                "displayValue": ctx.get("display_value"),
                "savings_ms": ctx.get("savings_ms"),
                "savings_bytes": ctx.get("savings_bytes"),
            }
            try:
                nova_doc = await pesquisador.documentar(audit=audit_dict, plataforma=plataforma)
                if nova_doc:
                    p["documentacao_md"] = nova_doc
                    p["pesquisado"] = True
            except Exception as e:
                logger.warning("Pesquisador falhou para audit %s: %s", p.get("audit_id"), e)

        novo[url] = problemas
    return {"problemas_por_url": novo}
```

Novo campo em `config.py`:

```python
cwv_pesquisador_max_por_analise: int = 5
```

E em `.env.example`:

```
# Quantos audits sem KB serao pesquisados em tempo real por análise (cap de custo)
CWV_PESQUISADOR_MAX_POR_ANALISE=5
```

### 2.8 Persistência e schemas

`services/cwv_persistencia.py`:

```python
problema = CwvProblema(
    analise_id=analise.id,
    kb_codigo=p.get("kb_codigo"),                     # pode ser None
    audit_id=p.get("audit_id"),                       # novo
    titulo=p.get("titulo", ""),
    severidade=p.get("severidade", 1),
    prioridade_ordem=p.get("prioridade_ordem", 0),
    metricas_afetadas=p.get("metricas_afetadas", []),
    contexto_especifico=p.get("contexto_especifico"),
    documentacao_md=p.get("documentacao_md", ""),
    pesquisado=bool(p.get("pesquisado", False)),
)
```

E em `_analise_to_dict`:

```python
"problemas": [
    {
        "id": str(p.id),
        "kb_codigo": p.kb_codigo,                # pode vir null
        "audit_id": p.audit_id,                  # novo
        ...
    }
    for p in problemas
],
```

Schema Pydantic `CwvProblemaResposta` em `schemas/cwv.py`:

```python
class CwvProblemaResposta(BaseModel):
    id: str
    kb_codigo: str | None = None
    audit_id: str | None = None
    titulo: str
    severidade: int
    prioridade_ordem: int
    metricas_afetadas: list[str]
    contexto_especifico: dict | None = None
    documentacao_md: str
    pesquisado: bool = False
```

### 2.9 Priorizador

`agents/cwv/priorizador.py` precisa priorizar problemas sem KB usando `savings_ms`/`savings_bytes` e severidade calculada. Ajustar a função `priorizar_problemas` para usar `severidade` (que já vem populada pelo documentador, inclusive para skeletons via `_severidade_por_savings`) como chave principal e `savings_ms` como desempate.

### 2.10 Frontend (`cwv-plano-acao.tsx` e `cwv.ts`)

Tipo:

```ts
export interface CwvProblemaResposta {
  id: string;
  kb_codigo: string | null;   // ← nullable
  audit_id: string | null;    // novo
  titulo: string;
  // ...
  pesquisado?: boolean;
}
```

Componente: adicionar badge contextual ao lado do título do problema:

- `kb_codigo` presente + `pesquisado=false` → badge "📘 Curado"
- `pesquisado=true` → badge "🔍 Pesquisado em tempo real" (já existe)
- `kb_codigo=null` e `pesquisado=false` → badge "📋 Lighthouse"

Cabeçalho do plano de ação ganha um resumo:

```
Plano de ação — 17 problemas
12 curados · 3 pesquisados · 2 do Lighthouse
```

### 2.11 Telemetria

Adicionar campos em `stats` retornado pelo analisador (já passa via `llm_stats` para `persistir_analise`):

| Campo | O que mede |
|---|---|
| `audits_total_psi` | total de audits retornados pelo PSI |
| `audits_falhos_total` | filtrados antes do mapeamento |
| `audits_ignorados` | filtrados por `AUDITS_IGNORADOS` |
| `audits_mapeados_kb` | resolvidos pelo fast-path (com aliases) |
| `audits_mapeados_llm` | resolvidos pelo LLM residual |
| `audits_sem_kb` | viram skeleton/pesquisado |

Persistir em colunas em `cwv_analise` (3 colunas novas via migration `0019` se quisermos histórico) ou retornar só na response (sem persistir). Recomendado: persistir, vira insumo do `scripts/cwv_kb_audit.py`.

## 3. Critérios de aceitação

1. **Paridade quantitativa:** análise de `https://www.olx.com.br/` mostra **≥15 problemas** no plano de ação (vs 7 hoje; vs 17 no PSI).
2. **Sem perda silenciosa:** todo audit falho no `raw_psi_json` aparece como exatamente 1 problema na UI ou está em `AUDITS_IGNORADOS` (verificável via SQL: `SELECT COUNT(*) FROM cwv_problema WHERE analise_id=X` ≈ `SELECT jsonb_array_length(audits_falhos)` da análise).
3. **Aliases funcionando:** `cache-insight` (audit do PSI) gera problema com `kb_codigo='cache-eficiente'` (doc curada da KB).
4. **Pesquisador escala:** se 5 audits forem sem KB, todos os 5 ganham `pesquisado=true` no DB (com `CWV_PESQUISADOR_MAX_POR_ANALISE=5`).
5. **Skeleton mínimo aceitável:** audit sem KB e sem pesquisador rendeu doc com título Lighthouse + savings + lista de elementos afetados.
6. **Migration `0018` aplica sem perda:** existing rows mantêm `kb_codigo` populado; novos podem ser `NULL`.
7. **Frontend mostra origem:** badges "Curado / Pesquisado / Lighthouse" visíveis no plano de ação.
8. **Sem regressão:** 96 testes unit CWV passam; novo teste cobre `mapeamento_audit_kb_com_aliases` e `_gerar_doc_skeleton`.

## 4. Arquivos afetados

**Backend (10 arquivos + 2 migrations):**
- `backend/migrations/versions/0018_cwv_problema_kb_codigo_nullable.py` (novo)
- `backend/migrations/versions/0019_cwv_problema_audit_id.py` (novo)
- `backend/app/models/cwv_problema.py` — `kb_codigo` nullable + `audit_id` opcional + índice
- `backend/app/services/cwv_kb.py` — `AUDIT_ALIASES`, `mapeamento_audit_kb_com_aliases`, reduzir `AUDITS_IGNORADOS`
- `backend/app/agents/cwv/analisador.py` — sem consolidação, sem cap, kb_codigo=None permitido
- `backend/app/agents/cwv/documentador.py` — `_gerar_doc_skeleton`, `_severidade_por_savings`, `_metricas_por_audit`
- `backend/app/agents/cwv/priorizador.py` — usar `severidade` (já calculada) + savings como desempate
- `backend/app/agents/cwv/workflow.py:node_pesquisar_outros` — sem_kb não 'outros'; cap configurável
- `backend/app/services/cwv_persistencia.py` — persiste `audit_id`, aceita `kb_codigo=None`
- `backend/app/schemas/cwv.py` — `kb_codigo: str | None`, `audit_id: str | None`
- `backend/app/config.py` — `cwv_pesquisador_max_por_analise: int = 5`
- `backend/.env.example` — documenta nova chave
- `backend/app/data/cwv_knowledge_base.yaml` — entradas opcionais para métricas-resumo (`metrica-lcp-info`, etc) para os audits removidos de `AUDITS_IGNORADOS`

**Frontend (2 arquivos):**
- `frontend/src/lib/api/cwv.ts` — `kb_codigo: string | null`, `audit_id: string | null`
- `frontend/src/components/cwv/cwv-plano-acao.tsx` — badge "Curado/Pesquisado/Lighthouse" + resumo no cabeçalho

**Testes (3+ arquivos):**
- `backend/tests/unit/test_cwv_kb.py` — `AUDIT_ALIASES`, `mapeamento_audit_kb_com_aliases`
- `backend/tests/unit/test_cwv_analisador.py` — sem consolidação, kb_codigo=None
- `backend/tests/unit/test_cwv_documentador.py` (novo se não existir) — `_gerar_doc_skeleton`, severidade por savings

## 5. Fora de escopo

- Refazer o `priorizador.py` por inteiro (só ajuste local).
- Mostrar audits **passantes** (verdes) na UI — só os falhos viram problemas.
- Internacionalização da `description` Lighthouse (vem em inglês do PSI; tradução automática seria útil mas é spec separada).
- Adicionar entradas YAML para `forced-reflow-insight` e `network-dependency-tree-insight` — esses ficam como skeleton/pesquisado nesta iteração; depois podem ganhar entrada própria.

## 6. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Cap de pesquisador (5) virar gargalo de custo se PSI passar a retornar 30 audits | Cap configurável via env; observabilidade nas `stats` permite reavaliar |
| Documentação skeleton confunde usuário ("não é solução") | Badge "📋 Lighthouse" deixa claro o nível; copy do skeleton menciona "documentação ainda não curada" |
| Audits removidos de `AUDITS_IGNORADOS` (metric scores) inflam o plano de ação | Severidade 1 nas entradas das métricas-resumo joga para o final; ordenação por severidade decrescente mantém ações reais no topo |
| Coluna `kb_codigo` virando nullable quebra queries downstream | Greppar `kb_codigo == 'outros'`, `kb_codigo ==` antes de aplicar; ajustar |
| Migration `0018` em produção lock-table | `ALTER COLUMN ... DROP NOT NULL` é instant no Postgres; sem risco |
| Frontend que depende de `kb_codigo` ser string falha em runtime | TypeScript já marcado nullable força tratamento; testar render com null |

## 7. Plano de rollout

1. **Backend** primeiro (migration 0018 + 0019 + analisador/documentador/persistência). Por trás de feature flag não é necessário — mudança é compatível com problemas pré-existentes.
2. **Frontend** depois (precisa do contrato novo do API).
3. **KB com aliases + entradas de métrica-resumo** podem ir junto ou depois — não bloqueia.
4. **Validação E2E** sobre `https://www.olx.com.br/`: contar problemas (esperado ≥15), conferir badges, conferir `pesquisado=true` em pelo menos 1 audit sem KB.
5. **Monitorar** taxa de `audits_sem_kb / audits_falhos_total` por 1 semana → input do próximo ciclo de expansão da KB.

## 8. Comparação antes × depois (exemplo: OLX)

| Métrica | Hoje (cc21c1dc) | Pós SPEC #17 (estimado) |
|---|---|---|
| Problemas mostrados | 7 | 15-18 |
| Problemas com doc curada (KB) | 6 | 9-11 (graças aos aliases) |
| Problemas pesquisados | 1 | 3-5 (cap configurável) |
| Problemas com doc skeleton | 0 | 2-4 |
| Audits perdidos silenciosamente | 7+ | 0 |
