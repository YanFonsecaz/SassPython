# SPEC — Distribuir: viabilidade decidida pelo juiz (piso de ruído no lugar do threshold)

**Status:** ✅ implementada (2026-07-03) — golden set +2 casos (`distribuir_sinonimo_baixo_cosine`,
`distribuir_tema_alheio_anti_forcagem`); gate integral PASSOU (4/4 deve_aplicar, 0 violações)
**Escopo:** backend (`workflow_inlinks_reversos.py`, `config.py`) + golden set
**Crédito:** não muda a fórmula (15 + 1·candidata); ver §Riscos sobre custo de LLM
**Depende de:** [SPEC_Inlinks_Julgamento_Unico](../inlinks-automaticos/SPEC_Inlinks_Julgamento_Unico.md) aplicada

---

## Contexto

O Receber já segue a filosofia "cosine não decide": piso de ruído 0.25 e o LLM juiz decide.
O Distribuir ainda tem o portão antigo no upstream: `node_filtrar_similaridade` descarta
candidatas com `cosine < threshold_efetivo` (0.6, ou relaxado no slug_only) **antes** de o juiz
vê-las. Os overrides (slug_only, keyword literal) compensam nos casos testados, mas a classe de
erro que motivou a correção do Receber existe aqui igual: candidata legítima com sinônimo de
domínio e cosine baixo (o padrão "dropshipping × loja virtual", cosine real 0.26) morre no filtro
sem nunca ser julgada — e aparece como "Sem relação suficiente", que é falso.

Assimetria também confunde manutenção: dois pipelines irmãos com regras de corte diferentes.

## Mudanças

### 1. `node_filtrar_similaridade` → piso de ruído + sinais

- Corte único: `score_semantico >= 0.25` (mesma constante/racional do Receber — extrair
  `PISO_RUIDO_SEMANTICO` para módulo compartilhado, ex. `app/agents/inlinks/constantes.py`).
- `threshold_score` do usuário vira **informativo** (gravado no funil, como no Receber).
- Mantidos como estão: modo `slug_only` (o pseudo-alvo pelo slug é o que dá um embedding
  representativo para alvos sem texto — continua necessário) e a detecção de boilerplate.
- `_candidata_tem_keyword_alvo` deixa de promover candidata (override) e vira **sinal registrado**
  (`sinal_keyword_alvo: bool`) — o juiz recebe a informação no prompt ("a candidata contém
  literalmente termos do slug do alvo") e decide.
- Candidatas abaixo do piso: `sem_match` com motivo "tema claramente distinto (cos=X.XX)".

### 2. Teto de julgamentos (proteção de custo)

Novo setting `distribuir_max_julgamentos: int = 30`: acima do piso, apenas as top-N por cosine
vão ao juiz; excedentes viram `sem_match` com motivo "fora do top-N por similaridade — aumente a
prioridade dividindo em execuções menores". Hoje o teto de candidatas já é 100; sem o filtro de
threshold, o juiz poderia receber todas — o teto limita o pior caso.

### 3. Rollback

Reusar o flag existente: `inlinks_pisos_legado_distribuir=True` passa a reativar **também** o
filtro por threshold no upstream (documentar no `.env.example`). Um flag, comportamento legado
completo.

### 4. Golden set

Adicionar 2 casos rotulados ao harness: (a) candidata com sinônimo de domínio e cosine < 0.6
que **deve aplicar** (análogo distribuído do dropshipping); (b) candidata de tema alheio acima
de 0.25 que **não deve linkar** (anti-forçagem no fluxo reverso). Gate de merge integral antes
do deploy.

## Verificação

- Unit: piso substitui threshold; keyword vira sinal (não promove); teto de julgamentos corta
  no top-N; flag legado restaura threshold.
- `python -m scripts.eval_inlinks --llm real` com os casos novos → PASSOU.
- E2E manual: caso Calcitran (3/3 hoje) permanece 3/3; caso com candidata sinônimo-baixo-cosine
  passa a aplicar.

## Riscos

- **Custo de LLM sobe** onde o threshold antes poupava chamadas: no pior caso (100 candidatas
  todas acima do piso) eram ~40 julgamentos a mais que hoje — o teto de 30 limita; créditos
  cobrados não mudam, então a margem por execução cai em execuções grandes. Monitorar.
- **Slug_only mais permissivo**: com keyword override virando sinal, candidatas que só passavam
  pelo override agora dependem do juiz — é o comportamento desejado, mas o caso (a) do golden
  set é obrigatório antes do merge.
