# SPEC — Ciclo before/after + Health Score + comparativo

**Status:** 📋 planejado
**Capacidade:** `auditoria-seo-tecnico`
**Escopo:** ambos — `backend/app/services/seotec_score.py`, transições de fase em `routers/ferramentas_seo_tecnico.py` · frontend `components/seotec/comparativo.tsx`, gauges/gráficos
**Créditos:** re-crawl (fase after ou intermediário) = `15`
**Depende de:** [SPEC_Ferramenta_Auditoria_SEO_Tecnico](SPEC_Ferramenta_Auditoria_SEO_Tecnico.md)

---

## 1. Contexto (por quê)

O produto da planilha é o **antes/depois**: score % e gráficos que provam o valor do trabalho ao
cliente. A ferramenta replica o ciclo com fases explícitas — mesmo desenho do CWV
(`SPEC_CWV_Auditoria_Ciclo_De_Vida` + `SPEC_CWV_Reauditoria_After`).

## 2. Requisitos / Critérios de aceite

- [ ] Fases: `before` (1º crawl congela baseline + `score_antes`) → `implementacao` (edições de
      status_cliente/validacao_seo; re-crawls intermediários permitidos, não alteram baseline) →
      `after` (crawl final recalcula itens automáticos + `score_depois`) → `concluida` (somente
      leitura).
- [ ] Health Score = `Σ pesos dos itens Aprovado ou n/a ÷ 940 × 100`, calculado por fase — regra
      idêntica à planilha (colunas R/S sobre Q2). Itens `Sem dados` não pontuam e são listados à
      parte.
- [ ] Itens manuais: status marcado pelo usuário vale para a fase corrente; ao entrar em `after`, o
      status manual é re-perguntado (default: copia do before com aviso "revisar").
- [ ] Datas-limite sugeridas por prioridade a partir da data do crawl before: VH+5d · H+10d ·
      M+20d · L+45d (regra da coluna P da planilha).
- [ ] Comparativo: por item (status antes→depois, badge `melhorou`/`piorou`/`igual`/`novo`) e por
      categoria (score parcial). Gráficos por prioridade replicando os "Before/After NPA" da
      planilha (contagem Aprovado/Atenção/Reprovado por prioridade — regra da aba Control).
- [ ] Delta de evidências: para item ainda reprovado no after, mostrar variação de `total_afetadas`
      (ex.: 120 → 8 páginas).

## 3. Design (mapeado ao código)

- `seo_auditoria.fase` + validação de transição no router (mesma máquina de estados do CWV).
- `seotec_score.calcular(auditoria_id, fase)` lê `seo_item_resultado` + pesos do YAML → grava
  `score_antes`/`score_depois`.
- Ingestão com `fase_destino=after` reroda motor + IA **apenas para os itens automáticos**; campos
  manuais e observações preservados.
- Front: gauge duplo (antes/depois), gráfico de barras por prioridade (recharts, reusa padrão
  `components/cwv/`), tabela comparativa com filtros (só mudanças / só reprovados restantes).

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Baseline | Congelada no 1º crawl; re-crawls intermediários não sobrescrevem | Baseline móvel (mata o comparativo) |
| Score de `Sem dados` | Não pontua (nem positivo nem negativo) + alerta | Contar como Reprovado (puniria export parcial) |
| Manuais no after | Copiar com flag "revisar" | Zerar (perderia trabalho) ou congelar (esconderia regressão) |

## 5. Verificação

```bash
rtk pytest backend/tests/unit/test_seotec_score.py        # fórmula 940 + fases + Sem dados
rtk pytest backend/tests/e2e/test_e2e_seotec.py::test_ciclo_before_after
```

## 6. Não-objetivos

Mais de um ciclo after por auditoria (nova auditoria resolve) · comparação entre auditorias de
domínios diferentes · export DOCX do comparativo (fase 2, reusará padrão `cwv_export`).

## 7. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-17 | Spec inicial | — |
