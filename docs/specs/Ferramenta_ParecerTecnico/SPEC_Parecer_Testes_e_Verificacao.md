# SPEC — Testes e Verificação

**Status:** a aplicar · **Data:** 2026-05-30
**Escopo:** pytest (backend) + E2E local + browser MCP
**Reusos:** infra de testes existente (`backend/tests`, `pytest-asyncio` com `asyncio_mode=auto`, `respx` para mock HTTP)
**Specs irmãs:** todas as demais desta pasta

## 1. Testes de backend (`backend/tests/`)

### 1.1 Renderer `.docx` (sem rede, rápido) — prioridade máxima

`tests/test_parecer_docx.py`:

- `estrutura_para_html`: dado um `ParecerEstruturado` de exemplo (com 1 seção, 1 problema, 1
  `imagens_indices=[0]`), o HTML contém `<h1>`, `<table data-meta>`, `<table data-causas>`, o `<img>`
  com o data URI esperado e os rótulos `Problema/Evidência/Solução`.
- `html_para_docx_bytes`:
  - retorna `bytes` não-vazios que **abrem** via `Document(io.BytesIO(...))` sem erro;
  - o documento tem ≥1 parágrafo `Title`, headings, 2 tabelas e ≥1 imagem (`doc.inline_shapes`);
  - **imagem WebP** e **GIF animado** de teste embutem (convertidas p/ PNG) — gerar bitmaps pequenos
    com Pillow no próprio teste;
  - HTML "editado" (parágrafo removido, texto trocado) ainda exporta sem erro;
  - nó desconhecido (`<blockquote>`) é ignorado sem quebrar (com log).
- Fallback de estilos: roda **sem** `parecer_template.docx` presente (usa `_garantir_estilos`).

### 1.2 Agentes de visão (mockando o LLM)

`tests/test_parecer_agentes.py`:

- `analisar_imagem`: mockar `chamada_llm_com_retry` para devolver um `AchadoImagem` fixo; garantir
  que a mensagem enviada é **multimodal** (tem bloco `image_url` com o data URI) e que `indice_global`
  é preenchido.
- `gerar_parecer_estruturado`: mock devolve `ParecerEstruturado`; garantir que o `cliente_nome` do
  argumento entra no contexto enviado ao LLM (e na `escopo_linha`).
- Sem `OPENAI_API_KEY`: `executar_workflow_parecer` falha com `ErroPermanente` e **libera a reserva**
  de créditos (mock de `credito_service`).

### 1.3 Rota + cobrança (integração)

`tests/test_parecer_rota.py` (seguir o estilo dos testes de rota existentes — client autenticado):

- `POST /parecer/custo` → custo = `10 + 3×n_imagens` (cap 90).
- `POST /parecer/gerar` sem créditos → `402`.
- `POST /parecer/gerar` ok → `202`, cria `ExecucaoFerramenta(ferramenta="parecer_tecnico")`,
  reserva créditos, enfileira (mock do `enqueue_job`).
- `GET /parecer/execucao/{id}` de outro usuário → `404` (multi-tenant).
- Falha no enqueue → status `falhou` + `liberar_reserva` chamado.
- `POST /parecer/{id}/exportar` com HTML simples → `200`, `Content-Type` docx,
  `Content-Disposition: attachment`, e persiste o HTML em `resultado_json`.
- Payload acima do limite (§6 da SPEC principal) → `413`.

### 1.4 Workflow (end-to-end com mocks de LLM)

`tests/test_parecer_workflow.py`: alimentar `entrada_json` com 2 blocos (1 com imagem, 1 só texto),
mockar analisador+documentador, rodar `executar_workflow_parecer` e checar:
`status=concluida`, `resultado_json.parecer_html` não-vazio, `confirmar_debito` chamado.

### 1.5 Persistência + Histórico ([[SPEC_Parecer_Dados_e_Persistencia]] / [[SPEC_Parecer_Historico_UI]])

`tests/test_parecer_persistencia.py`:
- `criar_parecer` grava linha com `meta_json`/`estrutura_json`/`parecer_html` e denormaliza
  `cliente_nome`/`plataforma`; worker guarda `parecer_id` em `execucao.resultado_json`.
- `atualizar_html` (via `exportar`) altera `parecer_html` e o re-download reflete a edição.
- `listar_pareceres`/`GET /parecer/historico` retornam **só** os do usuário e filtram por cliente.
- `GET /parecer/{id}` de outro usuário → `404`.
- `ON DELETE CASCADE`: apagar a execução remove o parecer.

### 1.6 Cenários de erro / robustez ([[SPEC_Parecer_Cenarios_Erro_Estados_e_Observabilidade]])
- **Falha parcial:** mock do analisador lança em 1 de 2 imagens → workflow conclui com `AchadoImagem`
  placeholder (degradado) e crédito **confirmado** (não aborta).
- Sem `OPENAI_API_KEY` → `ErroPermanente` + `liberar_reserva`.
- Payload > limite → `413`; bloco sem texto nem imagem → `422`.
- `data URI` com esquema inválido (ex.: `data:text/html`) → rejeitado na validação.

### 1.7 Comandos

```bash
cd backend
uv run pytest tests/test_parecer_*.py -v   # docx, agentes, rota, workflow, persistencia
uv run ruff check app/
uv run mypy app/agents/parecer app/services/parecer_service.py \
            app/services/parecer_persistencia.py app/routers/parecer.py app/models/parecer.py
```

Meta de cobertura do código novo: **≥70%** (alinhado ao critério das outras ferramentas).

## 2. Frontend

- `eslint` + `next build` limpos (static export precisa que o editor seja client-only — validar que
  o build **não** quebra por uso de `window`).
- (Opcional) teste leve de `comprimirImagem` e do parser `HTML → blocos` (texto+imagens em ordem).

## 3. E2E local (manual / assistido)

> **Subir com `make dev`** — o backend roda **no host** (o `make up`/Docker tem bug de host do
> Postgres; ver memória do projeto). Subir também o **worker ARQ** e o **frontend**. Garantir
> `OPENAI_API_KEY` no `.env` do backend.

Roteiro:
1. Login → abrir **/ferramentas/parecer**.
2. Selecionar um cliente.
3. **Colar** 1–2 prints reais (pode usar os PNGs do repo, ex. `cwv-detalhes-spec18.png`) e escrever
   descrições curtas.
4. **Gerar** → confirmar loading + polling → preview carrega no editor.
5. **Editar** um trecho do texto.
6. **Baixar .docx** → abrir no Word/Pages e conferir o padrão (cabeçalho de 3 linhas; seções `N.` →
   subseções `N.M.` com Problema/Evidência/Solução e prints embutidos; "Recomendações globais" por
   último; **sem** tabela de metadados nem sumário executivo).
7. Conferir: créditos debitados (confirmação), item no **Histórico**, isolamento por usuário.
8. Falhas: gerar sem créditos (402) e sem `OPENAI_API_KEY` (mensagem clara + refund).

## 4. Browser MCP (automação do fluxo)

Dirigir o fluxo colar→gerar→editar→baixar com **Playwright** ou **Chrome DevTools MCP**:
- navegar até a página autenticada, fazer upload/paste de uma imagem de teste,
- acionar **Gerar**, aguardar o preview (`wait_for` texto do parecer),
- **screenshot** do editor com o parecer gerado (evidência de E2E),
- validar o download do `.docx` (intercept de network / arquivo salvo).

## 5. Critérios de pronto (gate de release V1)

- [ ] Suites 1.1–1.4 verdes; cobertura do novo ≥70%
- [ ] `ruff`/`mypy` (novos módulos) e `eslint`/`next build` limpos
- [ ] E2E manual completo (passos 1–8) ok em pelo menos 1 cenário real
- [ ] Screenshot de E2E (browser MCP) anexado ao PR
- [ ] `.docx` final validado por um humano contra o documento de referência
