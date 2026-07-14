# SPEC — Export DOCX consolidado da execução (todas as URLs)

**Status:** 📋 planejado
**Capacidade:** `core-web-vitals`
**Escopo:** ambos — backend (export + endpoint) e frontend (botão)
**Código:** `backend/app/services/cwv_export.py`, `backend/app/routers/ferramentas_cwv.py`, `frontend/src/components/cwv/cwv-execucao-client.tsx`, `frontend/src/lib/api/cwv.ts`  ·  **Rota:** `core-web-vitals`
**Créditos:** não cobra
**Depende de:** `[[SPEC_CWV_Health_Score]]` (health na capa; se ausente, capa omite o valor)
**Referência:** `AUDITORIA_Planilha_NPBR_vs_Ferramenta_2026-07.md` (gap #8)

---

## 1. Contexto (por quê)

A planilha NPBR é **um documento por cliente** cobrindo todas as URLs auditadas. A ferramenta só exporta DOCX por análise individual (`GET /core-web-vitals/analise/{id}/docx`) — o consultor precisaria baixar 2×N arquivos e juntá-los na mão. Esta spec cria o relatório consolidado da execução: capa, sumário comparativo e um capítulo por URL, reutilizando a infraestrutura de export existente.

## 2. Requisitos / Critérios de aceite

- [ ] Dado uma execução concluída com 3 URLs (6 análises), quando `GET /core-web-vitals/execucao/{id}/docx`, então o download é um DOCX com capa, tabela-sumário com 6 linhas e 3 capítulos (mobile+desktop agrupados por URL).
- [ ] Dado uma execução de outro usuário, quando o endpoint é chamado, então 404.
- [ ] Dado uma execução com 1 URL falhada no PSI, então a falha aparece num apêndice "URLs não analisadas" (URL + erro) e não quebra o documento.
- [ ] Dado uma URL com mais de 15 problemas, então o capítulo mostra os 15 primeiros por `prioridade_ordem` + linha "… e mais N problemas de menor prioridade (ver análise individual)".
- [ ] Dado um problema com mais de 10 recursos em evidência, então a tabela é truncada em 10 com contagem do restante.
- [ ] Dado mobile e desktop com o MESMO conjunto de problemas (mesmos `kb_codigo`/`audit_id`), então o capítulo documenta uma vez com a nota "Observação: os problemas ocorrem de forma idêntica em Desktop e Mobile" (padrão do Parecer Técnico).

## 3. Design (mapeado ao código)

### 3.1 Export — `cwv_export.py`

Nova função:

```python
def relatorio_execucao_para_html(
    execucao: dict,          # id, criado_em, resultado_json (health_score se houver)
    analises: list[dict],    # saída de buscar_analise_com_problemas por análise
    cliente_nome: str = "",
) -> str
```

Estrutura do HTML (mesmos helpers `_html_table`, `_severidade_label`, `_fmt_ms`, `_fmt_bytes`, `_md_to_html`):

1. **Capa** — `<h1>Auditoria Core Web Vitals — {cliente_nome}</h1>`, data, nº de URLs, health score % (se presente em `execucao["resultado_json"]["health_score"]`).
2. **Sumário comparativo** — `_html_table` com colunas: URL, Estratégia, Score, LCP, CLS, INP, Nº problemas, Nº críticos (severidade ≥ 4). Uma linha por análise de sucesso, ordenada por URL e estratégia.
3. **Capítulos por URL** (agrupar `analises` por `url_canonica`):
   - `<h2>` com a URL; metadados (template, plataforma).
   - Se mobile e desktop têm o mesmo conjunto de chaves de problema (mesma chave usada em `comparar_com_anterior`: `kb_codigo` > `audit:{audit_id}` > `titulo:{titulo}`): renderizar UMA lista de problemas + a nota de identidade (critério 6). Senão: subseções "Mobile" e "Desktop".
   - Problemas: reusar o corpo de `relatorio_para_html` (extrair helper interno `_capitulo_problemas(problemas, max_problemas=15, max_recursos=10)` para não duplicar código — refatorar `relatorio_para_html` para usá-lo também, mantendo seu comportamento atual com limites 50/None).
4. **Apêndice — URLs não analisadas**: análises `status != "sucesso"` com `erro_msg`.

### 3.2 Endpoint — `routers/ferramentas_cwv.py`

`GET /core-web-vitals/execucao/{execucao_id}/docx`:
- Ownership como em `buscar_execucao_cwv` (404).
- Carregar as análises via `CwvAnalise.execucao_id == execucao_id` + `cwv_persistencia.buscar_analise_com_problemas` por id (ou query direta + `buscar_problemas_analise`).
- Nome do cliente: `session.get(Cliente, execucao.cliente_id)` (pode ser None → string vazia).
- Mesmo padrão do export existente: `rate_limit_autenticado("cwv_export", max_requests=30, window_seconds=300)`, `asyncio.to_thread(html_para_docx_bytes, html)` (import de `app.services.parecer_service`), `StreamingResponse` com `Content-Disposition: attachment; filename="cwv-auditoria-{slug-cliente-ou-data}.docx"`.

### 3.3 Frontend

- `lib/api/cwv.ts`: `exportarExecucaoCwvDocx(execucaoId): Promise<Blob>` (via `api.blob`, espelhando `exportarRelatorioCwvDocx`).
- `cwv-execucao-client.tsx`: botão "Baixar relatório completo (.docx)" visível quando `status === "concluida"`, com estado de loading e `toast.error(mensagemErroAmigavel(e))` em falha (padrão do handler em `cwv-plano-acao.tsx`).

## 4. Decisões & alternativas

| Tema | Decisão | Alternativa descartada |
|---|---|---|
| Escopo do documento | Por **execução** | Por cliente/auditoria — chega na `[[SPEC_CWV_Relatorio_Executivo]]`; esta spec é o bloco de montagem |
| Tamanho | Cap top-15 problemas/capítulo e 10 recursos/tabela | Documento integral (50 URLs × 2 × 30 problemas ≈ inviável de ler e de abrir) |
| Dedup mobile/desktop | Nota de identidade quando conjuntos iguais | Sempre duplicar (documento 2× maior sem ganho) |

## 5. Verificação

```bash
cd backend && .venv/bin/pytest tests/unit/test_cwv_export_execucao.py tests/test_cwv_export.py -q
```

Novo `backend/tests/unit/test_cwv_export_execucao.py` (HTML puro, sem DB — fixtures dict):
1. 3 URLs → capa + sumário com 6 linhas + 3 `<h2>`.
2. Conjuntos idênticos mobile/desktop → nota de identidade presente e problemas renderizados 1×.
3. 20 problemas → 15 renderizados + linha "e mais 5".
4. Análise falhada → apêndice com a URL e `erro_msg`.
5. Tabelas geradas via `<table data-causas>` (assert substring) — nunca markdown.
6. `relatorio_para_html` existente continua com saída equivalente (regressão do refactor `_capitulo_problemas`).

Teste de rota: ownership 404; execução concluída → 200 com content-type DOCX.

## 6. Não-objetivos

- Sumário executivo narrado por LLM e plano faseado — `[[SPEC_CWV_Relatorio_Executivo]]`.
- PDF ou Google Sheets — roadmap V3.
- Gráficos embutidos no DOCX (tabela cobre o comparativo).

## 7. Avisos ao implementador

1. **Tabelas no DOCX**: `html_para_docx_bytes` (parser selectolax em `parecer_service.py`) descarta tabelas markdown soltas — SEMPRE gerar via `cwv_export._html_table` (`<table data-causas>`); ver comentário em `cwv_export.py`.
2. O refactor de `relatorio_para_html` → `_capitulo_problemas` não pode mudar a saída do export unitário existente (há teste em `tests/test_cwv_export.py`).
3. Ownership 404 (nunca 403); rate limit igual aos exports existentes.
4. `asyncio.to_thread` para a conversão DOCX (bloqueante) — padrão dos dois endpoints de export existentes.

## 8. Histórico

| Data | Mudança | Commit |
|---|---|---|
| 2026-07-13 | Spec criada (📋) | — |
