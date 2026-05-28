# SPEC — Correção dos tiles de métrica + Chart de evolução comparativo (antes × agora)

**Status:** a aplicar · **Escopo:** frontend (componentes `cwv-metricas-resumo.tsx` e `cwv-evolucao-chart.tsx`)
**Dependências:** [[SPEC_CWV_Reanalisar_Comparador_Chart]], [[SPEC_CWV_Dashboard_Historico]]
**Esforço estimado:** ~0,5 dia
**Origem:** E2E de 2026-05-27 sobre análise `https://thefirealarmsupplier.com/` (LCP 14,1 s · CLS 0,111 · INP 292 ms · TBT 1,0 s) — todas as métricas pintaram em vermelho/amarelo, mas o rótulo abaixo de cada tile dizia "bom" como se fosse o estado atual.

## 1. Problema

### 1.1 Bug nos tiles de métrica (CRÍTICO — confunde o usuário)

Em `frontend/src/components/cwv/cwv-metricas-resumo.tsx:86-88`:

```tsx
<p className="text-xs text-muted-foreground mt-0.5">
  {m.label === "CLS" ? "< 0.1 bom" : m.label === "LCP" ? "< 2.5s bom" : m.label === "INP" ? "< 200ms bom" : "< 200ms bom"}
</p>
```

Esse rótulo é **estático** — mostra sempre o *threshold de "bom"*, independente do valor medido. O usuário não-técnico lê "INP 292 ms · < 200 ms bom" e entende que o INP está bom, quando na verdade está **acima** do limite.

A função `metricColor` (linha 20-30) **já calcula a classificação corretamente** (success / yellow-500 / destructive) e a cor do número reflete isso — falta apenas materializar a classificação em texto claro.

### 1.2 Chart de evolução pouco informativo

Em `frontend/src/components/cwv/cwv-evolucao-chart.tsx`:

- 4 abas (Score / LCP / CLS / INP) obrigam o usuário a clicar para comparar métricas.
- Eixo X mostra só `dd/mm` repetido (no E2E apareceu "27/05 · 27/05"), sem hora — quando há ≥2 análises no mesmo dia, vira ruído.
- Não há **referência visual dos thresholds CWV** (linha de "bom" e "ruim"), então o usuário não sabe se o ponto está dentro do verde ou não.
- Não existe um modo "**antes × agora**" — comparar diretamente a primeira análise da URL com a última (caso de uso principal do produto: "melhorei depois de aplicar o plano de ação?").

## 2. Solução proposta

### 2.1 Tiles de métrica: classificação dinâmica + tooltip com thresholds

Substituir o rótulo estático por **classificação calculada** + chip colorido + tooltip nativo com os thresholds completos.

**Classificações (web.dev oficial):**

| Métrica | Bom        | Precisa melhorar | Ruim       |
|---------|------------|------------------|------------|
| LCP     | ≤ 2,5 s    | 2,5 s – 4,0 s    | > 4,0 s    |
| CLS     | ≤ 0,10     | 0,10 – 0,25      | > 0,25     |
| INP     | ≤ 200 ms   | 200 – 500 ms     | > 500 ms   |
| TBT     | ≤ 200 ms   | 200 – 600 ms     | > 600 ms   |

Renderização proposta de cada tile:

```
┌──────────────────┐
│       LCP        │
│      14,1 s      │   ← cor já existe (destructive)
│   ● Ruim         │   ← NOVO: chip com classificação calculada
│  (tooltip: bom ≤ 2,5 s · ruim > 4,0 s)
└──────────────────┘
```

**Implementação:**

1. Criar helper `classificarMetrica(value, good, poor, lowerIsBetter)` que retorna `'bom' | 'precisa-melhorar' | 'ruim' | null` (null quando `value === null`).
2. Mapear classificação → label PT-BR (`'Bom'`, `'Precisa melhorar'`, `'Ruim'`) e cor (reaproveitar `text-success` / `text-yellow-500` / `text-destructive` já usados).
3. Trocar o `<p>` da linha 86-88 por um chip `<span>` com bolinha colorida e o label.
4. Adicionar `title={...}` no tile com os thresholds completos da métrica (ex.: `LCP — bom ≤ 2,5s · precisa melhorar 2,5–4,0s · ruim > 4,0s`).
5. Quando `value === null`, manter o "—" atual e omitir o chip.

**Critério de aceitação:** repetir o E2E e confirmar que com LCP=14,1 s o chip exibe "Ruim" (vermelho), com CLS=0,111 exibe "Precisa melhorar" (amarelo), e nunca aparece "Bom" em métrica fora do threshold verde.

### 2.2 Chart de evolução: thresholds + modo "Antes × Agora"

**A. Bandas de referência (todas as abas exceto Score):**

Adicionar `<ReferenceArea>` do Recharts em duas faixas:

- Faixa verde (`y1=0`, `y2=good`): zona "Bom"
- Faixa amarela (`y1=good`, `y2=poor`): zona "Precisa melhorar"
- Acima de `poor`: implícito (área não pintada) representa "Ruim"

Aplicar opacidade baixa (~0.15) para não competir com a linha.

Para Score (lowerIsBetter=false): inverter — faixa verde no topo (90-100), amarela no meio (50-89).

**B. Eixo X: data + hora quando ≥2 no mesmo dia**

Em `frontend/src/components/cwv/cwv-evolucao-chart.tsx:33-39`, mudar a formatação para:

- Se houver ≥2 análises no mesmo dia no `historico`: `dd/mm HH:mm`.
- Caso contrário: `dd/mm` (comportamento atual).

Decidir antes de mapear: `const temColisao = new Set(historico.map(a => a.criado_em.slice(0,10))).size < historico.length;`.

**C. Modo "Antes × Agora" (toggle no topo do componente):**

Adicionar um toggle/switch acima das tabs:

```
[Linha do tempo] [Antes × Agora]
```

No modo "Antes × Agora" (default quando `historico.length >= 2`):

- Esconde o LineChart.
- Mostra um **comparativo lado a lado** das duas análises extremas (a mais antiga = "Antes"; a mais recente = "Agora").
- Para cada métrica (Score, LCP, CLS, INP, TBT):
  - Valor "Antes" com sua classificação (chip colorido)
  - Seta `→` central
  - Valor "Agora" com sua classificação
  - Delta calculado (reaproveitar `deltaLabel` que já existe em `cwv-metricas-resumo.tsx` — exportar)
  - Cor verde se melhorou, vermelha se piorou, cinza se ≈ igual

Layout sugerido (grid responsivo, 1 col mobile / 2 cols desktop):

```
┌─────────────────────────────────────────┐
│ Score                                   │
│  41 ●Ruim   →   33 ●Ruim    (-8 ▼)      │
├─────────────────────────────────────────┤
│ LCP                                     │
│  13,2s ●Ruim → 14,1s ●Ruim  (+0,9s ▼)   │
├─────────────────────────────────────────┤
│ CLS                                     │
│  0,111 ●Precisa melhorar → 0,111 ●...   │
│                                  (= )    │
└─────────────────────────────────────────┘
```

No modo "Linha do tempo" mantém o comportamento atual (com as faixas de referência da seção A) + eixo X melhorado (seção B).

**D. Cabeçalho do componente:**

Substituir o `Evolucao (N analises)` por algo mais descritivo:

```
Evolução  ·  primeira análise 26/05 14:33 → última 27/05 10:57  (3 análises)
```

## 3. Critérios de aceitação

1. **Bug dos tiles:** E2E sobre uma URL com métricas ruins (ex.: thefirealarmsupplier) mostra "Ruim"/"Precisa melhorar" no chip, nunca "Bom".
2. **Tooltip:** hover/foco no tile expõe os 3 thresholds da métrica em PT-BR.
3. **Bandas no chart:** abas LCP/CLS/INP/TBT exibem faixas verde/amarela; o usuário consegue ver visualmente se um ponto está em "Bom" sem precisar saber o número-limite.
4. **Modo Antes × Agora:** com ≥2 análises, é o modo default; mostra para cada métrica os dois chips (Antes/Agora) + delta colorido. Com apenas 1 análise, o componente continua exibindo a mensagem atual ("Faça outra análise…").
5. **Eixo X:** quando ≥2 análises no mesmo dia, mostra `dd/mm HH:mm`.
6. **Sem regressões:** testes Playwright existentes em `frontend/e2e/cwv-*` continuam passando; rodar `npm run test` no frontend.

## 4. Arquivos afetados

- `frontend/src/components/cwv/cwv-metricas-resumo.tsx` — adicionar `classificarMetrica`, refatorar tile, exportar `deltaLabel`.
- `frontend/src/components/cwv/cwv-evolucao-chart.tsx` — toggle, `ReferenceArea`, formatação X, componente de comparação Antes × Agora.
- (Opcional) extrair `classificarMetrica` e thresholds para `frontend/src/lib/cwv/thresholds.ts` para reuso entre os dois componentes e no `cwv-plano-acao.tsx`.

## 5. Fora de escopo

- Não alterar backend / payload da API.
- Não trocar biblioteca de chart.
- Não mudar a paleta global; usar as cores já definidas no design system.
- Modo "Antes × Agora" com 3+ análises (escolhendo quais comparar) — fica para iteração futura; por ora sempre compara primeira × última.
