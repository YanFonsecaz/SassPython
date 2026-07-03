# Créditos e Billing

**Estado:** ✅ implementado
**Código:** `backend/app/services/credito_service.py` (reserva/confirma/refund), `ferramenta_service.py`
(custos), `billing_service.py` (planos/pacotes) · `models/conta_credito.py`, `transacao_credito.py`,
`plano.py`, `pacote_credito.py`, `compra.py` · `routers/creditos.py`, `billing.py`

Saldo **global de créditos** unifica o consumo de todas as ferramentas (não há limite por ferramenta).
Conceito de produto, planos e regras: [`core/PRD.md`](../../../core/PRD.md) §Sistema de Créditos.

## Modelo de cobrança real (no código)

Os custos **não são mais fixos** como na tabela antiga do PRD: cada ferramenta tem **base + variável +
teto**, calculado em `ferramenta_service.calcular_custo_*`. Fonte da verdade:

| Ferramenta | Fórmula | Teto |
|---|---|---|
| Gerar Artigo | `15 + (versão−1)·3 + (imagem? 5)` | — (máx. estimado p/ reserva) |
| Inlinks Automáticos | `15 + 1·N_urls` | 60 |
| Distribuir Inlinks | `15 + 1·N_candidatas` | 115 |
| Core Web Vitals | `15 + 1·N_urls` (reserva `N·2`: mobile+desktop) | 100 |
| Parecer Técnico | `10 + 3·N_imagens` | 90 |

## Ciclo de vida do débito (reserva → confirma/refund)

Como as ferramentas são **assíncronas e variáveis**, o fluxo não é "debitar no fim", e sim:

```
router: reserva o custo MÁXIMO estimado  → saldo_reservado += reserva
workflow conclui:  confirma (debita o custo REAL, libera a diferença)   → débito real, reservado -= reserva
workflow falha:    refund (libera a reserva inteira)                     → reservado -= reserva, sem débito
```

Regra de ouro (motivo das specs de billing por ferramenta): **reserva = liberação = `reservado=`** no
débito, com **fonte única** `ferramenta_service._obter_reserva_estimada(ferramenta, execucao)`. Quando
isso é violado, créditos ficam "presos" em `saldo_reservado` — classe de bug corrigida em todas as
ferramentas (ver specs de billing). Débito consome `saldo_plano` antes de `saldo_extras`; ação que falha
não cobra.

## Specs de billing por ferramenta (correções aplicadas)

| Ferramenta | Spec | Commit |
|---|---|---|
| Core Web Vitals | [../../ferramentas/core-web-vitals/SPEC_Billing_CWV.md](../../ferramentas/core-web-vitals/SPEC_Billing_CWV.md) | `e50a3e6` |
| Inlinks Automáticos | [../../ferramentas/inlinks-automaticos/SPEC_Billing_Inlinks.md](../../ferramentas/inlinks-automaticos/SPEC_Billing_Inlinks.md) | `0cbe741` |
| Gerar Artigo | [../../ferramentas/gerar-artigo/SPEC_Billing_Gerar_Artigo.md](../../ferramentas/gerar-artigo/SPEC_Billing_Gerar_Artigo.md) | `ddbeb88` |

> A auditoria [2026-05-16 SPEC_03 — Créditos transacional](../../auditorias/2026-05-16-codebase/SPEC_03_Creditos_Transacional.md)
> 🗄️ estabeleceu a base transacional (race over-spend) sobre a qual essas correções foram feitas.
