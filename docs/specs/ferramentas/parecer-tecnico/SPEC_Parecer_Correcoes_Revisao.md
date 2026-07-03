# SPEC — Correções pós code-review (bugs do Parecer Técnico)

**Status:** ✅ implementado · **Data:** 2026-06-01
**Escopo:** backend (créditos em falha, retry, render `.docx`, validação) + frontend (agrupamento imagem↔texto, polling, compressão) — correções de bugs encontrados na revisão da feature já em produção.
**Reusos:** `ferramenta_service.finalizar_falha`/`_obter_reserva_estimada`, `credito_service.liberar_reserva`, `app/core/excecoes.ErroPermanente`, padrão de cleanup de hooks (CWV `usePathname`)
**Specs irmãs:** [[SPEC_Parecer_Ferramenta]] · [[SPEC_Parecer_IA_Visao_Multimodal]] · [[SPEC_Parecer_Geracao_Docx]] · [[SPEC_Parecer_Editor_Frontend]] · [[SPEC_Parecer_Cenarios_Erro_Estados_e_Observabilidade]]

## Contexto

Revisão (code-review high) da feature em produção encontrou bugs **nos caminhos de
falha/erro** (o caminho feliz funciona). Esta spec corrige os de alta/média prioridade e anota os de
baixa. Cada item tem causa precisa e a correção.

---

## 🔴 P0 — Contabilidade de créditos em falha

### Problema
Quando a geração falha, os créditos reservados (`10 + 3×imagens`) não são liberados corretamente:
1. `_obter_reserva_estimada("parecer_tecnico")` retorna só `CUSTO_BASE_PARECER` (10), **não** o reservado
   real → numa falha de LLM o worker (`_marcar_falhou → finalizar_falha`) libera só 10 e os `3×N`
   por imagem **ficam presos** em `saldo_reservado`.
2. `_falhar` (workflow) libera **duas vezes**: `finalizar_falha` (que já libera) **+** `liberar_reserva(custo)`.
   Com outra reserva concorrente na mesma conta, a liberação extra de 10 **come crédito de outra reserva**.

### Causa
- `backend/app/services/ferramenta_service.py` → `_obter_reserva_estimada`:
  ```python
  if ferramenta == "parecer_tecnico":
      return CUSTO_BASE_PARECER   # ❌ deveria ser o reservado real
  ```
- `backend/app/agents/parecer/workflow.py` → `_falhar`:
  ```python
  await finalizar_falha(session, execucao_id, msg, ferramenta="parecer_tecnico")  # ja libera
  if custo > 0:
      await credito_service.liberar_reserva(session, usuario_id, custo)            # ❌ libera de novo
  ```

### Correção
1. `_obter_reserva_estimada` para parecer retorna o **reservado real** da execução:
   ```python
   if ferramenta == "parecer_tecnico":
       return execucao.creditos_cobrados or CUSTO_BASE_PARECER
   ```
2. `_falhar` chama **somente** `finalizar_falha` (que agora libera o valor certo) — remover o
   `liberar_reserva` extra:
   ```python
   async def _falhar(execucao_id, usuario_id, custo, msg):
       async with async_session_factory() as session:
           await ferramenta_service.finalizar_falha(session, execucao_id, msg, ferramenta="parecer_tecnico")
           await session.commit()
   ```
   (Assim os 3 caminhos — `_falhar`, worker `_marcar_falhou`, e OPENAI_API_KEY ausente — liberam
   exatamente `creditos_cobrados`, uma única vez.)

### Verificação
- Teste: reserva 10+3×N; falha → `saldo_reservado` volta a 0 e `saldo_disponivel` recompõe o total.
- Teste com 2 reservas concorrentes: falha de uma libera só a dela (não toca a outra).

---

## 🔴 P0 — Retry re-roda o workflow e re-cobra

### Problema
Falha de LLM vira `WorkflowError` (Exception genérica). O workflow faz `except Exception: ... raise`;
o worker `_executar_job` re-levanta no `else` → **ARQ retenta (max_tries=3)**, re-rodando visão+redação
(3× custo/tempo). Como a reserva já foi liberada no `_falhar`, um retry que conclua chama
`confirmar_debito` e **cobra de novo** do `saldo_disponivel`.

### Causa
`backend/app/agents/parecer/workflow.py` — `except Exception as e: ... await _falhar(...); raise`
(reraise genérico → o worker retenta) e ausência de guard de idempotência na entrada.

### Correção
1. **Guard de idempotência** no início do `executar_workflow_parecer`: se a execução já está em estado
   terminal, não re-rodar:
   ```python
   ex = await ferramenta_service.buscar_execucao(session, execucao_id)
   if not ex or ex.status in ("concluida", "falhou", "cancelada"):
       return
   ```
2. No `except Exception`, após `_falhar`, levantar **`ErroPermanente`** (que o worker **não** retenta) em
   vez de re-levantar a Exception genérica — as falhas de LLM já passaram pelo retry interno do
   `chamada_llm_mensagem_com_retry`, não há ganho em re-rodar o workflow inteiro:
   ```python
   except Exception as e:
       ... metrics/sentry ...
       await _falhar(execucao_id, usuario_id, custo, f"Erro ao gerar parecer: {e}")
       raise ErroPermanente(str(e)) from e
   ```

### Verificação
- Teste: workflow com `gerar_parecer_estruturado` lançando Exception → marca `falhou`, libera reserva 1×,
  e **não** é re-enfileirado (mock de ARQ/`_executar_job` não chama o handler de novo).
- Teste do guard: chamar `executar_workflow_parecer` numa execução já `concluida` → retorna sem efeito.

---

## 🔴 P0 — `.docx` sai com o parágrafo inteiro em negrito

### Problema
No export `.docx`, cada parágrafo "**Problema** …", "**Evidência:** …", "**Solução** …" sai **todo**
em negrito (e parágrafos com `<em>` saem todos em itálico), em vez de só o rótulo. O **preview HTML**
está correto; é só o renderer do `.docx` (o entregável).

### Causa
`backend/app/services/parecer_service.py` → `_render_inline`: cria **um único `run`** para o parágrafo
e seta `run.bold = True` (ou `italic`) assim que encontra o primeiro `<strong>`/`<em>`, concatenando
todo o texto dos filhos nesse mesmo run.

### Correção
Reescrever `_render_inline` para emitir **um run por filho**, preservando a formatação só do trecho
correto:
```python
def _render_inline(paragraph, node) -> None:
    for child in node.iter(include_text=True):
        ctag = (child.tag or "").lower()
        text = child.text() or ""
        if not text:
            continue
        run = paragraph.add_run(text)
        if ctag in ("strong", "b"):
            run.bold = True
        elif ctag in ("em", "i"):
            run.italic = True
        # text node ("-text") -> run normal
```
(Ajustar `_render_paragraph` para passar o `paragraph` — não um run pré-criado — e iterar os filhos.)

### Verificação
- Teste: `html_para_docx_bytes("<p><strong>Problema</strong> desc</p>")` → o run de "Problema" tem
  `bold=True` e o run de " desc" tem `bold=False` (checar `runs` do parágrafo no `python-docx`).

---

## 🟠 P1 — Imagem perde a descrição do usuário

### Problema
No `formulario-parecer.tsx`, `blocosFromHtml` emite **cada imagem como um bloco próprio com `texto:""`**,
separada da descrição. No backend, `_construir_nota_map` dá `nota=""` para essa imagem → a **análise de
visão** (analisador) recebe a imagem **sem o texto que o usuário escreveu**, perdendo o contexto.

### Causa
`frontend/src/components/ferramentas/formulario-parecer.tsx` → `blocosFromHtml`:
```js
if (el.tagName === "IMG") { flush(); blocos.push({ texto: "", imagens: [src] }); return; }
```

### Correção
Acumular a imagem **no bloco corrente** (junto do texto adjacente) em vez de emitir um bloco isolado:
- manter `imagensAtuais.push(src)` e deixar o `flush()` emitir `{ texto, imagens }` **juntos**;
- flush ao fim de cada quebra de seção natural; se a heurística for incerta, preferir **menos** blocos
  (texto+imagens próximos no mesmo bloco) a separar imagem de texto.
Resultado: cada imagem herda a descrição próxima → a visão recebe a `nota` certa.

### Verificação
- Teste de unidade do parser: HTML `"<p>Desc A</p><img src=...>"` → 1 bloco `{texto:"Desc A", imagens:[...]}`
  (não 2 blocos com a imagem sem texto).

---

## 🟠 P1 — Polling não é cancelado / erros engolidos

### Problema
`use-parecer.ts`: o loop de polling (via `setTimeout` em `erroRef`) **não é limpo no unmount** (timer vivo
até 10 min + `setState` em componente desmontado) e o `catch` do `poll` **reagenda em qualquer erro**
(rede/404/500) → o usuário fica em "Analisando…" por 10 min em vez de ver o erro.

### Causa
`frontend/src/hooks/use-parecer.ts` — sem `useEffect` de cleanup; `reset()` não limpa `erroRef`; `catch`
do `poll` reagenda sem contar erros consecutivos.

### Correção
1. `useEffect(() => () => clearTimeout(erroRef.current ?? undefined), [])` (cleanup no unmount); `reset()`
   também limpa o timer.
2. Cap de erros consecutivos no `poll`: após N (ex.: 3) falhas seguidas de `buscarExecucaoParecer`,
   rejeitar com erro real (mostrar `mensagemErroAmigavel`), em vez de reagendar até o timeout.
3. (Opcional) flag `cancelado` para não chamar `setState` após o cleanup.

### Verificação
- Teste/observação: desmontar durante "gerando" não dispara warning de setState nem mantém o timer.
- Backend 500 repetido → erro aparece em poucos segundos, não em 10 min.

---

## 🟡 P2 — Anotados (baixo impacto)

| # | Item | Arquivo | Correção sugerida |
|---|---|---|---|
| 6 | Limites medem **base64** (~33% maior) vs. msg "4 MB/12 MB" → rejeita imagem ~25% menor | `routers/ferramentas_parecer.py` `_validar_blocos` | medir bytes **decodificados** (`len(base64.b64decode(b64_part))`) ou ajustar a mensagem |
| 7 | Mensagens do backend (`detail`) não chegam ao usuário (front lê `detalhe`) — **pré-existente em todo o app** | `frontend/src/lib/api.ts` `parseError` | remapear `detail`→`detalhe` no parse (beneficia o app inteiro) |
| 8 | `image-compress` encoda WebP **2×** (feature-detect + saída) | `frontend/src/lib/image-compress.ts` | detectar suporte a WebP **uma vez** num canvas 1×1 (cache de módulo); encodar a saída 1× |
| 9 | `/parecer/execucao/{id}` não filtra por `ferramenta` (lê execução de outra ferramenta) | `routers/ferramentas_parecer.py` | adicionar `ExecucaoFerramenta.ferramenta == "parecer_tecnico"` ao `where` (CWV tem o mesmo gap) |
| 10 | Corrida *enqueue-antes-do-commit* (worker pode não achar a execução) — **compartilhada com o CWV** | `routers/ferramentas_parecer.py` | commit explícito antes do `enqueue_job`, ou `_defer` curto no job |

---

## 🗺️ Execução

- **Commit 1 (P0/P1 — alta/média):** itens 1–5. Inclui testes novos (créditos em falha, no-retry, docx
  negrito, parser de blocos, cleanup do polling).
- **Commit 2 (P2 — baixa):** itens 6–10 (item 7 é global/opcional).
- Deploy: push em `main` → autoDeploy Render (migrations não mudam).

## ✅ Critério de pronto
- [ ] Falha libera **exatamente** o reservado, 1×; sem vazar nem comer reserva concorrente
- [ ] Falha de LLM **não** re-roda o workflow (sem retry/re-cobrança); guard de idempotência ativo
- [ ] `.docx`: só o **rótulo** Problema/Evidência/Solução em negrito (teste do `python-docx`)
- [ ] Cada imagem chega à visão **com** a descrição do usuário (teste do parser)
- [ ] Polling limpa o timer no unmount e surfaceia erro real em poucos segundos
- [ ] Suíte `tests/test_parecer_*.py` verde + `ruff` + `tsc`/`next build` limpos
