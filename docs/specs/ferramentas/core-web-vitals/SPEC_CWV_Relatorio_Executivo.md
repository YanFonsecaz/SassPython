# SPEC — Relatório Executivo da auditoria (redator LLM + DOCX espelhando a planilha)

**Status:** 📋 planejado
**Capacidade:** `core-web-vitals`
**Escopo:** ambos — backend (agente redator, export, endpoints) e frontend (botões na auditoria)
**Código:** `backend/app/agents/cwv/redator.py` (novo), `backend/app/services/cwv_export.py`, `backend/app/routers/ferramentas_cwv_auditoria.py`, `backend/app/schemas/cwv_auditoria.py`, `backend/app/config.py`, `frontend/src/components/cwv/cwv-auditoria-client.tsx`, `frontend/src/lib/api/cwv.ts`  ·  **Rota:** `core-web-vitals/auditoria/[auditoriaId]`
**Créditos:** não cobra (decisão travada; custo LLM = 1 chamada por geração)
**Depende de:** `[[SPEC_CWV_Consolidador_Cross_URL]]` (consome consolidados), `[[SPEC_CWV_Export_Consolidado_Execucao]]` (reusa capítulos), `[[SPEC_CWV_Evidencias_Destacadas]]` (thresholds nas evidências)
**Referência:** `AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07.md` (gaps #8, #24); estrutura das abas visíveis da planilha NPBR

---

## 1. Contexto (por quê)

O produto final da planilha NPBR é um **documento de consultoria**: capa com objetivo/impactos, health score, checklist, e recomendações organizadas em prioridades — com narrativa para o dono do negócio E detalhe técnico para o dev. A ferramenta exporta dados; falta o documento. Esta spec cria o Redator (1 chamada LLM estruturada) e o export DOCX da auditoria completa, espelhando a organização da planilha e reutilizando toda a infra de export existente.

## 2. Requisitos / Critérios de aceite

- [ ] Dado auditoria com consolidação concluída, quando `POST /core-web-vitals/auditorias/{id}/relatorio`, então `cwv_auditoria.relatorio_json` é preenchido com `sumario_executivo_md`, `diagnostico_tecnico_md`, `plano_fases`, `gerado_em` e `modelo`.
- [ ] Dado que o LLM cita em `plano_fases` um `item_codigo` inexistente no checklist, então o código é removido do plano (fail-open) e um warning é logado — a geração NÃO falha.
- [ ] Dado auditoria com `consolidacao_status != 'concluida'`, quando `POST .../relatorio`, então 409.
- [ ] Dado relatório gerado, quando `GET /core-web-vitals/auditorias/{id}/docx`, então o DOCX contém as 8 seções na ordem (capa → sumário executivo → health/checklist → CrUX → page experience → plano consolidado → plano faseado → apêndices), com tabelas `<table data-causas>`.
- [ ] Dado `POST .../relatorio` repetido, então o relatório é regenerado (sobrescreve `relatorio_json`).
- [ ] Dado auditoria de outro usuário → 404 em ambos os endpoints.

## 3. Design (mapeado ao código)

### 3.1 Redator — `agents/cwv/redator.py` (novo)

Classe sobre `BaseAgent` com `invoke_structured` (padrão da casa). Settings novas em `config.py`: `cwv_redator_llm_model: str = "gpt-4.1"`, `cwv_redator_llm_temperature: float = 0.3` (texto para cliente — um pouco mais de fluidez que o analisador).

**Entrada (contexto compacto, pt-BR):** nome do cliente, health score before (e after se houver), assessments CrUX por URL (categoria por métrica), vereditos de page experience por origem, top 10 consolidados (título, causa raiz, escopo_descricao, severidade, esforço, savings agregados, metricas_afetadas, recomendacao_resumo) e a lista fechada de `item_codigo`+título do checklist (para o plano faseado referenciar). **Não enviar** `documentacao_md`, items brutos ou payloads.

**Saída estruturada:**

```python
class FaseOut(BaseModel):
    titulo: str                    # ex.: "Prioridade 1 — Quick wins de imagem"
    justificativa: str
    itens_codigos: list[str]       # item_codigo do checklist

class RelatorioOut(BaseModel):
    sumario_executivo_md: str      # 3-5 parágrafos, dono do negócio: o que foi achado, impacto no negócio, o que esperar
    diagnostico_tecnico_md: str    # para o dev: causas raiz, métricas afetadas, dependências entre correções
    plano_fases: list[FaseOut]     # 2-4 fases ordenadas por prioridade×esforço
```

**Validação (lista fechada, padrão do analisador):** filtrar de cada `FaseOut.itens_codigos` os códigos que não existem no checklist da auditoria; fases que ficarem vazias são removidas; se TODAS ficarem vazias, gerar plano determinístico de fallback (fases por esforço: quick wins = fails com esforço baixo; estruturais = médio; projetos = alto). O prompt deve instruir: pt-BR, não inventar dados, citar números reais fornecidos (health, savings), tom profissional de consultoria (referência de estilo: system prompt do documentador do Parecer, `agents/parecer/documentador.py::SYSTEM_DOC`).

Persistência: `relatorio_json = {"sumario_executivo_md", "diagnostico_tecnico_md", "plano_fases": [...], "gerado_em": iso, "modelo": settings.cwv_redator_llm_model}` (coluna já existe desde a migração 0026).

Execução **síncrona no endpoint** (1 chamada LLM, ~10-30s — dentro do timeout HTTP padrão? NÃO: usar o mesmo padrão 202+job se passar de ~20s. Decisão: **job arq** `executar_relatorio_cwv(ctx, auditoria_id)` registrado em `worker.py::functions`, com campo de status reutilizando `relatorio_json = {"status": "gerando"}` transitório → sobrescrito no fim; endpoint responde 202. Consistente com o consolidador e imune a timeout de request).

### 3.2 Export — `cwv_export.py::relatorio_auditoria_para_html`

```python
def relatorio_auditoria_para_html(
    auditoria: dict, checklist: list[dict], consolidados: list[dict],
    page_experience: list[dict], analises: list[dict], cliente_nome: str,
) -> str
```

Seções (na ordem, espelhando a planilha):
1. **Capa** — cliente, data, URLs auditadas, fase, health before/after (delta se after existir).
2. **Sumário executivo** — `_md_to_html(relatorio_json["sumario_executivo_md"])`.
3. **Health Score + Checklist** — tabela (`_html_table`): Item, Before, After, Implementação, Prioridade, Esforço — a "aba Checklist" da planilha.
4. **Dados de campo (CrUX)** — tabela por URL: LCP/INP/CLS p75 + categoria (campos `crux_*` das análises).
5. **Page Experience** — tabela por origem com os 7 vereditos.
6. **Plano de ação consolidado** — 1 capítulo por consolidado: título, causa raiz, escopo, evidências (via helper de evidências com threshold da S4), recomendação (`recomendacao_md`), e "Como corrigir" (buscar `documentacao_md` de um problema representativo do grupo — o primeiro de `problemas_origem_ids`).
7. **Plano faseado** — por fase: título, justificativa, tabela dos itens (título + esforço + status de implementação).
8. **Diagnóstico técnico + Apêndices** — `diagnostico_tecnico_md`; apêndice por URL reutilizando `_capitulo_problemas` da `[[SPEC_CWV_Export_Consolidado_Execucao]]` (top 15).

Endpoint `GET /core-web-vitals/auditorias/{auditoria_id}/docx`: ownership 404; relatório ausente → gera o DOCX **sem** as seções 2/7/8-narrativa (documento ainda útil); mesmo padrão `asyncio.to_thread(html_para_docx_bytes, ...)` + `StreamingResponse` + rate limit `cwv_export`.

### 3.3 Frontend

`cwv-auditoria-client.tsx`: botões "Gerar relatório" (POST 202 + polling do GET da auditoria até `relatorio_json.sumario_executivo_md` existir) e "Baixar DOCX"; preview do sumário executivo renderizado (markdown) na própria página.

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Execução | Job arq 202 (padrão consolidador) | Síncrono no request (risco de timeout HTTP e worker bloqueado) |
| Validação do plano | Lista fechada de item_codigo + fallback determinístico por esforço | Confiar no LLM (códigos inventados quebrariam a UI) |
| Modelo | `gpt-4.1` temp 0.3 (texto longo para cliente) | gpt-4o-mini (qualidade de prosa é o produto aqui) |
| DOCX sem relatório | Exporta seções de dados mesmo assim | Bloquear export até gerar (dado estruturado já tem valor) |

## 5. Verificação

```bash
cd backend && .venv/bin/pytest tests/unit/test_cwv_redator.py tests/unit/test_cwv_export_auditoria.py -q
```

Novo `tests/unit/test_cwv_redator.py` (mock de `invoke_structured`):
1. Saída válida → `relatorio_json` completo com `gerado_em`/`modelo`.
2. `itens_codigos` com código inexistente → filtrado; fase esvaziada → removida.
3. Todas as fases inválidas → fallback determinístico por esforço (baixo/médio/alto).
4. Contexto enviado ao LLM não contém `documentacao_md` (assert no prompt capturado pelo mock).

Novo `tests/unit/test_cwv_export_auditoria.py` (HTML puro com fixtures dict):
1. 8 seções presentes na ordem (assert na sequência dos `<h1>/<h2>`).
2. Sem `relatorio_json` → seções 2/7 ausentes, demais presentes.
3. Tabelas via `<table data-causas>`; snapshot básico do HTML dado fixture fixa (regressão de estrutura).

E2E manual: gerar relatório numa auditoria real e abrir o DOCX no Word/Docs.

## 6. Não-objetivos

- Editar o relatório na UI (regenerar substitui) — edição rica fica com o padrão do Parecer se houver demanda.
- Export Google Sheets no layout exato da planilha — roadmap V3.
- Gráficos/imagens embutidos no DOCX.

## 7. Avisos ao implementador

1. **Registrar `executar_relatorio_cwv` em `worker.py::functions`.**
2. Tabelas SEMPRE via `_html_table` (`<table data-causas>`) — markdown solto é descartado por `html_para_docx_bytes`.
3. Padrão LLM da casa: `invoke_structured`, validação em lista fechada, fail-open, prompts pt-BR; settings de modelo/temp em `config.py`.
4. Ownership 404; rate limit `cwv_export` no endpoint de DOCX.
5. Reusar `_capitulo_problemas` (S3) e `threshold_do_audit` (S4) — não duplicar renderização de problemas/evidências.
6. `relatorio_json` transitório `{"status": "gerando"}` não pode vazar para o DOCX (checar chave `sumario_executivo_md` antes de renderizar seções narrativas).

## 8. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-13 | Spec criada (📋) | — |
