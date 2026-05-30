# SPEC 08 — UI / Visual (design visual, contraste, marca)

**Status:** §3.1 e §3.2 **IMPLEMENTADOS** (2026-05-29, direção A) · restante a aplicar · **Escopo:** frontend (CSS/tema/visual) · **Severidade:** 🔴 Alta (tinha bug verificado) · **Esforço restante:** ~2h
**Índice:** [Auditoria UX 2026-05](README.md)

> **Decisão de marca:** usuário escolheu **(A) manter a sobriedade** — sem cor de acento.
>
> **Implementado nesta sessão (`src/app/globals.css`):**
> - §3.1 — utilitários corrigidos para CSS válido (`rgb(... / %)`). Validado por `getComputedStyle`: `.glass-card` agora `background: rgba(255,255,255,.8)` + borda 1px (antes transparente/0px); `.glow-md` com `box-shadow` real; `.bg-dot-pattern` renderiza. **Caveat:** `backdrop-filter: blur` ainda computa `none` (provável precedência do Tailwind v4 em `@layer utilities`) — impacto mínimo (o blur quase não aparece sobre fundo branco); o fundo translúcido + borda, que eram o bug, funcionam. Item menor de follow-up.
> - §3.2 — `.gradient-bg` aprofundado para `#7A6F63 → #5C5249` (brand-dark → brand-deep, **sem acento**). Contraste do texto branco no CTA medido no app: **4,90:1 e 7,61:1** (passa WCAG AA; antes 2,88:1). Cobre CTAs, chips de ícone e item ativo da sidebar de uma vez.
>
> **Pendente (não implementado):** §3.3 (paleta de data-viz), §3.4 (`dark:` morto), §3.5 (caixa-alta/legibilidade) — são mudanças maiores/opcionais.

> Adendo à auditoria: as SPECs 01–07 cobriram **UX** (fluxo/IA/conteúdo/a11y) e **consistência de UI**. Esta SPEC cobre o que faltava: **design visual** — hierarquia, **cor/contraste**, aplicação da marca, data-viz e efeitos. Achados fundamentados em `src/app/globals.css` + estilos computados no app rodando.

## 1. Problema

### 1.1 🔴 Utilitários visuais "assinatura" estão QUEBRADOS (verificado)
`globals.css` usa a sintaxe `#HEX / NN%` (válida no Tailwind v4, **inválida em CSS puro**) dentro de declarações cruas em `@layer utilities`. O navegador **descarta a declaração inteira**. Verificado via `getComputedStyle` no app em execução:

| Utilitário | Esperado | Computado real | Uso |
|---|---|---|---|
| `.glass-card` (`:135,138`) | branco translúcido + borda + blur | `background: rgba(0,0,0,0)`, `border: 0px`, `backdrop-filter: none` | **13 arquivos** (moldura principal) |
| `.glow-sm`/`.glow-md` (`:160,164`) | sombra suave (glow) | `box-shadow: none` | botões/logo |
| `.bg-dot-pattern` (`:168`) | fundo pontilhado | `background-image: none` | login/cadastro |
| `@keyframes pulse-glow` (`:228-229`) | pulsar do glow | inválido | — |

Ou seja: o "glass card" — moldura visual central do produto — é hoje uma **caixa transparente, sem borda e sem blur**; só parece um card por causa de outras classes (`rounded-2xl`, `p-…`, e em alguns lugares um `border` Tailwind explícito). O visual entrega **menos** do que foi desenhado.

### 1.2 🟡 Contraste do CTA primário abaixo do WCAG
A marca é toda taupe de baixo croma. O CTA primário usa `.gradient-bg` = `linear-gradient(135deg, #A3968D, #7A6F63)` com **texto branco**:
- Branco sobre **#A3968D** ≈ **2,9:1** → reprova WCAG AA para texto normal (4,5:1) **e** para texto grande (3:1).
- Branco sobre **#7A6F63** ≈ 4,9:1 (passa AA).
- Logo, a **metade clara de todo botão primário** fica abaixo do mínimo de contraste. Some-se o baixo croma geral: o CTA tem **valor tonal parecido com os neutros ao redor** → não "salta" (fraco affordance de ação para leigo).
- `text-muted-foreground` (#6B6259/branco ≈ 6,0:1) e `text-brand-dark` (#7A6F63/branco ≈ 4,9:1) **passam** — o problema é texto branco sobre o tom claro da marca.

### 1.3 🟡 Paleta de gráfico monocromática
`--chart-1..5` são todos tons de taupe (`#A3968D, #B8AFA0, #D0C5BA, #E8DDCF, #F8F6F3`). Em gráficos multi-série (evolução CWV) as linhas ficam **indistinguíveis**. Sintoma concreto: o painel de evolução (`cwv-evolucao-chart.tsx`) precisou **hardcodar verde/vermelho** nos sparklines porque os tokens de chart não diferenciam.

### 1.4 🟡 `dark:` morto / sem dark mode
Há `@custom-variant dark` e classes `dark:*` espalhadas (ex.: `cwv-dashboard-client.tsx`), mas **não existe** toggle nem tokens de tema escuro definidos no `:root.dark`. As classes `dark:` são **código morto** (nunca ativam) — falso affordance e ruído.

### 1.5 🟡 Legibilidade/hierarquia para leigo
- Uso pervasivo de rótulos `text-xs uppercase tracking-wider` para títulos de seção. Estiloso, mas **caixa-alta reduz velocidade de leitura** e pode parecer "etiqueta de formulário" — ruim para público não técnico/idoso.
- Densidade alta no dashboard CWV (página muito longa) — soma com [[SPEC_02_Error_Empty_Loading_Boundaries]]/divulgação progressiva.

## 2. Objetivos
1. **Consertar** os utilitários visuais quebrados (impacto imediato no acabamento).
2. **Atingir contraste WCAG AA** nas ações primárias mantendo a identidade.
3. **Paleta de data-viz** com séries distinguíveis.
4. Resolver `dark:` (implementar ou remover).
5. Melhorar hierarquia/legibilidade sem redesenho.

## 3. Mudanças propostas

### 3.1 Corrigir sintaxe CSS dos utilitários (P0)
Reescrever em CSS válido (`rgb(... / NN%)`, `rgba()` ou `color-mix`). Exemplos:
```css
.glass-card {
  background: rgb(255 255 255 / 80%);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgb(232 226 221 / 50%);
}
.glow-md { box-shadow: 0 0 30px -5px rgb(163 150 141 / 25%); }
.bg-dot-pattern { background-image: radial-gradient(rgb(163 150 141 / 15%) 1px, transparent 1px); background-size: 24px 24px; }
```
Aplicar o mesmo a `glow-sm`, `pulse-glow`. **Validar com `getComputedStyle`** que `background`/`box-shadow`/`background-image` deixam de ser `none`.

### 3.2 Contraste do CTA primário (P0 a11y)
- Opção recomendada: `.gradient-bg` passar a usar tons mais escuros (ex.: `linear-gradient(135deg, #7A6F63, #5C5249)`) → branco sobre ambos ≥ 4,5:1, e o botão ganha presença. Manter `#A3968D` como cor de marca para acentos/realces (não como fundo de texto branco).
- Garantir que badges/realces com texto branco usem `brand-dark`/`brand-deep`, não `brand`.
- **Decisão de marca (ver §5):** se o cliente quer manter o taupe claro como cor de ação, então o texto do botão deve ser escuro (`brand-deep`) em vez de branco.

### 3.3 Paleta de data-viz distinguível
- Redefinir `--chart-1..5` (ou um set dedicado de viz) com **matizes distintos porém on-brand** (ex.: taupe + um verde/azul/âmbar dessaturados) para séries separáveis.
- Padronizar semântica de melhora/piora (verde/vermelho atuais dos sparklines viram tokens, ex.: `--viz-positivo`, `--viz-negativo`).

### 3.4 Dark mode: decidir
- **Implementar** (definir `:root.dark` com os tokens invertidos + toggle no Perfil/sidebar) **ou remover** as classes `dark:*` (limpeza). Recomendado nesta fase: **remover** (evita código morto; dark mode vira backlog próprio).

### 3.5 Hierarquia/legibilidade
- Reduzir caixa-alta: usar `text-sm font-semibold` (case normal) para títulos de seção em vez de `text-xs uppercase tracking-wider` nos pontos de leitura (manter uppercase só em micro-rótulos realmente curtos).
- Garantir foco visível consistente (o `--ring` #A3968D tem contraste fraco sobre branco — considerar `--ring` mais escuro para foco perceptível; casa com [[SPEC_06_Acessibilidade_Base]]).

## 4. Critérios de aceite
- [ ] `getComputedStyle('.glass-card')` retorna `background` translúcido (não `rgba(0,0,0,0)`), `border` 1px e `backdrop-filter: blur`. Idem glow/dot-pattern não-`none`.
- [ ] Lighthouse "Accessibility" sem falhas de **contrast** nas telas principais; CTA primário ≥ 4,5:1.
- [ ] Gráfico de evolução CWV com múltiplas séries visualmente distinguíveis sem cores hardcoded ad hoc.
- [ ] Sem classes `dark:*` órfãs (ou dark mode funcional com toggle).
- [ ] `npm run build` e `tsc --noEmit` limpos.

## 5. Decisão em aberto (marca) — precisa do usuário
A identidade atual é **propositalmente muito sóbria** (taupe de baixo croma). Há duas direções para o contraste/energia da UI:
- **(A) Manter a sobriedade**: corrigir só o contraste (texto escuro nos CTAs claros) e os bugs — visual continua minimalista/elegante.
- **(B) Dar mais presença**: escurecer os CTAs (branco sobre taupe escuro) e introduzir **uma cor de acento** para ações/realces e data-viz, mantendo o taupe como base.

A §3.2/§3.3 assume **(B)** como recomendação (melhor para CTA "saltar" e gráficos legíveis), mas é uma escolha de design do produto.

**→ DECIDIDO: (A).** Implementação seguiu a direção A — sem cor de acento. Para resolver o contraste mantendo a sobriedade, o CTA foi aprofundado **dentro da própria marca taupe** (brand-dark → brand-deep) em vez de adicionar um acento, e o texto branco foi mantido (passa AA). Caso no futuro se queira o caminho literal "CTA claro + texto escuro", basta clarear `.gradient-bg` e trocar o texto dos botões para `text-foreground`.

## 6. Verificação E2E
Após corrigir: `getComputedStyle` dos utilitários (provar que renderizam); `mcp__chrome-devtools__lighthouse_audit` (accessibility/contrast) no hub, Gerar Artigo e dashboard CWV; screenshots antes/depois das telas principais para comparar acabamento.

## 7. Notas
- §3.1 (utilitários quebrados) é **bug objetivo** e deve entrar mesmo que a direção de marca (§5) fique pendente.
- Relacionado: [[SPEC_06_Acessibilidade_Base]] (contraste/foco), [[SPEC_05_Design_System_Consistencia]] (tokens), `cwv-evolucao-chart.tsx` (cores de viz).
