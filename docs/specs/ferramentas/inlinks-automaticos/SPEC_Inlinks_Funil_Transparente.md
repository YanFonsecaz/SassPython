# SPEC — Inlinks: funil transparente (contadores por etapa + motivos sempre visíveis)

**Status:** ✅ implementado
**Escopo:** backend (2 workflows) + frontend (tipos + strip compartilhado) — sem migration
**Crédito:** não muda
**Depende de:** [SPEC_Inlinks_Julgamento_Unico](SPEC_Inlinks_Julgamento_Unico.md)

---

## Contexto

Quando a execução termina com poucos links, o usuário não tem como saber **onde** cada candidata
parou (scrape? similaridade? juiz? densidade?). Os motivos individuais existem (`motivo_*`), mas não
há visão agregada — e o histórico de ~30 specs mostra que sem essa visibilidade cada ajuste de
threshold foi feito às cegas.

## Mudanças

### 1. Backend — chave `funil` no estado dos dois workflows

Cada nó mescla contadores em `estado["funil"]`; `node_persistir` consolida em
`resultado_json["funil"]`:

- `extrair_candidatos/candidatas`: `n_solicitadas`, `n_scrape_ok`, `n_scrape_falhas`, `urls_falhas[]`.
- `match_rerank` (Receber): `n_pos_cosine_top15`, `n_pos_piso_ruido`, `threshold_informativo`.
- `filtrar_similaridade` (Distribuir): `n_viaveis`, `n_descartadas`, `n_falhas`.
- `inserir`/`inserir_em_cada`: `n_enviadas_juiz`, `n_decisao_aplicar/sugerir/descartar`,
  `n_colisoes_min_distance`, `n_retries_ok`.
- `revisar` (Receber): `n_rejeitados_revisor`.
- Consolidação inclui `motivos: {motivo_normalizado: contagem}` agregado dos itens.
- **Motivo nunca vazio**: fallback no persistir.

### 2. Backend — `etapa_atual` persistida

Helper (~6 linhas, sessão própria, espelhando `workflow_helpers._atualizar_etapa`) chamado nos
`node_start` dos dois workflows — a barra de progresso sobrevive a reload de página (complementa a
derivação por `nodeHistory` da [SPEC_Inlinks_UX_Verdade](SPEC_Inlinks_UX_Verdade.md)).

### 3. Frontend

- `types/ferramenta.ts`: interface `FunilInlinks` (`funil?` nos dois resultados).
- Novo `components/ferramentas/inlinks-funil-strip.tsx` (compartilhado): "12 raspadas → 10
  relacionadas → 6 avaliadas pela IA → 4 aplicadas · 1 sugestão · 1 descartada", com tooltip listando
  os motivos agregados.
- `inlinks-resultado.tsx` e `distribuir-inlinks-resultado.tsx` renderizam o strip; itens exibem
  `motivo_sugestao || motivo_rejeicao || motivo` (nunca em branco) e badge discreto de `confianca`.

## Verificação

- Unit `test_inlinks_funil.py`: contadores consolidados no `resultado_final` das duas ferramentas.
- E2E: execução com 10 candidatas (algumas com URL quebrada) mostra o strip com a conta fechando
  (solicitadas = ok + falhas; avaliadas = aplicar + sugerir + descartar).

## Riscos

- Tudo em `resultado_json` (JSONB) e dicts — zero migration; execuções antigas sem `funil` renderizam
  a UI sem o strip (campo opcional).
