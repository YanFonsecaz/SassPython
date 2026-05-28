# SPEC — CWV UX: Empty State, Site Perfeito & Análise Rasa

**Status:** a aplicar · **Escopo:** frontend (UI/UX) + pequeno ajuste backend (metadata)
**Dependências:** [[SPEC_CWV_Dashboard_Historico]]
**Esforço estimado:** ~1 dia

## 1. Problema

No e2e de 2026-05-26, ao analisar `https://example.com/` (site Apache padrão da IETF, super-simples):

- Score: **100/100**
- Todas as métricas verdes (LCP 776ms, CLS 0, INP 16ms, TBT 0ms)
- Resultado: **"Nenhum problema identificado nessa analise. Continue monitorando e re-analisando periodicamente."**

Esse texto está tecnicamente correto, **mas é o mesmo texto que aparece para um site genuinamente bem otimizado**.

Não há diferenciação entre:

| Cenário | Hoje | Deveria ser |
|---|---|---|
| Site real com SEO perfeito (score 95+, real-world traffic) | "Nenhum problema identificado" | "✨ Site otimizado · Continue monitorando" |
| Site trivial (`example.com`, "Hello world", 1 linha de HTML) | "Nenhum problema identificado" | "ℹ Análise rasa · Esse site é simples demais para gerar diagnósticos úteis" |
| Site com poucos problemas (1-3, todos baixa severidade) | Lista 1-3 itens normal | Mesmo, mas adicionar contexto "Site quase pronto · pequenos ajustes" |
| Site com muitos problemas críticos | Lista N itens normal | Mesmo, mas adicionar resumo no topo "X críticos · começar por 1, 2, 3" |

Isso impacta a credibilidade do produto. Um cliente paga 16 créditos, analisa o site dele que é "Hello world" mockup, recebe "site perfeito" — e perde confiança na ferramenta.

## 2. Objetivos

1. **Diferenciar visualmente** os 4 estados acima
2. **Heurística de "análise rasa"**: páginas muito pequenas / com pouco conteúdo / com poucos audits totais
3. **Resumo executivo no topo** quando há muitos problemas
4. **Persistir metadata** da análise para suportar isso (ex: `n_audits_totais_lighthouse`)

## 3. Heurísticas

### 3.1 "Análise rasa" — sinais

PSI processou o site, mas o site tem pouco material:

```python
def is_analise_rasa(parsed: dict) -> bool:
    audits_totais = len(parsed.get("audits_falhos", [])) + parsed.get("audits_ok_count", 0)
    main_doc_size = parsed.get("main_document_size_bytes", 0)
    n_requests = parsed.get("n_network_requests", 0)
    
    # Critérios (qualquer um dispara):
    return (
        audits_totais < 30 or              # Lighthouse normalmente roda 50+ audits
        main_doc_size < 5000 or            # HTML <5KB = página muito simples
        n_requests < 5                     # <5 requests = sem CSS/JS/imagens
    )
```

### 3.2 Estados visuais

#### Estado A — "Análise rasa"
```
┌────────────────────────────────────────────────┐
│  ℹ️  Análise rasa                              │
│                                                 │
│  Este site é muito simples (HTML 2KB, 3        │
│  requisições) para gerarmos diagnóstico útil   │
│  de Core Web Vitals.                            │
│                                                 │
│  • Funciona como sanity check técnico          │
│  • Para análise real, use uma URL com         │
│    conteúdo de produção                        │
└────────────────────────────────────────────────┘
```

#### Estado B — "Site otimizado" (não rasa + 0 problemas)
```
┌────────────────────────────────────────────────┐
│       ✨                                       │
│       Site otimizado                          │
│                                                 │
│  Nenhum problema identificado nesta análise.   │
│  Suas métricas estão dentro dos thresholds     │
│  recomendados pelo Google.                     │
│                                                 │
│  💡 Re-analise em ~1 semana para garantir     │
│     que continua assim.                        │
└────────────────────────────────────────────────┘
```

#### Estado C — "Quase lá" (1-3 problemas, todos severidade ≤3)
```
┌────────────────────────────────────────────────┐
│   ⚡ Site quase pronto                         │
│                                                 │
│   3 ajustes pequenos podem subir seu score    │
│   de 88 para ~95.                              │
└────────────────────────────────────────────────┘
[ accordion abaixo: 3 itens normais ]
```

#### Estado D — "Muitos problemas" (>5 OU ≥2 críticos)
```
┌────────────────────────────────────────────────┐
│   🎯 Por onde começar                          │
│                                                 │
│   Encontramos 7 problemas (6 críticos).        │
│   Foque nestes 3 primeiro para maior impacto:  │
│                                                 │
│   1. Execução pesada de JS no carregamento    │
│      (afeta INP, TBT, LCP)                     │
│   2. Imagens sem dimensões                    │
│      (afeta LCP, CLS)                          │
│   3. Bundle JavaScript grande                  │
│      (afeta INP, TBT)                          │
└────────────────────────────────────────────────┘
[ accordion abaixo: 7 itens normais ]
```

## 4. Backend (mudanças pequenas)

### 4.1 `parse_psi` — extrair mais metadata

`app/services/cwv_psi_client.py`:

```python
def parse_psi(payload: dict) -> dict:
    lh = payload["lighthouseResult"]
    audits = lh.get("audits", {})
    categories = lh.get("categories", {})
    
    # ... código atual ...
    
    # NOVO: contagens e tamanhos para heurística de "análise rasa"
    audits_com_score = sum(1 for a in audits.values() if a.get("score") is not None)
    
    network_items = audits.get("network-requests", {}).get("details", {}).get("items", [])
    main_doc_bytes = 0
    for item in network_items:
        url = item.get("url", "")
        if url == lh.get("finalUrl") or url == lh.get("requestedUrl"):
            main_doc_bytes = item.get("transferSize", 0)
            break
    
    return {
        # ... campos atuais ...
        "audits_totais": audits_com_score,
        "n_network_requests": len(network_items),
        "main_document_size_bytes": main_doc_bytes,
    }
```

### 4.2 Persistência — novos campos opcionais em `cwv_analise`

Migration `0016_cwv_metadata_analise.py`:

```sql
ALTER TABLE cwv_analise
ADD COLUMN audits_totais INTEGER DEFAULT 0,
ADD COLUMN n_network_requests INTEGER DEFAULT 0,
ADD COLUMN main_document_size_bytes INTEGER DEFAULT 0;
```

Model `cwv_analise.py` adiciona as 3 colunas.

Em `cwv_persistencia.py:persistir_analise`, popular do `parsed`:

```python
audits_totais=parsed.get("audits_totais", 0),
n_network_requests=parsed.get("n_network_requests", 0),
main_document_size_bytes=parsed.get("main_document_size_bytes", 0),
```

### 4.3 Schemas — expor no `AnaliseResposta`

```python
class AnaliseResposta(BaseModel):
    ...
    audits_totais: int = 0
    n_network_requests: int = 0
    main_document_size_bytes: int = 0
```

## 5. Frontend

### 5.1 Novo helper de "estado da análise"

`frontend/src/lib/cwv-estado.ts`:

```ts
import type { CwvAnaliseResposta } from "@/lib/api/cwv";

export type EstadoAnalise =
  | { tipo: "rasa"; motivos: string[] }
  | { tipo: "otimizado" }
  | { tipo: "quase_pronto"; nProblemas: number; scoreEstimadoMelhora?: number }
  | { tipo: "muitos_problemas"; nProblemas: number; nCriticos: number; top3: string[] }
  | { tipo: "normal"; nProblemas: number }
  | { tipo: "falhou" };

export function classificarAnalise(analise: CwvAnaliseResposta): EstadoAnalise {
  if (analise.status !== "sucesso") return { tipo: "falhou" };

  const problemas = analise.problemas ?? [];
  const nProblemas = problemas.length;
  const nCriticos = problemas.filter((p) => p.severidade >= 4).length;

  // Análise rasa
  const motivos: string[] = [];
  if (analise.audits_totais > 0 && analise.audits_totais < 30) {
    motivos.push(`Lighthouse rodou apenas ${analise.audits_totais} audits`);
  }
  if (analise.main_document_size_bytes > 0 && analise.main_document_size_bytes < 5000) {
    motivos.push(`HTML muito pequeno (${(analise.main_document_size_bytes / 1024).toFixed(1)}KB)`);
  }
  if (analise.n_network_requests > 0 && analise.n_network_requests < 5) {
    motivos.push(`apenas ${analise.n_network_requests} requisições`);
  }
  if (motivos.length >= 1 && nProblemas === 0) {
    return { tipo: "rasa", motivos };
  }

  // Otimizado
  if (nProblemas === 0) return { tipo: "otimizado" };

  // Quase pronto: 1-3 problemas, todos severidade ≤3
  if (nProblemas <= 3 && nCriticos === 0) {
    return { tipo: "quase_pronto", nProblemas };
  }

  // Muitos problemas: >5 OU ≥2 críticos
  if (nProblemas > 5 || nCriticos >= 2) {
    return {
      tipo: "muitos_problemas",
      nProblemas,
      nCriticos,
      top3: problemas.slice(0, 3).map((p) => p.titulo),
    };
  }

  return { tipo: "normal", nProblemas };
}
```

### 5.2 Novo componente `CwvEstadoBanner`

`frontend/src/components/cwv/cwv-estado-banner.tsx`:

```tsx
import { InfoIcon, SparklesIcon, ZapIcon, TargetIcon, AlertTriangleIcon } from "lucide-react";
import type { EstadoAnalise } from "@/lib/cwv-estado";

interface Props {
  estado: EstadoAnalise;
  score: number | null;
}

export function CwvEstadoBanner({ estado, score }: Props) {
  if (estado.tipo === "normal" || estado.tipo === "falhou") return null;

  if (estado.tipo === "rasa") {
    return (
      <div className="rounded-xl border border-blue-200 bg-blue-50 dark:bg-blue-950/20 dark:border-blue-900 p-5">
        <div className="flex items-start gap-3">
          <InfoIcon className="size-5 text-blue-600 mt-0.5 shrink-0" />
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Análise rasa</h3>
            <p className="text-sm text-muted-foreground">
              Este site é muito simples para gerarmos diagnóstico útil de Core Web Vitals:
            </p>
            <ul className="text-sm text-muted-foreground space-y-0.5 pl-2">
              {estado.motivos.map((m, i) => <li key={i}>• {m}</li>)}
            </ul>
            <p className="text-xs text-muted-foreground pt-1">
              Use uma URL de página real (com conteúdo, imagens, JS) para análise significativa.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (estado.tipo === "otimizado") {
    return (
      <div className="rounded-xl border border-success/30 bg-success/5 p-5">
        <div className="flex items-start gap-3">
          <SparklesIcon className="size-5 text-success mt-0.5 shrink-0" />
          <div className="space-y-1">
            <h3 className="text-sm font-semibold">Site otimizado</h3>
            <p className="text-sm text-muted-foreground">
              Suas métricas estão dentro dos thresholds recomendados pelo Google. Continue monitorando.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (estado.tipo === "quase_pronto") {
    return (
      <div className="rounded-xl border border-yellow-200 bg-yellow-50 dark:bg-yellow-950/20 dark:border-yellow-900 p-5">
        <div className="flex items-start gap-3">
          <ZapIcon className="size-5 text-yellow-600 mt-0.5 shrink-0" />
          <div className="space-y-1">
            <h3 className="text-sm font-semibold">Site quase pronto</h3>
            <p className="text-sm text-muted-foreground">
              {estado.nProblemas} ajuste{estado.nProblemas !== 1 ? "s" : ""} pequeno{estado.nProblemas !== 1 ? "s" : ""}
              {" "}pode{estado.nProblemas !== 1 ? "m" : ""} subir seu score
              {score != null && ` de ${score}`} para ~95.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (estado.tipo === "muitos_problemas") {
    return (
      <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-5">
        <div className="flex items-start gap-3">
          <TargetIcon className="size-5 text-destructive mt-0.5 shrink-0" />
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Por onde começar</h3>
            <p className="text-sm text-muted-foreground">
              Encontramos {estado.nProblemas} problemas ({estado.nCriticos} críticos). Foque nestes 3 primeiro:
            </p>
            <ol className="text-sm space-y-1 pt-1 pl-4 list-decimal">
              {estado.top3.map((titulo) => <li key={titulo}>{titulo}</li>)}
            </ol>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
```

### 5.3 Integração no `cwv-dashboard-client.tsx`

```tsx
import { classificarAnalise } from "@/lib/cwv-estado";
import { CwvEstadoBanner } from "@/components/cwv/cwv-estado-banner";

...

const estado = useMemo(() => classificarAnalise(analiseAtual), [analiseAtual]);

return (
  <div className="space-y-6">
    {/* ... */}
    <MetricasResumo analiseAtual={analiseAtual} analiseAnterior={analiseAnterior} />
    
    <CwvEstadoBanner estado={estado} score={analiseAtual.score_performance} />
    
    {/* ... existing accordion ... */}
  </div>
);
```

### 5.4 Empty state também no histórico

Quando o cliente não tem nenhuma análise CWV ainda, o histórico mostra empty state. Validar texto:

```tsx
<EmptyState
  icon={GaugeIcon}
  title="Nenhuma análise ainda"
  description="Analise URLs do site do seu cliente para receber diagnóstico técnico e plano de ação."
  action={<Link href="/ferramentas/core-web-vitals" className={buttonVariants()}>Analisar primeira URL</Link>}
/>
```

(Provavelmente já está OK — confirmar.)

## 6. Plano de execução

| Fase | O que | Esforço |
|---|---|---|
| U1 | Backend: estender `parse_psi` + migration 0016 + persistência | 0.25 dia |
| U2 | Backend: schema `AnaliseResposta` com novos campos + teste | 0.1 dia |
| U3 | Frontend: helper `classificarAnalise` + componente `CwvEstadoBanner` | 0.4 dia |
| U4 | Frontend: integrar no dashboard + estilização tailwind | 0.25 dia |
| **Total** | | **~1 dia** |

## 7. Critério de pronto

- [ ] Migration 0016 aplicada
- [ ] `example.com` (site trivial) → banner "Análise rasa"
- [ ] Site bem otimizado real (ex: `web.dev` se passar pra 95+) → banner "Site otimizado"
- [ ] Site com 7 problemas (web.dev no e2e original) → banner "Por onde começar" com top 3
- [ ] Site com 2 problemas severidade ≤3 → banner "Site quase pronto"
- [ ] Site com 4-5 problemas mix → banner normal (sem banner)
- [ ] Helper `classificarAnalise` tem testes unitários cobrindo cada caminho
- [ ] Screenshots de cada estado adicionados ao PR

## 8. Não-objetivos

- Sugerir URL alternativa quando análise é rasa (V2)
- Plot de "score esperado se você corrigir top 3" (precisa modelo preditivo)
- Gamificação ("seu site subiu 2 níveis!")
- Compartilhar relatório por link (V2)
