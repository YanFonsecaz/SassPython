# SPEC — CWV Re-analisar + Comparador + Chart de Evolução

**Status:** ✅ implementado · **Escopo:** backend (validação do endpoint /reanalisar) + frontend (dialog, chart, comparador entre análises)
**Dependências:** [[SPEC_Ferramenta_Core_Web_Vitals]] (endpoint existe), [[SPEC_CWV_Dashboard_Historico]] (chart estrutura)
**Esforço estimado:** ~2 dias

## 1. Problema

O e2e de 2026-05-26 confirmou que:
- Endpoint `POST /reanalisar/{analise_id}` existe e foi corrigido (`mode="json"`)
- Componente `ReanalisarDialog` está montado no dashboard URL
- Componente `EvolucaoChart` está montado mas **só renderiza com ≥2 análises da mesma URL** (estado nunca alcançado no e2e)
- **Comparador entre análises** (delta de score, métricas que melhoraram/pioraram, problemas resolvidos/novos) não foi exercitado

Como nenhuma URL teve 2+ análises bem-sucedidas durante o e2e, todo o fluxo de "evolução temporal" está **funcional em teoria mas não validado**.

Pior: a SPEC original do dashboard (§3.4 do [[SPEC_CWV_Dashboard_Historico]]) menciona "comparador entre análises" como parte do dashboard URL, mas o componente atual **não implementa o comparador** — só mostra a análise atual.

## 2. Cenários a validar/implementar

### 2.1 Re-analisar via dialog (já existe, falta validar)

Fluxo:
1. Usuário no dashboard URL clica em "Re-analisar"
2. Dialog confirma custo (16 créditos para 1 URL)
3. Submit chama `POST /reanalisar/{analise_id}` → 202 com `execucao_id`
4. Dialog fecha, mostra toast "Re-análise enfileirada"
5. Usuário é redirecionado para `/execucao/{id}` para polling

**Status:** existe na UI, não foi exercitado no e2e. Apenas precisa validação.

### 2.2 Chart de evolução (componente existe, dados nunca)

```
┌──── Evolução (3 análises) ──────────────────────┐
│ [Score] [LCP] [CLS] [INP] [Todas]                │
│                                                   │
│  100 ─┐                                          │
│   80 ─┤         ●                                │
│   60 ─┤  ●            ●                          │
│   40 ─┤                                          │
│       └─ 12/mai ── 19/mai ── 26/mai ─────────────│
└──────────────────────────────────────────────────┘
```

**Status:** já implementado em `cwv-evolucao-chart.tsx`. Falta validar render real.

### 2.3 Comparador entre análises (NOVO — falta implementar)

Atualmente o `MetricasResumo` recebe `analiseAnterior` mas só usa para exibir delta em cada métrica. Não há visão consolidada de "o que mudou entre as duas".

**Adicionar** seção no dashboard URL (entre `MetricasResumo` e `PlanoAcaoAccordion`):

```
┌──── Comparação com análise anterior (há 7 dias) ─────┐
│                                                       │
│ 📈 Melhoraram:                                        │
│   ✓ LCP: 4.2s → 2.1s (−50%)                          │
│   ✓ Score: 52 → 78 (+26 pts)                         │
│                                                       │
│ 📉 Pioraram:                                          │
│   ✗ CLS: 0.05 → 0.12 (+140%)                         │
│                                                       │
│ ✅ Problemas resolvidos (4):                         │
│   • Imagem do LCP muito grande                       │
│   • CSS bloqueante                                   │
│   • [+2 mais]                                        │
│                                                       │
│ ⚠️ Novos problemas (1):                              │
│   • Layout shift em iframe                           │
└───────────────────────────────────────────────────────┘
```

## 3. Backend (validação + 1 endpoint novo)

### 3.1 Re-analisar — apenas testar (sem mudança de código)

Já validado o fix de `mode="json"` no e2e. Adicionar testes:

```python
# em backend/tests/cwv/test_router_reanalisar.py
@pytest.mark.asyncio
async def test_reanalisar_persiste_nova_analise_e_marca_concluida(...):
    """E2E: dispara reanalise, mocka PSI, aguarda worker, valida nova análise no DB"""
    ...
```

### 3.2 Endpoint NOVO: comparar análises (`GET /comparacao`)

```python
@router.get("/core-web-vitals/comparacao/{analise_id}")
async def comparar_com_anterior(analise_id: str, ...):
    """
    Retorna comparação entre analise_id e a análise imediatamente anterior
    da mesma url_canonica + cliente.

    Response:
    {
        "analise_atual_id": "uuid",
        "analise_anterior_id": "uuid",
        "dias_decorridos": 7,
        "metricas": {
            "score": {"antes": 52, "depois": 78, "delta": 26, "melhorou": true},
            "lcp_ms": {"antes": 4200, "depois": 2100, "delta": -2100, "melhorou": true},
            ...
        },
        "problemas_resolvidos": [{"kb_codigo": "x", "titulo": "..."}],
        "problemas_novos": [{"kb_codigo": "y", "titulo": "..."}],
        "problemas_persistentes": [{"kb_codigo": "z", "titulo": "..."}]
    }
    ```
```

Implementação:
1. Carrega análise atual + problemas
2. Busca análise anterior (mesma url_canonica + cliente, criado_em < atual, mais recente)
3. Se não existe, retorna `null` ou 404
4. Carrega problemas anteriores
5. Calcula deltas por métrica (com flag `melhorou` baseada na direção: LCP/CLS/INP/TBT/FCP/TTFB menor = melhor; score maior = melhor)
6. Set diff por `kb_codigo`:
   - resolvidos = anteriores \ atuais
   - novos = atuais \ anteriores
   - persistentes = atuais ∩ anteriores

Schema Pydantic `ComparacaoResposta` em `app/schemas/cwv.py`.

### 3.3 Persistência: novo helper

Adicionar em `cwv_persistencia.py`:

```python
async def buscar_analise_anterior(
    session, url_canonica: str, cliente_id: str, antes_de: datetime
) -> CwvAnalise | None:
    """Retorna a análise imediatamente anterior à data dada para mesma URL+cliente."""
    resultado = await session.execute(
        select(CwvAnalise)
        .where(
            CwvAnalise.cliente_id == cliente_id,
            CwvAnalise.url_canonica == url_canonica,
            CwvAnalise.criado_em < antes_de,
            CwvAnalise.status == "sucesso",
        )
        .order_by(CwvAnalise.criado_em.desc())
        .limit(1)
    )
    return resultado.scalar_one_or_none()
```

## 4. Frontend

### 4.1 Componente `CwvComparadorAnalises` (NOVO)

`frontend/src/components/cwv/cwv-comparador.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { TrendingUpIcon, TrendingDownIcon, CheckCircle2Icon, AlertCircleIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { buscarComparacaoCwv } from "@/lib/api/cwv";
import type { CwvComparacaoResposta } from "@/lib/api/cwv";

interface ComparadorProps {
  analiseId: string;
}

export function CwvComparador({ analiseId }: ComparadorProps) {
  const [data, setData] = useState<CwvComparacaoResposta | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    buscarComparacaoCwv(analiseId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setCarregando(false));
  }, [analiseId]);

  if (carregando) return <div className="h-32 rounded-xl bg-muted/50 animate-pulse" />;
  if (!data) return null; // sem análise anterior

  const metricasMelhora = Object.entries(data.metricas).filter(([, m]) => m.melhorou && m.delta !== 0);
  const metricasPioraram = Object.entries(data.metricas).filter(([, m]) => !m.melhorou && m.delta !== 0);

  return (
    <div className="glass-card rounded-2xl p-6 sm:p-8 space-y-5">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
        Comparação com análise anterior · há {data.dias_decorridos} dia{data.dias_decorridos !== 1 ? "s" : ""}
      </h3>

      {metricasMelhora.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-success flex items-center gap-2">
            <TrendingUpIcon className="size-4" /> Melhoraram
          </p>
          <ul className="space-y-1.5 text-sm">
            {metricasMelhora.map(([nome, m]) => (
              <li key={nome} className="pl-6">
                <span className="font-mono uppercase text-xs">{nome}</span>:{" "}
                {formatMetricaValor(nome, m.antes)} → {formatMetricaValor(nome, m.depois)}{" "}
                <span className="text-success font-medium">({formatDelta(nome, m.delta)})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {metricasPioraram.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-destructive flex items-center gap-2">
            <TrendingDownIcon className="size-4" /> Pioraram
          </p>
          <ul className="space-y-1.5 text-sm">
            {metricasPioraram.map(([nome, m]) => (
              <li key={nome} className="pl-6">
                <span className="font-mono uppercase text-xs">{nome}</span>:{" "}
                {formatMetricaValor(nome, m.antes)} → {formatMetricaValor(nome, m.depois)}{" "}
                <span className="text-destructive font-medium">({formatDelta(nome, m.delta)})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.problemas_resolvidos.length > 0 && (
        <div className="space-y-2 border-t border-border pt-4">
          <p className="text-sm font-medium text-success flex items-center gap-2">
            <CheckCircle2Icon className="size-4" /> Problemas resolvidos ({data.problemas_resolvidos.length})
          </p>
          <ul className="space-y-1.5 text-sm pl-6">
            {data.problemas_resolvidos.slice(0, 3).map((p) => (
              <li key={p.kb_codigo} className="text-muted-foreground">• {p.titulo}</li>
            ))}
            {data.problemas_resolvidos.length > 3 && (
              <li className="text-xs text-muted-foreground">[+{data.problemas_resolvidos.length - 3} mais]</li>
            )}
          </ul>
        </div>
      )}

      {data.problemas_novos.length > 0 && (
        <div className="space-y-2 border-t border-border pt-4">
          <p className="text-sm font-medium text-amber-600 flex items-center gap-2">
            <AlertCircleIcon className="size-4" /> Novos problemas ({data.problemas_novos.length})
          </p>
          <ul className="space-y-1.5 text-sm pl-6">
            {data.problemas_novos.slice(0, 3).map((p) => (
              <li key={p.kb_codigo} className="text-muted-foreground">• {p.titulo}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function formatMetricaValor(nome: string, valor: number) {
  if (nome === "cls") return valor.toFixed(3);
  if (nome === "score") return String(Math.round(valor));
  return `${Math.round(valor)}ms`;
}

function formatDelta(nome: string, delta: number) {
  if (nome === "score") return `${delta > 0 ? "+" : ""}${Math.round(delta)} pts`;
  const pct = ((delta / Math.abs(delta)) * 100).toFixed(0);
  return `${delta > 0 ? "+" : ""}${pct}%`;
}
```

### 4.2 Integração no `cwv-dashboard-client.tsx`

Adicionar entre `MetricasResumo` e `PlanoAcaoAccordion`:

```tsx
{historico.length >= 2 && (
  <CwvComparador analiseId={analiseAtual.id} />
)}
```

### 4.3 Cliente API em `lib/api/cwv.ts`

```ts
export interface CwvComparacaoMetrica {
  antes: number;
  depois: number;
  delta: number;
  melhorou: boolean;
}

export interface CwvProblemaSimplificado {
  kb_codigo: string;
  titulo: string;
  severidade: number;
}

export interface CwvComparacaoResposta {
  analise_atual_id: string;
  analise_anterior_id: string;
  dias_decorridos: number;
  metricas: Record<"score" | "lcp" | "cls" | "inp" | "tbt" | "fcp" | "ttfb", CwvComparacaoMetrica>;
  problemas_resolvidos: CwvProblemaSimplificado[];
  problemas_novos: CwvProblemaSimplificado[];
  problemas_persistentes: CwvProblemaSimplificado[];
}

export async function buscarComparacaoCwv(analiseId: string): Promise<CwvComparacaoResposta | null> {
  try {
    return await api.get(`/ferramentas/core-web-vitals/comparacao/${analiseId}`);
  } catch (err) {
    if (err && typeof err === "object" && "status" in err && (err as { status: number }).status === 404) {
      return null;
    }
    throw err;
  }
}
```

## 5. Plano de execução

| Fase | O que | Esforço |
|---|---|---|
| R1 | Backend: schema `ComparacaoResposta` + `buscar_analise_anterior` helper | 0.25 dia |
| R2 | Backend: endpoint `GET /comparacao/{analise_id}` | 0.25 dia |
| R3 | Backend: tests para endpoint + helper | 0.25 dia |
| R4 | Frontend: cliente API + componente `CwvComparador` | 0.5 dia |
| R5 | Frontend: integrar no dashboard URL | 0.25 dia |
| R6 | E2E manual: criar 2 análises da mesma URL (mockando timestamps), validar chart + comparador + reanalisar | 0.5 dia |
| **Total** | | **~2 dias** |

## 6. Critério de pronto

- [ ] `POST /reanalisar/{id}` validado em ambiente local + tem teste cobrindo regressão Bug #3
- [ ] `GET /comparacao/{id}` retorna 404 quando não há análise anterior
- [ ] `GET /comparacao/{id}` retorna struct esperada quando há análise anterior
- [ ] Componente `CwvComparador` renderiza no dashboard URL quando `historico.length >= 2`
- [ ] `EvolucaoChart` renderiza com dados reais (validado com 2+ análises da mesma URL)
- [ ] Click em "Re-analisar" no dashboard abre dialog, confirma, e dispara nova execução
- [ ] Teste e2e manual: análise inicial → re-analise → nova análise → dashboard mostra chart + comparador
- [ ] Capturas de tela do antes/depois adicionadas neste PR

## 7. Não-objetivos

- Comparação entre N análises (só par mais recente — UI ficaria poluída com mais)
- Comparativo entre URLs diferentes (out of scope V1)
- Anotações do usuário ("explicar por que score melhorou")
- Comparativo cliente vs benchmark setorial
