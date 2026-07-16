# CWV Auditoria UI V2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Página da auditoria CWV com donuts de health score, checklist estilo Excel editável (implementação/notas/prioridade) e before/after por URL, servida por um endpoint comparativo novo.

**Architecture:** Backend ganha 1 endpoint agregado (`GET /auditorias/{id}/comparativo`) montado por função pura de serviço + campo `prioridade` no PATCH de item. Frontend quebra `cwv-auditoria-client.tsx` em componentes por aba sob `components/cwv/auditoria/` (header com donuts, 3 abas via shadcn Tabs sincronizadas com `?tab=`).

**Tech Stack:** FastAPI + SQLAlchemy async + Pydantic v2 (backend); Next.js 16.2.4 `output: "export"` + React + Tailwind + shadcn + recharts 3.8 + vitest/testing-library (frontend).

**Specs:** `docs/specs/ferramentas/core-web-vitals/SPEC_CWV_Auditoria_Comparativo_API.md` e `SPEC_CWV_Auditoria_UI_V2.md` — leia ambas antes de começar.

## Global Constraints

- Next.js deste repo é **16.2.4 com breaking changes** — antes de qualquer task de frontend, leia `frontend/node_modules/next/dist/docs/01-app/` sobre `useSearchParams`/`useRouter`/`usePathname`. `frontend/AGENTS.md` manda: "Read the relevant guide before writing any code."
- `output: "export"`: **nunca** `useParams()`; id da rota via `usePathname()` (padrão existente `cwv-auditoria-client.tsx:66-67`).
- Pass/Fail (`status_before`/`status_after`) é **somente leitura** na UI — vem da análise.
- `chave_problema` (`backend/app/services/cwv_auditoria_service.py:37-49`) é contrato — importar, nunca reimplementar.
- Testes backend sem rede/DB real quando possível (funções puras, padrão `test_cwv_auditoria.py`).
- Testes frontend: vitest + `@testing-library/react`, mock de `@/lib/utils` `cn` (padrão `comparador-component.test.tsx:7-10`).
- Comandos backend: `cd backend && uv run pytest ...`. Frontend: `cd frontend && pnpm test -- --run <path>`.
- Commits frequentes, mensagens `feat(cwv):`/`test(cwv):` etc., rodapé `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: `prioridade` no PATCH de item do checklist

**Files:**
- Modify: `backend/app/schemas/cwv_auditoria.py:73-76` (classe `ChecklistItemPatch`)
- Modify: `backend/app/routers/ferramentas_cwv_auditoria.py:244-250` (handler `atualizar_item_checklist`)
- Test: `backend/tests/unit/test_cwv_auditoria.py`

**Interfaces:**
- Consumes: `ChecklistItemPatch` existente (`status_implementacao`, `nota_cliente`, `nota_seo`).
- Produces: `ChecklistItemPatch.prioridade: int | None` (ge=0) — o front (Task 4) envia `{ prioridade: number }` no PATCH.

- [ ] **Step 1: Teste falhando (validação do schema)**

Adicionar ao fim de `backend/tests/unit/test_cwv_auditoria.py`:

```python
def test_checklist_item_patch_aceita_prioridade():
    from app.schemas.cwv_auditoria import ChecklistItemPatch

    corpo = ChecklistItemPatch(prioridade=3)
    assert corpo.prioridade == 3


def test_checklist_item_patch_rejeita_prioridade_negativa():
    import pydantic
    import pytest as _pytest

    from app.schemas.cwv_auditoria import ChecklistItemPatch

    with _pytest.raises(pydantic.ValidationError):
        ChecklistItemPatch(prioridade=-1)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && uv run pytest tests/unit/test_cwv_auditoria.py -q`
Expected: 2 FAIL — `ValidationError` (campo `prioridade` desconhecido? Pydantic v2 ignora extra por padrão → o primeiro teste falha com `AttributeError: prioridade`).

- [ ] **Step 3: Implementar schema + handler**

Em `backend/app/schemas/cwv_auditoria.py`, classe `ChecklistItemPatch` (linha 73) — adicionar campo (conferir que `Field` já está importado de `pydantic`; se não, adicionar ao import existente):

```python
class ChecklistItemPatch(BaseModel):
    status_implementacao: StatusImplementacao | None = None
    nota_cliente: str | None = None
    nota_seo: str | None = None
    prioridade: int | None = Field(default=None, ge=0)
```

Em `backend/app/routers/ferramentas_cwv_auditoria.py`, handler `atualizar_item_checklist`, junto dos outros ifs (após linha 249 `item.nota_seo = corpo.nota_seo`):

```python
    if corpo.prioridade is not None:
        item.prioridade = corpo.prioridade
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && uv run pytest tests/unit/test_cwv_auditoria.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/schemas/cwv_auditoria.py backend/app/routers/ferramentas_cwv_auditoria.py backend/tests/unit/test_cwv_auditoria.py
rtk git commit -m "feat(cwv): prioridade editavel no PATCH de item do checklist

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: função pura `montar_comparativo` no service

**Files:**
- Modify: `backend/app/services/cwv_auditoria_service.py` (nova função no fim do arquivo)
- Test: `backend/tests/unit/test_cwv_auditoria.py`

**Interfaces:**
- Consumes: `chave_problema` (mesmo módulo, linha 37).
- Produces: `montar_comparativo(analises_before: list[dict], analises_after: list[dict] | None) -> list[dict]`. Cada análise-dict tem `id`, `url_canonica`, `estrategia`, `template_tipo`, `status`, `score_performance`, `lcp_ms`, `cls`, `inp_ms`, `tbt_ms`, `problemas` (lista de dicts com `kb_codigo`/`audit_id`/`titulo`) — é o shape de `cwv_persistencia.buscar_analises_da_execucao` (`cwv_persistencia.py:136-150`). Retorno: lista de pares (shape do JSON da spec §3.1).

- [ ] **Step 1: Testes falhando**

Adicionar ao `backend/tests/unit/test_cwv_auditoria.py`:

```python
def _analise(url, estrategia, score, problemas, status="sucesso", template="home"):
    return {
        "id": f"{url}-{estrategia}",
        "url_canonica": url,
        "estrategia": estrategia,
        "template_tipo": template,
        "status": status,
        "score_performance": score,
        "lcp_ms": 4200.0,
        "cls": 0.57,
        "inp_ms": 348.0,
        "tbt_ms": 890.0,
        "problemas": problemas,
    }


def _prob(kb):
    return {"kb_codigo": kb, "audit_id": None, "titulo": kb}


def test_montar_comparativo_pareia_e_conta_diff():
    from app.services.cwv_auditoria_service import montar_comparativo

    before = [_analise("https://a.com/", "mobile", 23, [_prob("k1"), _prob("k2"), _prob("k3")])]
    after = [_analise("https://a.com/", "mobile", 61, [_prob("k2"), _prob("k9")])]

    pares = montar_comparativo(before, after)
    assert len(pares) == 1
    par = pares[0]
    assert par["url_canonica"] == "https://a.com/"
    assert par["estrategia"] == "mobile"
    assert par["before"]["score_performance"] == 23
    assert par["after"]["score_performance"] == 61
    assert par["problemas"]["resolvidos"] == 2      # k1, k3
    assert par["problemas"]["persistentes"] == 1    # k2
    assert par["problemas"]["novos"] == 1           # k9
    assert "k1" in par["problemas"]["titulos_resolvidos"]
    assert par["problemas"]["titulos_novos"] == ["k9"]


def test_montar_comparativo_sem_after_retorna_baseline():
    from app.services.cwv_auditoria_service import montar_comparativo

    before = [_analise("https://a.com/", "mobile", 23, [_prob("k1")])]
    pares = montar_comparativo(before, None)
    assert pares[0]["after"] is None
    assert pares[0]["problemas"] is None


def test_montar_comparativo_after_faltando_para_url():
    from app.services.cwv_auditoria_service import montar_comparativo

    before = [
        _analise("https://a.com/", "mobile", 23, []),
        _analise("https://a.com/b", "mobile", 50, []),
    ]
    after = [_analise("https://a.com/", "mobile", 61, [])]
    pares = montar_comparativo(before, after)
    assert len(pares) == 2
    sem_after = [p for p in pares if p["url_canonica"] == "https://a.com/b"][0]
    assert sem_after["after"] is None


def test_montar_comparativo_ignora_analises_sem_sucesso():
    from app.services.cwv_auditoria_service import montar_comparativo

    before = [_analise("https://a.com/", "mobile", 23, [])]
    after = [_analise("https://a.com/", "mobile", None, [], status="falhou")]
    pares = montar_comparativo(before, after)
    assert pares[0]["after"] is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && uv run pytest tests/unit/test_cwv_auditoria.py -q`
Expected: FAIL — `ImportError: cannot import name 'montar_comparativo'`.

- [ ] **Step 3: Implementar**

No fim de `backend/app/services/cwv_auditoria_service.py`:

```python
_CAP_TITULOS = 20


def _metricas_analise(a: dict) -> dict:
    return {
        "analise_id": str(a.get("id", "")),
        "score_performance": a.get("score_performance"),
        "lcp_ms": a.get("lcp_ms"),
        "cls": a.get("cls"),
        "inp_ms": a.get("inp_ms"),
        "tbt_ms": a.get("tbt_ms"),
        "n_problemas": len(a.get("problemas") or []),
    }


def montar_comparativo(
    analises_before: list[dict], analises_after: list[dict] | None
) -> list[dict]:
    """SPEC_CWV_Auditoria_Comparativo_API: pares URL×estratégia before/after.

    Função pura — recebe dicts de ``buscar_analises_da_execucao``. Diff de
    problemas pela mesma ``chave_problema`` do checklist/S5.
    """
    ok_before = [a for a in analises_before if a.get("status") == "sucesso"]
    ok_after = [a for a in (analises_after or []) if a.get("status") == "sucesso"]
    idx_after = {(a["url_canonica"], a["estrategia"]): a for a in ok_after}

    pares: list[dict] = []
    for a in ok_before:
        b = idx_after.get((a["url_canonica"], a["estrategia"]))
        problemas = None
        if b is not None:
            chaves_b = {chave_problema(p): p for p in (a.get("problemas") or [])}
            chaves_a = {chave_problema(p): p for p in (b.get("problemas") or [])}
            resolvidas = sorted(set(chaves_b) - set(chaves_a))
            novas = sorted(set(chaves_a) - set(chaves_b))
            persistentes = set(chaves_b) & set(chaves_a)
            problemas = {
                "resolvidos": len(resolvidas),
                "persistentes": len(persistentes),
                "novos": len(novas),
                "titulos_resolvidos": [chaves_b[c].get("titulo") or c for c in resolvidas[:_CAP_TITULOS]],
                "titulos_novos": [chaves_a[c].get("titulo") or c for c in novas[:_CAP_TITULOS]],
            }
        pares.append({
            "url_canonica": a["url_canonica"],
            "estrategia": a["estrategia"],
            "template_tipo": a.get("template_tipo", ""),
            "before": _metricas_analise(a),
            "after": _metricas_analise(b) if b is not None else None,
            "problemas": problemas,
        })

    pares.sort(key=lambda p: (p["template_tipo"], p["url_canonica"], p["estrategia"]))
    return pares
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && uv run pytest tests/unit/test_cwv_auditoria.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/cwv_auditoria_service.py backend/tests/unit/test_cwv_auditoria.py
rtk git commit -m "feat(cwv): montar_comparativo — pares URL x estrategia before/after

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: endpoint `GET /auditorias/{id}/comparativo`

**Files:**
- Modify: `backend/app/schemas/cwv_auditoria.py` (3 schemas novos no fim)
- Modify: `backend/app/routers/ferramentas_cwv_auditoria.py` (endpoint novo, após o GET de auditoria da linha 162)
- Test: `backend/tests/unit/test_cwv_auditoria.py` (schema round-trip)

**Interfaces:**
- Consumes: `montar_comparativo` (Task 2), `cwv_persistencia.buscar_analises_da_execucao(session, execucao_id)`.
- Produces: rota `GET /api/ferramentas/core-web-vitals/auditorias/{auditoria_id}/comparativo` → `{"fase": str, "pares": [...]}` — consumida pelo front (Task 4).

- [ ] **Step 1: Teste falhando (schemas validam o shape do service)**

```python
def test_comparativo_resposta_valida_shape_do_service():
    from app.schemas.cwv_auditoria import ComparativoResposta
    from app.services.cwv_auditoria_service import montar_comparativo

    before = [_analise("https://a.com/", "mobile", 23, [_prob("k1")])]
    after = [_analise("https://a.com/", "mobile", 61, [])]
    resp = ComparativoResposta(fase="after", pares=montar_comparativo(before, after))
    assert resp.pares[0].problemas.resolvidos == 1
    assert resp.pares[0].after.score_performance == 61
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && uv run pytest tests/unit/test_cwv_auditoria.py::test_comparativo_resposta_valida_shape_do_service -q`
Expected: FAIL — `ImportError: ComparativoResposta`.

- [ ] **Step 3: Schemas + endpoint**

No fim de `backend/app/schemas/cwv_auditoria.py`:

```python
class ComparativoMetricas(BaseModel):
    analise_id: str
    score_performance: int | None = None
    lcp_ms: float | None = None
    cls: float | None = None
    inp_ms: float | None = None
    tbt_ms: float | None = None
    n_problemas: int = 0


class ComparativoProblemas(BaseModel):
    resolvidos: int
    persistentes: int
    novos: int
    titulos_resolvidos: list[str] = []
    titulos_novos: list[str] = []


class ComparativoPar(BaseModel):
    url_canonica: str
    estrategia: str
    template_tipo: str = ""
    before: ComparativoMetricas
    after: ComparativoMetricas | None = None
    problemas: ComparativoProblemas | None = None


class ComparativoResposta(BaseModel):
    fase: FaseAuditoria
    pares: list[ComparativoPar]
```

Em `backend/app/routers/ferramentas_cwv_auditoria.py`, logo após o endpoint `GET /auditorias/{auditoria_id}` (linha ~175). Imports: adicionar `ComparativoResposta` ao import de schemas do topo do arquivo e `montar_comparativo` ao import de `cwv_auditoria_service`; `buscar_analises_da_execucao` importar de `app.services.cwv_persistencia`:

```python
@router.get(
    "/core-web-vitals/auditorias/{auditoria_id}/comparativo",
    response_model=ComparativoResposta,
)
async def comparativo_auditoria(
    auditoria_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    aud_result = await db.execute(
        select(CwvAuditoria).where(CwvAuditoria.id == auditoria_id)
    )
    auditoria = aud_result.scalar_one_or_none()
    if not auditoria or str(auditoria.usuario_id) != str(usuario.id):
        raise HTTPException(status_code=404, detail="Auditoria nao encontrada")

    from app.services.cwv_persistencia import buscar_analises_da_execucao

    analises_before = await buscar_analises_da_execucao(db, str(auditoria.execucao_before_id))
    analises_after = None
    if auditoria.execucao_after_id:
        analises_after = await buscar_analises_da_execucao(db, str(auditoria.execucao_after_id))

    return {"fase": auditoria.fase, "pares": montar_comparativo(analises_before, analises_after)}
```

- [ ] **Step 4: Rodar suíte CWV inteira**

Run: `cd backend && uv run pytest tests/unit/test_cwv_auditoria.py tests/unit/test_workflow_syntaxerror.py -q`
Expected: PASS (o segundo garante que o app importa com o router alterado).

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/schemas/cwv_auditoria.py backend/app/routers/ferramentas_cwv_auditoria.py backend/tests/unit/test_cwv_auditoria.py
rtk git commit -m "feat(cwv): endpoint GET /auditorias/{id}/comparativo

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: API client do front — tipos + `buscarComparativoAuditoria` + `prioridade`

**Files:**
- Modify: `frontend/src/lib/api/cwv.ts` (tipos após `AuditoriaResumo` linha 286; função junto das de auditoria linha ~300)

**Interfaces:**
- Consumes: endpoint da Task 3.
- Produces (usado nas Tasks 7-8):

```ts
export interface ComparativoMetricas { analise_id: string; score_performance: number | null; lcp_ms: number | null; cls: number | null; inp_ms: number | null; tbt_ms: number | null; n_problemas: number; }
export interface ComparativoProblemas { resolvidos: number; persistentes: number; novos: number; titulos_resolvidos: string[]; titulos_novos: string[]; }
export interface ComparativoPar { url_canonica: string; estrategia: string; template_tipo: string; before: ComparativoMetricas; after: ComparativoMetricas | null; problemas: ComparativoProblemas | null; }
export interface ComparativoResposta { fase: FaseAuditoria; pares: ComparativoPar[]; }
export async function buscarComparativoAuditoria(auditoriaId: string): Promise<ComparativoResposta>
```

- [ ] **Step 1: Implementar (sem teste próprio — tipos + fetch fino; cobertos nos testes dos componentes)**

Adicionar os 4 tipos acima após `AuditoriaResumo` (linha 286). Função junto de `buscarAuditoriaCwv` (linha ~300), seguindo o padrão de fetch do arquivo (copiar o estilo de `buscarAuditoriaCwv` — mesmo helper HTTP usado nas funções vizinhas):

```ts
export async function buscarComparativoAuditoria(auditoriaId: string): Promise<ComparativoResposta> {
  return apiFetch(`/api/ferramentas/core-web-vitals/auditorias/${auditoriaId}/comparativo`);
}
```

> Conferir o nome real do helper HTTP no arquivo (as funções vizinhas mostram — usar o mesmo, não inventar).

No tipo do payload de `atualizarItemChecklistCwv` (linha ~308), adicionar `prioridade?: number` ao objeto `dados`.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit 2>&1 | head -20` (via `rtk tsc` se disponível)
Expected: sem erros novos.

- [ ] **Step 3: Commit**

```bash
rtk git add frontend/src/lib/api/cwv.ts
rtk git commit -m "feat(cwv): client do comparativo + prioridade no PATCH de item

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: componente `health-donut.tsx`

**Files:**
- Create: `frontend/src/components/cwv/auditoria/health-donut.tsx`
- Test: `frontend/src/components/cwv/__tests__/health-donut.test.tsx`

**Interfaces:**
- Produces: `<HealthDonut pass={85} fail={91} label="Before" size={140} />` e variante vazia `<HealthDonut pass={null} fail={null} label="After" hint="aguardando re-auditoria" />`. Usado por Tasks 9 e 10.

- [ ] **Step 1: Teste falhando**

`frontend/src/components/cwv/__tests__/health-donut.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

import { HealthDonut } from "@/components/cwv/auditoria/health-donut";

describe("HealthDonut", () => {
  it("mostra % central e contadores", () => {
    render(<HealthDonut pass={85} fail={91} label="Before" />);
    expect(screen.getByText("48%")).toBeInTheDocument(); // 85/176 = 48.3 → round 48
    expect(screen.getByText(/85/)).toBeInTheDocument();
    expect(screen.getByText(/91/)).toBeInTheDocument();
    expect(screen.getByText("Before")).toBeInTheDocument();
  });

  it("estado vazio com hint", () => {
    render(<HealthDonut pass={null} fail={null} label="After" hint="aguardando re-auditoria" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("aguardando re-auditoria")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/health-donut.test.tsx`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar**

`frontend/src/components/cwv/auditoria/health-donut.tsx` — donut SVG puro (mesmo precedente do
sparkline custom de `cwv-evolucao-chart.tsx:105`; determinístico em jsdom, sem
ResponsiveContainer):

```tsx
"use client";

// Donut de health score (SPEC_CWV_Auditoria_UI_V2 §3.1): SVG puro, % central.
// Verde = pass, vermelho = fail — mesmas cores dos badges do checklist.

interface HealthDonutProps {
  pass: number | null;
  fail: number | null;
  label: string;
  hint?: string;
  size?: number;
}

export function HealthDonut({ pass, fail, label, hint, size = 140 }: HealthDonutProps) {
  const total = (pass ?? 0) + (fail ?? 0);
  const vazio = pass === null || fail === null || total === 0;
  const pct = vazio ? 0 : Math.round((pass! / total) * 100);

  const stroke = size * 0.11;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const passLen = (pct / 100) * c;

  return (
    <div className="flex flex-col items-center gap-1" data-testid={`donut-${label.toLowerCase()}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${vazio ? "sem dados" : `${pct}% aprovado`}`}>
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          className={vazio ? "stroke-muted" : "stroke-destructive/70"}
          strokeWidth={stroke}
        />
        {!vazio && (
          <circle
            cx={size / 2} cy={size / 2} r={r} fill="none"
            className="stroke-success"
            strokeWidth={stroke}
            strokeDasharray={`${passLen} ${c - passLen}`}
            strokeDashoffset={c / 4}
            strokeLinecap="round"
          />
        )}
        <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" className="fill-foreground font-bold" fontSize={size * 0.2}>
          {vazio ? "—" : `${pct}%`}
        </text>
      </svg>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      {vazio ? (
        hint && <p className="text-[11px] text-muted-foreground">{hint}</p>
      ) : (
        <p className="text-[11px] text-muted-foreground">
          <span className="text-success">✔ {pass}</span> · <span className="text-destructive">✖ {fail}</span>
        </p>
      )}
    </div>
  );
}
```

> Nota de desvio da spec: spec citava recharts `PieChart`; SVG puro entrega o mesmo visual com
> teste determinístico e segue o precedente do sparkline custom do próprio módulo CWV. Registrar
> no Histórico da spec ao final (Task 11).

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/health-donut.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/components/cwv/auditoria/health-donut.tsx frontend/src/components/cwv/__tests__/health-donut.test.tsx
rtk git commit -m "feat(cwv): componente HealthDonut (donut SVG pass/fail)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: componente `health-evolucao-chart.tsx`

**Files:**
- Create: `frontend/src/components/cwv/auditoria/health-evolucao-chart.tsx`
- Test: `frontend/src/components/cwv/__tests__/health-evolucao-chart.test.tsx`

**Interfaces:**
- Consumes: `AuditoriaResumo[]` (de `listarAuditoriasCwv`, tipo em `lib/api/cwv.ts:278-286`).
- Produces: `<HealthEvolucaoChart auditorias={resumos} auditoriaAtualId={id} />`. Usado pela Task 9.

- [ ] **Step 1: Teste falhando**

```tsx
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

import { HealthEvolucaoChart } from "@/components/cwv/auditoria/health-evolucao-chart";
import type { AuditoriaResumo } from "@/lib/api/cwv";

const aud = (id: string, before: number | null, after: number | null, criado: string): AuditoriaResumo => ({
  id, titulo: `Auditoria ${id}`, fase: "concluida",
  health_score_before: before, health_score_after: after,
  n_itens: 40, criado_em: criado,
});

describe("HealthEvolucaoChart", () => {
  it("plota um ponto por auditoria com health", () => {
    render(
      <HealthEvolucaoChart
        auditorias={[aud("a", 48.3, 72.0, "2026-05-01T00:00:00Z"), aud("b", 70.0, null, "2026-07-01T00:00:00Z")]}
        auditoriaAtualId="b"
      />
    );
    // Ponto usa after quando existe, senão before.
    expect(screen.getByTestId("evolucao-pontos").textContent).toContain("72");
    expect(screen.getByTestId("evolucao-pontos").textContent).toContain("70");
  });

  it("com < 2 pontos mostra empty state", () => {
    render(<HealthEvolucaoChart auditorias={[aud("a", 48.3, null, "2026-07-01T00:00:00Z")]} auditoriaAtualId="a" />);
    expect(screen.getByText(/primeira auditoria/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/health-evolucao-chart.test.tsx`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar**

SVG de linha simples (precedente `cwv-evolucao-chart.tsx:105` — `viewBox` fixo,
`preserveAspectRatio="none"`), pontos com rótulo de valor:

```tsx
"use client";

// Evolução do health score entre auditorias do cliente
// (SPEC_CWV_Auditoria_UI_V2 §3.1 — dados de listarAuditoriasCwv, zero backend novo).

import type { AuditoriaResumo } from "@/lib/api/cwv";

interface Props {
  auditorias: AuditoriaResumo[];
  auditoriaAtualId: string;
}

function healthDaAuditoria(a: AuditoriaResumo): number | null {
  return a.health_score_after ?? a.health_score_before;
}

export function HealthEvolucaoChart({ auditorias, auditoriaAtualId }: Props) {
  const pontos = auditorias
    .map((a) => ({ a, v: healthDaAuditoria(a) }))
    .filter((p): p is { a: AuditoriaResumo; v: number } => p.v !== null)
    .sort((p1, p2) => p1.a.criado_em.localeCompare(p2.a.criado_em));

  if (pontos.length < 2) {
    return (
      <div className="flex h-40 items-center justify-center rounded-xl border bg-surface-light">
        <p className="text-xs text-muted-foreground">
          Primeira auditoria do cliente — a evolução aparece a partir da segunda.
        </p>
      </div>
    );
  }

  const w = 320;
  const h = 140;
  const pad = 22;
  const xs = (i: number) => pad + (i * (w - 2 * pad)) / (pontos.length - 1);
  const ys = (v: number) => h - pad - (v / 100) * (h - 2 * pad);
  const path = pontos.map((p, i) => `${i === 0 ? "M" : "L"}${xs(i)},${ys(p.v)}`).join(" ");

  return (
    <div className="rounded-xl border bg-surface-light p-3">
      <p className="mb-1 text-xs font-medium text-muted-foreground">Evolução do health score</p>
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label="Evolução do health score">
        <line x1={pad} y1={ys(50)} x2={w - pad} y2={ys(50)} className="stroke-border" strokeDasharray="3 3" />
        <path d={path} fill="none" className="stroke-brand" strokeWidth={2} />
        <g data-testid="evolucao-pontos">
          {pontos.map((p, i) => (
            <g key={p.a.id}>
              <circle cx={xs(i)} cy={ys(p.v)} r={p.a.id === auditoriaAtualId ? 5 : 3.5}
                className={p.a.id === auditoriaAtualId ? "fill-brand" : "fill-brand/60"} />
              <text x={xs(i)} y={ys(p.v) - 8} textAnchor="middle" fontSize={10} className="fill-foreground">
                {p.v}
              </text>
              <text x={xs(i)} y={h - 6} textAnchor="middle" fontSize={9} className="fill-muted-foreground">
                {new Date(p.a.criado_em).toLocaleDateString("pt-BR", { month: "short", year: "2-digit" })}
              </text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/health-evolucao-chart.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/components/cwv/auditoria/health-evolucao-chart.tsx frontend/src/components/cwv/__tests__/health-evolucao-chart.test.tsx
rtk git commit -m "feat(cwv): chart de evolucao do health por auditoria

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: componente `checklist-grid.tsx` (tabela estilo Excel)

**Files:**
- Create: `frontend/src/components/cwv/auditoria/checklist-grid.tsx`
- Test: `frontend/src/components/cwv/__tests__/checklist-grid.test.tsx`

**Interfaces:**
- Consumes: `ChecklistItemResposta` (`lib/api/cwv.ts:244`), payload PATCH com `prioridade` (Task 4).
- Produces: `<ChecklistGrid checklist={itens} salvandoId={id|null} onAtualizarItem={(itemId, dados) => void} />` onde `dados: { status_implementacao?: StatusImplementacao; nota_cliente?: string; nota_seo?: string; prioridade?: number }`. Usado pela Task 10.

- [ ] **Step 1: Teste falhando**

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

import { ChecklistGrid } from "@/components/cwv/auditoria/checklist-grid";
import type { ChecklistItemResposta } from "@/lib/api/cwv";

const item = (over: Partial<ChecklistItemResposta>): ChecklistItemResposta => ({
  id: "i1", origem: "psi_audit", item_codigo: "k1", titulo: "Execução pesada",
  status_before: "fail", status_after: null, status_implementacao: "nao_executado",
  nota_cliente: null, nota_seo: null, prioridade: 1, esforco: "alto", escopo_json: { urls: [] },
  ...over,
});

describe("ChecklistGrid", () => {
  it("agrupa por origem com contadores", () => {
    render(
      <ChecklistGrid
        checklist={[item({}), item({ id: "i2", origem: "field_data", item_codigo: "crux_lcp", titulo: "CrUX LCP", status_before: "pass", prioridade: 0 })]}
        salvandoId={null}
        onAtualizarItem={() => {}}
      />
    );
    expect(screen.getByText(/Page Speed Insights/)).toBeInTheDocument();
    expect(screen.getByText(/Dados de campo/)).toBeInTheDocument();
  });

  it("filtro Reprovados esconde os pass", () => {
    render(
      <ChecklistGrid
        checklist={[item({}), item({ id: "i2", titulo: "Item aprovado", status_before: "pass", prioridade: 0 })]}
        salvandoId={null}
        onAtualizarItem={() => {}}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /reprovados/i }));
    expect(screen.getByText("Execução pesada")).toBeInTheDocument();
    expect(screen.queryByText("Item aprovado")).not.toBeInTheDocument();
  });

  it("mudar implementação dispara PATCH", () => {
    const onAtualizar = vi.fn();
    render(<ChecklistGrid checklist={[item({})]} salvandoId={null} onAtualizarItem={onAtualizar} />);
    fireEvent.change(screen.getByDisplayValue("Não executado"), { target: { value: "implementado" } });
    expect(onAtualizar).toHaveBeenCalledWith("i1", { status_implementacao: "implementado" });
  });

  it("editar prioridade dispara PATCH no blur", () => {
    const onAtualizar = vi.fn();
    render(<ChecklistGrid checklist={[item({})]} salvandoId={null} onAtualizarItem={onAtualizar} />);
    const input = screen.getByLabelText(/prioridade de Execução pesada/i);
    fireEvent.change(input, { target: { value: "5" } });
    fireEvent.blur(input);
    expect(onAtualizar).toHaveBeenCalledWith("i1", { prioridade: 5 });
  });

  it("item na não conta como reprovado", () => {
    render(
      <ChecklistGrid
        checklist={[item({ id: "i3", titulo: "Safe Browsing", status_before: "na", prioridade: 0 })]}
        salvandoId={null}
        onAtualizarItem={() => {}}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /reprovados/i }));
    expect(screen.queryByText("Safe Browsing")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/checklist-grid.test.tsx`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar**

`frontend/src/components/cwv/auditoria/checklist-grid.tsx`. Pontos obrigatórios (código completo
abaixo é o esqueleto integral — manter < 300 linhas):

```tsx
"use client";

// Tabela estilo Excel do checklist (SPEC_CWV_Auditoria_UI_V2 §3.2).
// Pass/Fail somente leitura; edita implementação, notas (cliente+SEO) e prioridade.

import { useMemo, useState } from "react";
import { Loader2Icon, ChevronDownIcon, ChevronRightIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { ChecklistItemResposta, OrigemItem, StatusCheck, StatusImplementacao } from "@/lib/api/cwv";

const ORIGEM_LABELS: Record<OrigemItem, string> = {
  psi_audit: "Page Speed Insights",
  field_data: "Dados de campo (CrUX)",
  page_experience: "Page Experience",
};

type Filtro = "todos" | "reprovados" | "aprovados" | "implementados";

export interface AtualizarItemDados {
  status_implementacao?: StatusImplementacao;
  nota_cliente?: string;
  nota_seo?: string;
  prioridade?: number;
}

interface Props {
  checklist: ChecklistItemResposta[];
  salvandoId: string | null;
  onAtualizarItem: (itemId: string, dados: AtualizarItemDados) => void;
}

function badgeStatus(s: StatusCheck | null) {
  if (s === "pass") return <span className="inline-flex rounded-md border border-success/30 bg-success/10 px-2 py-0.5 text-[10px] font-medium text-success">✔ Pass</span>;
  if (s === "fail") return <span className="inline-flex rounded-md border border-destructive/30 bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive">✖ Fail</span>;
  if (s === "na") return <span className="inline-flex rounded-md border bg-muted/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">n/a</span>;
  return <span className="text-[10px] text-muted-foreground">—</span>;
}

function tintaLinha(s: StatusCheck | null): string {
  if (s === "pass") return "bg-success/5";
  if (s === "fail") return "bg-destructive/5";
  return "";
}

export function ChecklistGrid({ checklist, salvandoId, onAtualizarItem }: Props) {
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [busca, setBusca] = useState("");
  const [colapsados, setColapsados] = useState<Record<string, boolean>>({});
  const [notasAbertas, setNotasAbertas] = useState<string | null>(null);
  // Ordenação por clique no header (spec §2: "ordenação por clique no header").
  const [sort, setSort] = useState<{ campo: "titulo" | "prioridade"; asc: boolean }>({ campo: "prioridade", asc: true });

  function toggleSort(campo: "titulo" | "prioridade") {
    setSort((s) => (s.campo === campo ? { campo, asc: !s.asc } : { campo, asc: true }));
  }

  const visiveis = useMemo(() => {
    return checklist.filter((i) => {
      if (filtro === "reprovados" && i.status_before !== "fail") return false;
      if (filtro === "aprovados" && i.status_before !== "pass") return false;
      if (filtro === "implementados" && i.status_implementacao !== "implementado") return false;
      if (busca && !i.titulo.toLowerCase().includes(busca.toLowerCase())) return false;
      return true;
    });
  }, [checklist, filtro, busca]);

  const grupos = useMemo(() => {
    const g: Partial<Record<OrigemItem, ChecklistItemResposta[]>> = {};
    for (const i of visiveis) (g[i.origem] ??= []).push(i);
    for (const lista of Object.values(g)) {
      lista!.sort((a, b) => {
        const cmp = sort.campo === "titulo"
          ? a.titulo.localeCompare(b.titulo)
          : (a.prioridade || 999) - (b.prioridade || 999);
        return sort.asc ? cmp : -cmp;
      });
    }
    return g;
  }, [visiveis, sort]);

  const filtros: { id: Filtro; rotulo: string }[] = [
    { id: "todos", rotulo: "Todos" },
    { id: "reprovados", rotulo: "Reprovados" },
    { id: "aprovados", rotulo: "Aprovados" },
    { id: "implementados", rotulo: "Implementados" },
  ];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {filtros.map((f) => (
          <button
            key={f.id}
            className={`rounded-full border px-3 py-1 text-xs ${filtro === f.id ? "border-brand bg-brand/10 font-medium text-brand" : "text-muted-foreground hover:text-foreground"}`}
            onClick={() => setFiltro(f.id)}
          >
            {f.rotulo}
          </button>
        ))}
        <input
          className="ml-auto w-48 rounded border bg-card px-2 py-1 text-xs"
          placeholder="Buscar item..."
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
      </div>

      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-card">
            <tr className="border-b text-left text-[11px] uppercase text-muted-foreground">
              <th className="px-3 py-2">
                <button onClick={() => toggleSort("titulo")} className="hover:text-foreground">
                  Item {sort.campo === "titulo" ? (sort.asc ? "↑" : "↓") : ""}
                </button>
              </th>
              <th className="px-2 py-2">Before</th>
              <th className="px-2 py-2">After</th>
              <th className="px-2 py-2">Implementação</th>
              <th className="px-2 py-2">
                <button onClick={() => toggleSort("prioridade")} className="hover:text-foreground">
                  Prio {sort.campo === "prioridade" ? (sort.asc ? "↑" : "↓") : ""}
                </button>
              </th>
              <th className="px-2 py-2">Esforço</th>
              <th className="px-2 py-2">Notas</th>
            </tr>
          </thead>
          <tbody>
            {(Object.keys(ORIGEM_LABELS) as OrigemItem[]).map((origem) => {
              const itens = grupos[origem];
              if (!itens || itens.length === 0) return null;
              const nPass = itens.filter((i) => i.status_before === "pass").length;
              const nFail = itens.filter((i) => i.status_before === "fail").length;
              const colapsado = colapsados[origem];
              return [
                <tr key={origem} className="cursor-pointer border-b bg-muted/30" onClick={() => setColapsados((c) => ({ ...c, [origem]: !c[origem] }))}>
                  <td colSpan={7} className="px-3 py-1.5 text-xs font-semibold">
                    <span className="inline-flex items-center gap-1">
                      {colapsado ? <ChevronRightIcon className="size-3" /> : <ChevronDownIcon className="size-3" />}
                      {ORIGEM_LABELS[origem]} ({itens.length})
                      <span className="ml-2 font-normal text-muted-foreground">
                        <span className="text-success">✔ {nPass}</span> · <span className="text-destructive">✖ {nFail}</span>
                      </span>
                    </span>
                  </td>
                </tr>,
                ...(colapsado ? [] : itens.map((item) => (
                  <LinhaItem
                    key={item.id}
                    item={item}
                    salvando={salvandoId === item.id}
                    notasAbertas={notasAbertas === item.id}
                    onToggleNotas={() => setNotasAbertas(notasAbertas === item.id ? null : item.id)}
                    onAtualizar={(dados) => onAtualizarItem(item.id, dados)}
                  />
                ))),
              ];
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LinhaItem({ item, salvando, notasAbertas, onToggleNotas, onAtualizar }: {
  item: ChecklistItemResposta;
  salvando: boolean;
  notasAbertas: boolean;
  onToggleNotas: () => void;
  onAtualizar: (dados: AtualizarItemDados) => void;
}) {
  const [prioLocal, setPrioLocal] = useState(String(item.prioridade ?? 0));
  const [notaCliente, setNotaCliente] = useState(item.nota_cliente ?? "");
  const [notaSeo, setNotaSeo] = useState(item.nota_seo ?? "");
  const nNotas = (item.nota_cliente ? 1 : 0) + (item.nota_seo ? 1 : 0);

  return (
    <>
      <tr className={`border-b ${tintaLinha(item.status_before)}`}>
        <td className="max-w-[280px] truncate px-3 py-2" title={item.titulo}>
          {salvando && <Loader2Icon className="mr-1 inline size-3 animate-spin text-muted-foreground" />}
          {item.titulo}
        </td>
        <td className="px-2 py-2">{badgeStatus(item.status_before)}</td>
        <td className="px-2 py-2">{badgeStatus(item.status_after)}</td>
        <td className="px-2 py-2">
          <select
            className="rounded border bg-card px-2 py-1 text-xs"
            value={item.status_implementacao}
            onChange={(e) => onAtualizar({ status_implementacao: e.target.value as StatusImplementacao })}
          >
            <option value="nao_executado">Não executado</option>
            <option value="em_andamento">Em andamento</option>
            <option value="implementado">Implementado</option>
          </select>
        </td>
        <td className="px-2 py-2">
          <input
            type="number"
            min={0}
            aria-label={`prioridade de ${item.titulo}`}
            className="w-14 rounded border bg-card px-1.5 py-1 text-xs"
            value={prioLocal}
            onChange={(e) => setPrioLocal(e.target.value)}
            onBlur={() => {
              const n = Math.max(0, parseInt(prioLocal, 10) || 0);
              if (n !== item.prioridade) onAtualizar({ prioridade: n });
            }}
          />
        </td>
        <td className="px-2 py-2">{item.esforco && <Badge variant="outline" className="text-[9px]">{item.esforco}</Badge>}</td>
        <td className="px-2 py-2">
          <button className="text-xs text-muted-foreground hover:text-foreground" onClick={onToggleNotas}>
            📝{nNotas > 0 ? ` ${nNotas}` : ""}
          </button>
        </td>
      </tr>
      {notasAbertas && (
        <tr className="border-b bg-muted/20">
          <td colSpan={7} className="px-3 py-2">
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="space-y-1 text-[11px] text-muted-foreground">
                Nota do cliente
                <textarea className="w-full resize-none rounded border bg-card px-2 py-1 text-xs" rows={2}
                  value={notaCliente} onChange={(e) => setNotaCliente(e.target.value)} />
              </label>
              <label className="space-y-1 text-[11px] text-muted-foreground">
                Nota SEO
                <textarea className="w-full resize-none rounded border bg-card px-2 py-1 text-xs" rows={2}
                  value={notaSeo} onChange={(e) => setNotaSeo(e.target.value)} />
              </label>
            </div>
            <button
              className="mt-1 rounded bg-brand px-2 py-0.5 text-[11px] text-white"
              onClick={() => { onAtualizar({ nota_cliente: notaCliente, nota_seo: notaSeo }); onToggleNotas(); }}
            >
              Salvar notas
            </button>
          </td>
        </tr>
      )}
    </>
  );
}
```

> Desvio registrável: spec citava `Select`/`Popover` shadcn — `frontend/src/components/ui/` não
> tem esses componentes; usar `<select>` nativo (padrão já existente no `ItemChecklist` atual,
> linha 450) e linha expansível de notas. Registrar no Histórico da spec (Task 11).

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/checklist-grid.test.tsx`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/components/cwv/auditoria/checklist-grid.tsx frontend/src/components/cwv/__tests__/checklist-grid.test.tsx
rtk git commit -m "feat(cwv): ChecklistGrid — tabela estilo Excel com edicao inline

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: componente `before-after-tab.tsx`

**Files:**
- Create: `frontend/src/components/cwv/auditoria/before-after-tab.tsx`
- Test: `frontend/src/components/cwv/__tests__/before-after-tab.test.tsx`

**Interfaces:**
- Consumes: `buscarComparativoAuditoria` + tipos `ComparativoPar` (Task 4).
- Produces: `<BeforeAfterTab auditoriaId={id} fase={fase} />` (fetch interno). Usado pela Task 10.

- [ ] **Step 1: Teste falhando**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

const mockBuscar = vi.fn();
vi.mock("@/lib/api/cwv", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/cwv")>()),
  buscarComparativoAuditoria: (...a: unknown[]) => mockBuscar(...a),
}));

import { BeforeAfterTab } from "@/components/cwv/auditoria/before-after-tab";

const par = {
  url_canonica: "https://a.com/",
  estrategia: "mobile",
  template_tipo: "home",
  before: { analise_id: "b1", score_performance: 23, lcp_ms: 4200, cls: 0.57, inp_ms: 348, tbt_ms: 890, n_problemas: 22 },
  after: { analise_id: "a1", score_performance: 61, lcp_ms: 2100, cls: 0.09, inp_ms: 180, tbt_ms: 300, n_problemas: 10 },
  problemas: { resolvidos: 12, persistentes: 8, novos: 2, titulos_resolvidos: ["Imagem grande"], titulos_novos: ["Novo problema"] },
};

describe("BeforeAfterTab", () => {
  it("card por URL com métricas e deltas", async () => {
    mockBuscar.mockResolvedValue({ fase: "after", pares: [par] });
    render(<BeforeAfterTab auditoriaId="x" fase="after" />);
    await waitFor(() => expect(screen.getByText("https://a.com/")).toBeInTheDocument());
    expect(screen.getByText("23")).toBeInTheDocument();
    expect(screen.getByText("61")).toBeInTheDocument();
    expect(screen.getByText(/12 resolvidos/)).toBeInTheDocument();
    expect(screen.getByText(/2 novos/)).toBeInTheDocument();
  });

  it("fase before mostra baseline + aviso", async () => {
    mockBuscar.mockResolvedValue({ fase: "before", pares: [{ ...par, after: null, problemas: null }] });
    render(<BeforeAfterTab auditoriaId="x" fase="before" />);
    await waitFor(() => expect(screen.getByText(/aguardando re-auditoria/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/before-after-tab.test.tsx`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar**

```tsx
"use client";

// Aba Before/After por URL (SPEC_CWV_Auditoria_UI_V2 §3.1 + Comparativo API).

import { useEffect, useState } from "react";
import { ArrowDownIcon, ArrowUpIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  buscarComparativoAuditoria,
  type ComparativoPar,
  type ComparativoMetricas,
  type FaseAuditoria,
} from "@/lib/api/cwv";
import { mensagemErroAmigavel } from "@/lib/api";

interface Props {
  auditoriaId: string;
  fase: FaseAuditoria;
}

// menorMelhor: LCP/CLS/INP/TBT melhoram quando caem; score melhora quando sobe.
const METRICAS: { chave: keyof ComparativoMetricas; rotulo: string; menorMelhor: boolean; fmt: (v: number) => string }[] = [
  { chave: "score_performance", rotulo: "Score", menorMelhor: false, fmt: (v) => String(v) },
  { chave: "lcp_ms", rotulo: "LCP", menorMelhor: true, fmt: (v) => `${(v / 1000).toFixed(1)}s` },
  { chave: "cls", rotulo: "CLS", menorMelhor: true, fmt: (v) => v.toFixed(2) },
  { chave: "inp_ms", rotulo: "INP", menorMelhor: true, fmt: (v) => `${Math.round(v)}ms` },
  { chave: "tbt_ms", rotulo: "TBT", menorMelhor: true, fmt: (v) => `${Math.round(v)}ms` },
];

export function BeforeAfterTab({ auditoriaId, fase }: Props) {
  const [pares, setPares] = useState<ComparativoPar[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    buscarComparativoAuditoria(auditoriaId)
      .then((r) => setPares(r.pares))
      .catch((e) => setErro(mensagemErroAmigavel(e)));
  }, [auditoriaId]);

  if (erro) return <p className="text-sm text-destructive">{erro}</p>;
  if (!pares) return <div className="h-32 animate-pulse rounded-xl bg-muted/50" />;

  const semAfter = pares.every((p) => p.after === null);

  return (
    <div className="space-y-4">
      {semAfter && (
        <div className="rounded-xl border border-yellow-400/40 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
          Baseline registrado — comparação disponível após a re-auditoria (aguardando re-auditoria).
        </div>
      )}
      {pares.map((p) => (
        <CardPar key={`${p.url_canonica}-${p.estrategia}`} par={p} />
      ))}
    </div>
  );
}

function CardPar({ par }: { par: ComparativoPar }) {
  const [expandido, setExpandido] = useState(false);
  return (
    <div className="glass-card space-y-3 rounded-2xl p-5">
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-sm font-medium" title={par.url_canonica}>{par.url_canonica}</p>
        <Badge variant="outline" className="text-[10px]">{par.estrategia}</Badge>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase text-muted-foreground">
            <th className="py-1">Métrica</th><th>Before</th><th>After</th><th>Δ</th>
          </tr>
        </thead>
        <tbody>
          {METRICAS.map(({ chave, rotulo, menorMelhor, fmt }) => {
            const antes = par.before[chave] as number | null;
            const depois = par.after ? (par.after[chave] as number | null) : null;
            const delta = antes !== null && depois !== null ? depois - antes : null;
            const melhorou = delta !== null && (menorMelhor ? delta < 0 : delta > 0);
            return (
              <tr key={chave} className="border-t">
                <td className="py-1.5 text-muted-foreground">{rotulo}</td>
                <td>{antes !== null ? fmt(antes) : "—"}</td>
                <td>{depois !== null ? fmt(depois) : "—"}</td>
                <td>
                  {delta !== null && delta !== 0 && (
                    <span className={`inline-flex items-center gap-0.5 text-xs ${melhorou ? "text-success" : "text-destructive"}`}>
                      {melhorou ? <ArrowUpIcon className="size-3" /> : <ArrowDownIcon className="size-3" />}
                      {fmt(Math.abs(delta))}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {par.problemas && (
        <div className="space-y-1">
          <button className="text-xs text-muted-foreground hover:text-foreground" onClick={() => setExpandido(!expandido)}>
            <span className="text-success">✔ {par.problemas.resolvidos} resolvidos</span>
            {" · "}<span>⚑ {par.problemas.persistentes} persistentes</span>
            {" · "}<span className="text-destructive">✖ {par.problemas.novos} novos</span>
          </button>
          {expandido && (
            <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
              <div>
                <p className="font-medium text-success">Resolvidos</p>
                <ul className="list-inside list-disc">{par.problemas.titulos_resolvidos.map((t) => <li key={t}>{t}</li>)}</ul>
              </div>
              <div>
                <p className="font-medium text-destructive">Novos</p>
                <ul className="list-inside list-disc">{par.problemas.titulos_novos.map((t) => <li key={t}>{t}</li>)}</ul>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/before-after-tab.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/components/cwv/auditoria/before-after-tab.tsx frontend/src/components/cwv/__tests__/before-after-tab.test.tsx
rtk git commit -m "feat(cwv): aba Before/After por URL com deltas e diff de problemas

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: componente `visao-geral-tab.tsx`

**Files:**
- Create: `frontend/src/components/cwv/auditoria/visao-geral-tab.tsx`
- Test: `frontend/src/components/cwv/__tests__/visao-geral-tab.test.tsx`

**Interfaces:**
- Consumes: `HealthDonut` (Task 5), `HealthEvolucaoChart` (Task 6), `listarAuditoriasCwv`, `AuditoriaResposta`, `ProblemaConsolidadoResposta`.
- Produces: `<VisaoGeralTab auditoria={auditoria} consolidados={consolidados | null} onIrParaChecklist={() => void} />`. Usado pela Task 10.

- [ ] **Step 1: Teste falhando**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

const mockListar = vi.fn();
vi.mock("@/lib/api/cwv", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/cwv")>()),
  listarAuditoriasCwv: (...a: unknown[]) => mockListar(...a),
}));

import { VisaoGeralTab } from "@/components/cwv/auditoria/visao-geral-tab";
import type { AuditoriaResposta } from "@/lib/api/cwv";

const auditoria = {
  id: "x", cliente_id: "c1", titulo: "Kumon", fase: "after",
  execucao_before_id: "e1", execucao_after_id: "e2",
  health_score_before: 48.3, health_score_after: 72.0,
  consolidacao_status: "concluida", checklist: [
    { id: "i1", origem: "psi_audit", item_codigo: "k", titulo: "t", status_before: "fail", status_after: "pass", status_implementacao: "implementado", nota_cliente: null, nota_seo: null, prioridade: 1, esforco: "alto", escopo_json: {} },
  ],
  n_pass_before: 9, n_fail_before: 29, n_implementados: 1,
  relatorio_json: null, criado_em: "2026-07-15T00:00:00Z", atualizado_em: "2026-07-15T00:00:00Z",
} as unknown as AuditoriaResposta;

describe("VisaoGeralTab", () => {
  it("donuts + top consolidados", async () => {
    mockListar.mockResolvedValue({ auditorias: [] });
    render(
      <VisaoGeralTab
        auditoria={auditoria}
        consolidados={[{ id: "c1", titulo: "Execução pesada", causa_raiz: "Bundle grande", severidade: 5, esforco: "alto", metricas_afetadas: ["TBT"], prioridade_ordem: 1, kb_codigo: null, problemas_origem_ids: [], escopo_json: {}, evidencias_json: {}, recomendacao_md: null } as never]}
        onIrParaChecklist={() => {}}
      />
    );
    expect(screen.getByTestId("donut-before")).toBeInTheDocument();
    expect(screen.getByTestId("donut-after")).toBeInTheDocument();
    expect(screen.getByText("Execução pesada")).toBeInTheDocument();
    await waitFor(() => expect(mockListar).toHaveBeenCalledWith("c1"));
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/visao-geral-tab.test.tsx`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar**

```tsx
"use client";

// Aba Visão Geral (SPEC_CWV_Auditoria_UI_V2 §3.1): donuts grandes + evolução + top-5 consolidados.

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { HealthDonut } from "./health-donut";
import { HealthEvolucaoChart } from "./health-evolucao-chart";
import {
  listarAuditoriasCwv,
  type AuditoriaResposta,
  type AuditoriaResumo,
  type ProblemaConsolidadoResposta,
} from "@/lib/api/cwv";

interface Props {
  auditoria: AuditoriaResposta;
  consolidados: ProblemaConsolidadoResposta[] | null;
  onIrParaChecklist: () => void;
}

export function VisaoGeralTab({ auditoria, consolidados, onIrParaChecklist }: Props) {
  const [historico, setHistorico] = useState<AuditoriaResumo[]>([]);

  useEffect(() => {
    listarAuditoriasCwv(auditoria.cliente_id).then((r) => setHistorico(r.auditorias)).catch(() => {});
  }, [auditoria.cliente_id]);

  // Contadores do donut: pass/fail do checklist (before) e (after quando existe).
  const passAfter = auditoria.checklist.filter((i) => i.status_after === "pass").length;
  const failAfter = auditoria.checklist.filter((i) => i.status_after === "fail").length;
  const temAfter = auditoria.health_score_after !== null;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="glass-card flex items-center justify-around rounded-2xl p-5">
          <HealthDonut pass={auditoria.n_pass_before} fail={auditoria.n_fail_before} label="Before" />
          <HealthDonut
            pass={temAfter ? passAfter : null}
            fail={temAfter ? failAfter : null}
            label="After"
            hint="aguardando re-auditoria"
          />
        </div>
        <HealthEvolucaoChart auditorias={historico} auditoriaAtualId={auditoria.id} />
      </div>

      {consolidados && consolidados.length > 0 && (
        <div className="glass-card space-y-2 rounded-2xl p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Top problemas consolidados</h2>
            <button className="text-xs text-brand hover:underline" onClick={onIrParaChecklist}>
              Ver checklist completo →
            </button>
          </div>
          {consolidados.slice(0, 5).map((c) => (
            <div key={c.id} className="rounded-lg border bg-surface-light px-4 py-2.5">
              <div className="flex items-start justify-between gap-2">
                <p className="flex-1 text-sm font-medium">{c.titulo}</p>
                <div className="flex shrink-0 gap-1">
                  <Badge variant="outline" className="text-[9px]">Sev {c.severidade}</Badge>
                  {c.esforco && <Badge variant="outline" className="text-[9px]">{c.esforco}</Badge>}
                </div>
              </div>
              {c.causa_raiz && <p className="mt-0.5 text-xs text-muted-foreground">{c.causa_raiz}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/visao-geral-tab.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/components/cwv/auditoria/visao-geral-tab.tsx frontend/src/components/cwv/__tests__/visao-geral-tab.test.tsx
rtk git commit -m "feat(cwv): aba Visao Geral (donuts + evolucao + top consolidados)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: header, abas com `?tab=` e reescrita do orquestrador

**Files:**
- Create: `frontend/src/components/cwv/auditoria/auditoria-header.tsx`
- Modify: `frontend/src/components/cwv/cwv-auditoria-client.tsx` (reescrita — vira orquestrador)
- Test: `frontend/src/components/cwv/__tests__/auditoria-header.test.tsx`

**Interfaces:**
- Consumes: tudo das Tasks 5-9; handlers existentes do client atual (`handleConsolidar`, `handleGerarRelatorio`, `handleBaixarDocx`, `handleReauditar`, `handleAtualizarItem` — linhas 88-187, preservar comportamento incluindo pollings).
- Produces: página final com header + 3 abas.

**ANTES DE COMEÇAR:** ler `frontend/node_modules/next/dist/docs/01-app/` (seções de `useSearchParams` e `useRouter`) — Next 16.2.4 tem breaking changes (aviso do `frontend/AGENTS.md`).

- [ ] **Step 1: Teste falhando (header)**

`frontend/src/components/cwv/__tests__/auditoria-header.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("@/lib/utils", () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(" ") }));

import { AuditoriaHeader } from "@/components/cwv/auditoria/auditoria-header";

describe("AuditoriaHeader", () => {
  it("mostra fase, donuts compactos e delta", () => {
    render(
      <AuditoriaHeader
        titulo="Kumon" fase="after"
        healthBefore={48.3} healthAfter={72.0}
        nPassBefore={9} nFailBefore={29} nPassAfter={20} nFailAfter={8}
        criadoEm="2026-07-15T00:00:00Z"
      />
    );
    expect(screen.getByText(/After \(re-auditoria\)/)).toBeInTheDocument();
    expect(screen.getByText(/\+23\.7/)).toBeInTheDocument();
    expect(screen.getByTestId("donut-before")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/auditoria-header.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implementar header**

`frontend/src/components/cwv/auditoria/auditoria-header.tsx`:

```tsx
"use client";

// Header fixo da auditoria: fase + donuts compactos + delta (SPEC_CWV_Auditoria_UI_V2 §3.1).

import { Badge } from "@/components/ui/badge";
import { HealthDonut } from "./health-donut";
import type { FaseAuditoria } from "@/lib/api/cwv";

export const FASE_LABELS: Record<FaseAuditoria, string> = {
  before: "Before (auditoria inicial)",
  aguardando_implementacao: "Aguardando implementação",
  after: "After (re-auditoria)",
  concluida: "Concluída",
};

export const FASE_CORES: Record<FaseAuditoria, string> = {
  before: "border-blue-400 text-blue-700 bg-blue-50",
  aguardando_implementacao: "border-yellow-400 text-yellow-700 bg-yellow-50",
  after: "border-purple-400 text-purple-700 bg-purple-50",
  concluida: "border-success/30 text-success bg-success/10",
};

interface Props {
  titulo: string;
  fase: FaseAuditoria;
  healthBefore: number | null;
  healthAfter: number | null;
  nPassBefore: number;
  nFailBefore: number;
  nPassAfter: number | null;
  nFailAfter: number | null;
  criadoEm: string;
}

export function AuditoriaHeader(p: Props) {
  const delta = p.healthBefore !== null && p.healthAfter !== null ? p.healthAfter - p.healthBefore : null;
  return (
    <div className="glass-card rounded-2xl p-5">
      <div className="flex items-center justify-between gap-3">
        <Badge variant="outline" className={FASE_CORES[p.fase]}>{FASE_LABELS[p.fase]}</Badge>
        <span className="text-xs text-muted-foreground">{new Date(p.criadoEm).toLocaleDateString("pt-BR")}</span>
      </div>
      <div className="mt-3 flex items-center justify-center gap-8">
        <HealthDonut pass={p.nPassBefore} fail={p.nFailBefore} label="Before" size={90} />
        <div className="text-center">
          {delta !== null ? (
            <p className={`text-lg font-bold ${delta >= 0 ? "text-success" : "text-destructive"}`}>
              {delta >= 0 ? "+" : ""}{delta.toFixed(1)} p.p. {delta >= 0 ? "↑" : "↓"}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">Δ após re-auditoria</p>
          )}
        </div>
        <HealthDonut pass={p.nPassAfter} fail={p.nFailAfter} label="After" size={90} hint="pendente" />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/auditoria-header.test.tsx`
Expected: PASS.

- [ ] **Step 5: Reescrever o orquestrador**

`cwv-auditoria-client.tsx` — manter TODO o estado/handlers/pollings existentes (linhas 65-187
inalterados na lógica) e trocar apenas o JSX de render (linhas 218-402):

- `PageHeader` + `AuditoriaHeader` (props derivadas: `nPassAfter`/`nFailAfter` contados do
  checklist como na Task 9; `null` quando `health_score_after === null`).
- Abas shadcn `Tabs` (`@/components/ui/tabs`) controladas:

```tsx
const searchParams = useSearchParams();
const tab = searchParams.get("tab") ?? "visao-geral";
function setTab(t: string) {
  const sp = new URLSearchParams(searchParams.toString());
  sp.set("tab", t);
  router.replace(`${pathname}?${sp.toString()}`);
}
// <Tabs value={tab} onValueChange={setTab}> com TabsTrigger:
//   visao-geral → <VisaoGeralTab auditoria={auditoria} consolidados={consolidados} onIrParaChecklist={() => setTab("checklist")} />
//   checklist   → <ChecklistGrid checklist={auditoria.checklist} salvandoId={salvandoId} onAtualizarItem={handleAtualizarItem} />
//   before-after→ <BeforeAfterTab auditoriaId={id} fase={auditoria.fase} />
```

- `handleAtualizarItem` ganha assinatura com os novos campos (tipo `AtualizarItemDados` exportado
  pelo grid) — atualização **otimista**: aplicar no estado local antes do PATCH e reverter em erro:

```tsx
async function handleAtualizarItem(itemId: string, dados: AtualizarItemDados) {
  const anterior = auditoria;
  setAuditoria((a) => a && {
    ...a,
    checklist: a.checklist.map((i) => (i.id === itemId ? { ...i, ...dados } : i)),
  });
  setSalvandoId(itemId);
  try {
    await atualizarItemChecklistCwv(id, itemId, dados);
    const atualizada = await buscarAuditoriaCwv(id);
    setAuditoria(atualizada);
  } catch (e) {
    setAuditoria(anterior); // rollback
    toast.error(mensagemErroAmigavel(e));
  } finally {
    setSalvandoId(null);
  }
}
```

- Blocos de consolidação/relatório/fase/re-auditar existentes (linhas 286-399) ficam **abaixo das
  abas** na aba Visão Geral? Não — mantê-los fora das abas, após o `<Tabs>` (ações globais da
  auditoria), sem mudança de lógica.
- Remover `FASE_LABELS`/`FASE_CORES` locais (importar do header) e o componente `ItemChecklist`
  (substituído pelo grid). `ORIGEM_LABELS`, `corStatus`, `rotuloStatus` morrem com ele.

- [ ] **Step 6: Rodar TODOS os testes do CWV + typecheck**

Run: `cd frontend && pnpm test -- --run src/components/cwv/__tests__/ && pnpm tsc --noEmit`
Expected: PASS, sem erros de tipo.

- [ ] **Step 7: Commit**

```bash
rtk git add frontend/src/components/cwv/auditoria/auditoria-header.tsx frontend/src/components/cwv/cwv-auditoria-client.tsx frontend/src/components/cwv/__tests__/auditoria-header.test.tsx
rtk git commit -m "feat(cwv): pagina da auditoria em abas (header donuts + ?tab=)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: verificação final, specs e build

**Files:**
- Modify: `docs/specs/ferramentas/core-web-vitals/SPEC_CWV_Auditoria_Comparativo_API.md` (status + histórico)
- Modify: `docs/specs/ferramentas/core-web-vitals/SPEC_CWV_Auditoria_UI_V2.md` (status + histórico + desvios registrados)

- [ ] **Step 1: Suíte completa**

Run: `cd backend && uv run pytest tests/unit -q` — Expected: tudo verde.
Run: `cd frontend && pnpm test -- --run` — Expected: tudo verde.

- [ ] **Step 2: Build de export estático**

Run: `cd frontend && rtk next build`
Expected: build passa (rota `auditoria/[auditoriaId]` com `generateStaticParams` intacta).

- [ ] **Step 3: Verificação manual (skill verify / make dev)**

Backend local + front dev; abrir uma auditoria real e conferir: donuts corretos, edição de
implementação/prio/notas persiste após reload, filtros e colapso de grupos, `?tab=` deep-link,
aba Before/After com fase before mostra baseline.

- [ ] **Step 4: Atualizar as 2 specs**

Status `📋 planejado` → `✅ implementado`; commit hash no header; no Histórico da UI V2 registrar
os desvios: donut SVG puro (em vez de recharts PieChart) e `<select>` nativo + linha expansível
de notas (em vez de Select/Popover shadcn inexistentes).

- [ ] **Step 5: Commit final**

```bash
rtk git add docs/specs/ferramentas/core-web-vitals/SPEC_CWV_Auditoria_Comparativo_API.md docs/specs/ferramentas/core-web-vitals/SPEC_CWV_Auditoria_UI_V2.md
rtk git commit -m "docs(cwv): marca specs Comparativo API e Auditoria UI V2 como implementadas

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
