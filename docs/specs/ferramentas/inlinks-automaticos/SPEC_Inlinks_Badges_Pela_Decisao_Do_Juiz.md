# SPEC — Inlinks: badges de conexão derivadas da decisão do juiz (não do cosine)

**Status:** ✅ implementada (2026-07-03) — `injector._categoria_match_por_decisao()`; sem
confiança registrada a badge cai para `complemento_contextual` (pede revisão, nunca assume "forte")
**Escopo:** backend (`inseridor.py`, `injector.py`) + frontend (`inlinks-resultado.tsx`,
`distribuir-inlinks-resultado.tsx`, `types/ferramenta.ts`)
**Crédito:** não muda
**Depende de:** [SPEC_Inlinks_Julgamento_Unico](SPEC_Inlinks_Julgamento_Unico.md) aplicada

---

## Contexto

As badges da UI ("Conexão forte", "Conexão sólida", "Conexão indireta · revise", "Conexão
fraca · revise") vêm de `categoria_match`, calculada em `injector._categoria_match()` a partir
de **cortes de cosine/score** (0.8/0.65/0.7/0.55) — a filosofia antiga vazando na interface.
Resultado incoerente observado no E2E: link aplicado pelo juiz com confiança 0.8 e justificativa
sólida exibido como "Conexão indireta · revise", porque o cosine ficou na faixa errada. O usuário
compara a badge com o resultado e não entende — exatamente o tipo de ruído que a correção
eliminou do backend mas ficou na UI.

Quem decidiu a qualidade foi o juiz; a badge deve refletir a decisão e a confiança dele.
O cosine continua disponível como detalhe secundário (`sinal_cos_*`, "sem N").

## Mudanças

### 1. Backend — `categoria_match` derivada de (status, confiança)

Em `inseridor.py`, nova função substitui `_categoria_match` nos itens julgados:

| Situação | categoria_match |
|---|---|
| aplicado, confiança ≥ 0.85 | `alta_similaridade` ("Conexão forte") |
| aplicado, 0.70 ≤ confiança < 0.85 | `boa_similaridade` ("Conexão sólida") |
| aplicado, confiança < 0.70 (ou None) | `complemento_contextual` ("Confirme se agrega") |
| sugestao_manual | `similaridade_media` (a badge própria "Sugestão manual" domina) |
| rejeitado | `similaridade_media` |

- Itens de CTA fallback: `boa_similaridade` (link deliberado, não inferido).
- `injector._categoria_match` permanece para execuções antigas (dados persistidos não mudam)
  e para o caminho legado (`aplicar_pisos_legado=True`).

### 2. Frontend — copy das badges sem jargão de score

`CATEGORIA_INFO` em `inlinks-resultado.tsx` (e labels equivalentes no Distribuir):
- descrições passam a falar da **decisão da IA** ("A IA aplicou com alta confiança: tema do
  destino casa direto com o trecho"), não de "score"/"similaridade";
- "Conexão indireta · revise" vira "Aplicado com ressalva · revise" (é um link APLICADO com
  confiança menor — o texto atual sugere que não deveria estar lá);
- o número de cosine ("sem N") vira tooltip/detalhe, não protagonista.

## Verificação

- Unit: mapeamento (status, confiança) → categoria para os 5 casos da tabela + CTA + legado.
- E2E manual: execução do Receber → badges coerentes com confiança exibida ("IA 90%" nunca ao
  lado de "Conexão fraca").
- Execução antiga (pré-spec) continua renderizando com as badges gravadas.

## Riscos

- **Mistura de eras no histórico**: execuções antigas têm categoria por cosine, novas por
  confiança — aceitável (badges são orientativas), documentado aqui.
- Thresholds de confiança (0.85/0.70) são chute inicial — calibrar com o golden set (imprimir
  a distribuição de confiança no relatório do eval antes de fixar).
