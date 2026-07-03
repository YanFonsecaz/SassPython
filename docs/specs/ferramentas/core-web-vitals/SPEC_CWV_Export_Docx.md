# SPEC — Exportar documentação CWV em `.docx`

**Status:** ✅ implementado · **Data:** 2026-06-01
**Escopo:** backend (2 endpoints + montagem do documento + 1 dependência + pequena melhora no renderer compartilhado) + frontend (botões de download + api client)
**Reusos:** **`parecer_service.html_para_docx_bytes`** (motor `.docx` do Parecer) · `cwv_persistencia` (busca de análise/problemas) · padrão de download via blob de `lib/api/parecer.ts` (`exportarParecer`) · `StreamingResponse` (como em `ferramentas_parecer.py`)
**Specs irmãs:** [[SPEC_Parecer_Geracao_Docx]] (renderer reaproveitado) · [[SPEC_Ferramenta_Core_Web_Vitals]] · [[SPEC_CWV_Dashboard_Historico]]

## 1. Objetivo

Permitir baixar a documentação do Core Web Vitals em `.docx`, de **duas** formas:

- **A) Um `.docx` por problema** — cada item do plano de ação (ex.: “Scripts bloqueando renderização
  no `<head>`”) vira um documento próprio, pronto para enviar a quem vai corrigir.
- **B) Relatório completo da URL** — todos os problemas de uma análise num único `.docx`, com
  cabeçalho (URL, plataforma, estratégia, métricas) e sumário.

Reaproveita o motor de `.docx` já existente (Parecer): monta **HTML** e converte com
`html_para_docx_bytes`. Não há tabela/coluna nova — os dados já existem.

## 2. Dados disponíveis (sem migração)

`CwvProblema` (`backend/app/models/cwv_problema.py`) já tem tudo:
- `titulo`, `severidade` (1–5), `metricas_afetadas` (lista, ex.: `["LCP","FCP"]`), `audit_id`/`kb_codigo`
- `contexto_especifico` (JSONB): `display_value`, `savings_ms`/`savings_bytes`, `metric_savings`,
  `description`, `details_type`, `warnings`, `items[]` (os “Recursos afetados”), `headings`
- `documentacao_md` (markdown “Como corrigir”: Problema / Solução, com listas e blocos de código)

`CwvAnalise`: `url_canonica`, `template_tipo`, `plataforma_detectada`, `estrategia` (mobile/desktop),
`score_performance`, `lcp_ms`, `cls`, `inp_ms`, `fcp_ms`, `criado_em`. Busca já pronta em
`cwv_persistencia.buscar_analise_com_problemas` / `buscar_problemas_analise` / `buscar_analise_por_id`.

## 3. Backend

### 3.1 Dependência
- `backend/pyproject.toml`: adicionar **`markdown>=3.5`** (puro-Python) para converter
  `documentacao_md` → HTML, com extensões `fenced_code`, `tables`, `sane_lists`.

### 3.2 Melhora no renderer compartilhado (`parecer_service.py`)
O `documentacao_md` usa **blocos de código** (` ``` `), `h4`–`h6` e às vezes citações. O renderer
hoje cobre o vocabulário do Parecer (h1–h3, p, strong/em, ul/ol, table, img, hr). Generalizar
`_render_node` (beneficia o Parecer também):
- `pre` / `code` (bloco): parágrafo monoespaçado (estilo “code”), preservando o texto.
- `h4`/`h5`/`h6` → **Heading 3**.
- `blockquote` → parágrafo recuado.
- `a` (inline) → renderiza o texto do link (e, opcional, a URL entre parênteses).
- **Fallback seguro:** no `else`, em vez de iterar só elementos (perdendo texto de nós
  desconhecidos), renderizar o texto do nó como parágrafo. (Hoje um `h4`/`pre` perde o conteúdo.)

> Adicionar testes do renderer para `pre`/`code` e `h4` em `tests/test_parecer_docx.py` (o motor é
> compartilhado).

### 3.3 Montagem do HTML (`backend/app/services/cwv_export.py`, novo)
```python
def problema_para_html(problema: dict) -> str:
    # <h1>{titulo}</h1>
    # <p>Métricas: LCP, FCP · Severidade: Crítico</p>
    # <p><strong>Economia estimada:</strong> {display_value/savings}</p>   (se houver)
    # {markdown(description)}                                              (se houver)
    # <table data-recursos> Recurso | Detalhe | Desperdiçado | Total </table>  (de items[])
    # <h2>Como corrigir</h2> {markdown(documentacao_md)}
    ...

def relatorio_para_html(analise: dict, problemas: list[dict]) -> str:
    # <h1>Relatório Core Web Vitals — {url}</h1>
    # <p><em>{plataforma} · {estrategia} · {data}</em></p>
    # <table data-meta> Score/LCP/CLS/INP/FCP </table>
    # <h2>Sumário</h2> <table> Prioridade | Problema | Métricas | Severidade </table>
    # por problema (i a partir de 1): <h2>{i}. {titulo}</h2> + (valor, descrição, recursos, como corrigir como em problema_para_html, mas com headings rebaixados)
    ...
```
Reusa helpers de formatação (bytes/ms) e a tabela de recursos com as **mesmas colunas da UI**
(`cwv-problema-detalhes.tsx`: Recurso · Detalhe · Desperdiçado · Total; trunca em N itens? não —
no `.docx` inclui todos).

### 3.4 Persistência (`cwv_persistencia.py`)
- `buscar_problema_por_id(db, problema_id) -> CwvProblema | None` (join em `cwv_analise` para validar
  `usuario_id`), **ou** reusar `buscar_analise_com_problemas` e filtrar o problema.

### 3.5 Endpoints (`backend/app/routers/ferramentas_cwv.py`)
Mesma forma do `exportar` do Parecer (auth, ownership, `StreamingResponse`, `Content-Disposition`):

| Endpoint | Retorno |
|---|---|
| `GET /core-web-vitals/problema/{problema_id}/docx` | `.docx` de **um** problema (404 se não for do usuário) |
| `GET /core-web-vitals/analise/{analise_id}/docx` | `.docx` do **relatório completo** da análise |

```python
@router.get("/core-web-vitals/problema/{problema_id}/docx")
async def exportar_problema_docx(problema_id, db=..., usuario=...):
    prob = await cwv_persistencia.buscar_problema_por_id(db, problema_id)
    if not prob or str(prob_analise.usuario_id) != str(usuario.id):
        raise HTTPException(404, "Problema nao encontrado")
    from app.services.cwv_export import problema_para_html
    from app.services.parecer_service import html_para_docx_bytes
    docx = html_para_docx_bytes(problema_para_html(prob_dict))
    nome = _slug(prob.titulo)  # ex.: "cwv-scripts-bloqueando-render.docx"
    return StreamingResponse(io.BytesIO(docx), media_type="...wordprocessingml.document",
                             headers={"Content-Disposition": f'attachment; filename="{nome}.docx"'})
```
(O endpoint do relatório é análogo, usando `relatorio_para_html(analise, problemas)`.)

> Sem custo de créditos (é só re-exportar dados já gerados) e sem job assíncrono — render é rápido.
> Rate limit leve (`rate_limit_autenticado`, ex.: 30/5min).

## 4. Frontend

### 4.1 API client (`frontend/src/lib/api/cwv.ts`)
Download via blob (mesmo padrão de `exportarParecer`, com Bearer/CSRF):
```ts
export async function exportarProblemaCwvDocx(problemaId: string): Promise<Blob> { ... }
export async function exportarRelatorioCwvDocx(analiseId: string): Promise<Blob> { ... }
// + helper baixarBlob(blob, nome) reaproveitável
```

### 4.2 UI
- **Por problema (Opção A):** botão **“Exportar .docx”** (ícone `DownloadIcon`, `variant ghost/sm`) no
  cabeçalho de cada `AccordionItem` em `cwv-plano-acao.tsx` — ao lado dos badges. `stopPropagation`
  para não abrir/fechar a accordion ao clicar.
- **Relatório completo (Opção B):** botão **“Baixar relatório (.docx)”** no topo do dashboard da
  análise (`cwv-dashboard-client.tsx`), perto do título/ações, passando o `analise_id`.
- Estados: spinner no botão durante o download; `toast.error(mensagemErroAmigavel(e))` em falha.

## 5. Verificação
- **Pytest:** `cwv_export.problema_para_html` / `relatorio_para_html` produzem o HTML esperado
  (título, tabela de recursos, “Como corrigir”); `html_para_docx_bytes` gera `.docx` válido com
  blocos de código preservados (novo teste do renderer para `pre`/`code`/`h4`).
- **E2E local:** abrir uma análise CWV real, exportar 1 problema e o relatório completo, abrir no
  Word e conferir (cabeçalho, sumário, tabela de recursos, código formatado).
- `ruff` + `tsc`/`next build` limpos.

## 6. Critério de pronto
- [ ] `GET /problema/{id}/docx` baixa o `.docx` de um problema (multi-tenant; 404 para outro usuário)
- [ ] `GET /analise/{id}/docx` baixa o relatório completo (cabeçalho + sumário + todos os problemas)
- [ ] Renderer preserva **blocos de código** e `h4`–`h6` (com teste); Parecer segue intacto
- [ ] Botão “Exportar .docx” por problema (sem abrir/fechar a accordion) e “Baixar relatório” no dashboard
- [ ] Sem créditos cobrados; nomes de arquivo amigáveis (slug do título / URL)

## 7. Notas / evolução
- Opcional: incluir um print/imagem (screenshot do PSI) no `.docx` se passarmos a guardá-los (hoje o
  CWV não persiste imagens — diferente do Parecer).
- Opcional: “Baixar todos os problemas (zip)” — fora do escopo; as duas opções acima cobrem o pedido.
