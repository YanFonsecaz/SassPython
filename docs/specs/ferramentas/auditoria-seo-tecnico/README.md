# Auditoria de SEO Técnico

**Estado:** 🚧 parcial (Onda 1 implementada — upload manual + motor parcial: 31 regras de 98 itens SF; restantes na Onda 1b) · **Rota:** `/ferramentas/auditoria-seo-tecnico` · **Slug:** `auditoria_seo_tecnico`
**Créditos (proposta):** `30` por auditoria (fase before) · `15` por re-crawl (fase after) — a definir em `calcular_custo_seo_tecnico()`
**Código (previsto):** `backend/app/agents/seotec/*` · `routers/ferramentas_seo_tecnico.py` · `services/seotec_*` · `models/seo_auditoria.py`, `seo_crawl.py`, `seo_item_resultado.py` · conector: repositório/pacote `sf-connector`

Digitaliza a planilha NPBR **"Auditoria de SEO Técnico" (Template Enterprise 2026)** — checklist de
~125 itens em 22 categorias com Health Score e comparativo antes/depois — usando o **Screaming Frog
do próprio usuário** como fonte de crawl (via **MCP nativo do SF v24**, stdio headless) e **agentes
IA** (LangGraph) para diagnóstico e recomendação por item. É a ferramenta-irmã do
[core-web-vitals](../core-web-vitals/README.md): mesma infra (worker ARQ, créditos
reserva/confirma/refund, SSE, KB YAML, ciclo de auditoria before/after).

Análise-base da planilha (85 abas, fórmulas, scoring):
[ANALISE_Planilha_NPBR_SEO_Tecnico_2026-07](ANALISE_Planilha_NPBR_SEO_Tecnico_2026-07.md).

## Como funciona (fluxo)

1. Usuário cria auditoria (cliente + domínio) → plataforma emite **código de pareamento**.
2. Na máquina do usuário, o **conector local** (`sf-connector pair` / `sf-connector run`) executa o
   Screaming Frog **headless** via MCP stdio (fallback CLI clássico), roda a **receita de exports**
   definida pelo backend, normaliza para JSON versionado e sobe via API. Fallback sem instalação:
   upload manual do mesmo pacote `.zip` na UI.
3. Worker processa: **motor de regras determinístico** (status por item + evidências) → **agentes
   IA** (diagnóstico + recomendação, KB curada + fallback LLM) → **health score** (fórmula da
   planilha, base 940 pontos).
4. UI: checklist por categoria (status/prioridade/responsável/prazo), Health Score com gráficos,
   detalhe por item (= aba oculta da planilha) com evidências paginadas e campos
   **Status cliente / Validação SEO**.
5. Itens de GSC/SERP/subjetivos ficam **manuais** (usuário marca status e escreve observação).
6. Ciclo: `before` → `implementacao` → `after` (re-crawl) → `concluida`, com comparativo por item e
   delta de score.

## Arquitetura (mapa → código previsto)

```
[sf-connector (máquina do usuário)]
  pair → run → SF v24 MCP stdio → exports → normaliza → upload chunks
        └─ fallback: SF CLI --headless --export-tabs / upload manual .zip
[backend]
  POST /ingestao → valida schema → seo_crawl
  worker ARQ: validar_pacote → motor_regras → analisar_ia → recomendar_ia → health_score → persistir
[frontend]
  painel auditorias · tela auditoria (score+checklist) · drawer item · comparativo · página conector
```

| Peça | Spec |
|---|---|
| Spec-mãe (workflow, tabelas, rotas, cobrança, front) | [SPEC_Ferramenta_Auditoria_SEO_Tecnico](SPEC_Ferramenta_Auditoria_SEO_Tecnico.md) |
| Conector local + MCP SF + contrato de ingestão | [SPEC_SEOTEC_Conector_Local_SF](SPEC_SEOTEC_Conector_Local_SF.md) |
| Seed do checklist (125 itens) + motor de regras | [SPEC_SEOTEC_Checklist_Motor_Regras](SPEC_SEOTEC_Checklist_Motor_Regras.md) |
| Agentes IA (diagnóstico/recomendação + KB) | [SPEC_SEOTEC_Agentes_IA](SPEC_SEOTEC_Agentes_IA.md) |
| Health score + ciclo before/after + comparativo | [SPEC_SEOTEC_Ciclo_Auditoria_Health_Score](SPEC_SEOTEC_Ciclo_Auditoria_Health_Score.md) |

## Decisões travadas (brainstorm 2026-07-17)

| Tema | Decisão | Descartado |
|---|---|---|
| Onde roda o SF | Máquina de **cada usuário** (licença própria), multi-tenant | SF no servidor (licença/infra JVM da empresa) |
| Ponte local→cloud | Conector CLI outbound-only + fallback upload manual do mesmo pacote | Túnel MCP vivo (broker WebSocket; análise dependeria da máquina online; before/after exige snapshot persistido de todo jeito) |
| Interface com o SF | MCP nativo v24 stdio headless; fallback CLI `--headless` p/ SF ≥16 | Exigir GUI aberto (HTTP mode); parsear `.seospider` proprietário |
| Escopo V1 | Itens SF automatizados + IA; GSC/SERP/subjetivos manuais | OAuth GSC na V1; "só SF puro" sem IA |
| Análise IA | Server-side sobre dados persistidos (chaves LLM do servidor) | LLM no conector |
| Evidências | Resumo + amostra limitada (≤500 URLs/item) no Postgres | Crawl inteiro no DB |
| Recomendação em massa | Padrão/template + até N exemplos por item | Gerar title/meta novo por URL (custo LLM explode) |

## Não-objetivos (V1)

OAuth Google Search Console (itens ficam manuais) · geração em massa de titles/metas por URL ·
túnel MCP vivo · editar pesos/itens do checklist pela UI (seed YAML no git) · export PDF ·
rodar Screaming Frog no servidor · suporte a SF free (500 URLs — funciona, mas sem garantia de
completude) · análise separada site vs. blog (colunas N/O da planilha viram um único status por item
na V1).

## Estado atual

Nenhum código. Specs escritas em 2026-07-17 a partir do design aprovado em sessão de brainstorming.
Próximo passo: plano de implementação (superpowers/writing-plans) e execução por ondas (ver ordem
sugerida na spec-mãe, §7).
