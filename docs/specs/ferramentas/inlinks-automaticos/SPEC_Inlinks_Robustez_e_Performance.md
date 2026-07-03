# SPEC — Inlinks: robustez, cobrança justa e performance

**Status:** ✅ implementado
**Escopo:** backend (workflow + 3 agentes + llm_guard + ferramenta_service)
**Crédito:** muda — cobrança proporcional quando `n_aplicados == 0`
**Depende de:** `SPEC_Inlinks_Bugs_Pos_Spec_Qualidade.md` aplicada

---

## Contexto

Revisão profunda da ferramenta após aplicação da SPEC anterior identificou 6 problemas remanescentes — não fatais mas com impacto direto em confiança do usuário, eficiência e estabilidade sob concorrência:

1. **B7 — `erro_msg` ausente no branch de zero candidatas válidas.** A SPEC anterior dizia para popular a mensagem; aplicação atual deixa em branco. Usuário vê "concluída" sem motivo claro.
2. **B6 — Cobrança cheia quando `n_aplicados == 0` mas `n_validas > 0`.** Usuário paga 15+N créditos por execução sem inlinks aplicados (todas filtradas pelo reranker ou rejeitadas pelo revisor).
3. **A6 — Agentes (Inseridor, Reranker, Revisor) sobrescrevem `_invoke_llm` e chamam `self.llm.ainvoke` direto.** Bypass de `chamada_llm_com_retry` → semáforo de concorrência por usuário + retry + rate limit ignorados. Em rajada de execuções, risco real de rate-limit OpenAI.
4. **B3 — N+1 chamadas de embedding no Inseridor.** `_validar_relevancia_semantica` é chamado dentro do loop por candidato, cada chamada gera 2 textos. 5 candidatos = 5 round-trips. Pode ser 1 batch.
5. **B1 — Rollback em `IntegrityError` durante insert de chunks destrói chunks já gravados.** `session.rollback()` no meio do loop sobre N chunks anula tudo desde o último commit. Em race condition (testes paralelos do mesmo usuário com mesma URL), perdem-se chunks silenciosamente.
6. **B5 — Reranker LLM recebe 30 candidatos em um prompt.** Atenção do LLM diminui no meio da lista (efeito "lost in the middle"); pré-filtro para top-15 reduz custo e melhora precisão.

Todos os 6 são fixes pequenos e isolados.

---

## 1. Resumo

Seis entregas. Pode ser 1 PR com 6 commits (1 por entrega) para facilitar review e bissecção.

| # | Entrega | Arquivos | Esforço |
|---|---|---|---|
| **1** | B7 — `erro_msg` no branch zero candidatas | `workflow_inlinks.py` | 1 min |
| **2** | B6 — Cobrança proporcional quando `n_aplicados == 0` | `workflow_inlinks.py` | 5 min |
| **3** | A6 — Agentes usam `chamada_llm_mensagem_com_retry` via guard | `llm_guard.py`, 6 agentes inlinks | 15 min |
| **4** | B3 — Batch embeddings no Inseridor | `inseridor.py` | 15 min |
| **5** | B1 — SAVEPOINT por chunk no insert | `workflow_inlinks.py` | 10 min |
| **6** | B5 — Pré-filtrar top-15 antes do reranker | `workflow_inlinks.py` | 1 min |

Total: ~45 min.

---

## 2. Entrega 1 — `erro_msg` no branch zero candidatas

### `backend/app/agents/workflow_inlinks.py:777-784`

Atualizar `_finalizar_sucesso_inlinks` no branch `n_processadas == 0`:

```python
if n_processadas == 0:
    execucao.status = "concluida"
    execucao.creditos_cobrados = 0
    execucao.erro_msg = (
        "Nenhuma URL candidata pode ser processada. "
        "Possiveis causas: dominio inexistente (DNS), robots.txt bloqueando, "
        "ou IP privado. Verifique as URLs informadas."
    )
    execucao.resultado_json = resultado_json
    execucao.concluida_em = datetime.utcnow()
    await db.flush()
    logger.info("execucao_id=%s inlinks status=concluida sem creditos (0 candidatas validas)", execucao_id)
    return
```

UI já exibe `erro_msg`, nenhuma mudança de frontend.

---

## 3. Entrega 2 — Cobrança proporcional quando `n_aplicados == 0`

### Lógica

- `n_validas == 0` → cobrança 0 (já implementado).
- `n_validas > 0 AND n_aplicados == 0` → cobrar **apenas** o custo por URL (sem `CUSTO_BASE_INLINKS=15`). Justifica-se: scraping + embeddings + reranker rodaram, mas resultado final é zero inlinks. Cobrar base de 15 nesse cenário é desproporcional.
- `n_aplicados > 0` → cobrança cheia normal.

### `backend/app/agents/workflow_inlinks.py:_finalizar_sucesso_inlinks`

Após o branch de `n_processadas == 0`, antes da chamada normal:

```python
custo = ferramenta_service.calcular_custo_inlinks(n_processadas)

# Sem inlinks aplicados → cobra so pelas URLs (sem base)
n_aplicados = resultado_json.get("n_aplicadas", 0)
if n_aplicados == 0:
    custo = max(0, custo - ferramenta_service.CUSTO_BASE_INLINKS)
    logger.info(
        "execucao_id=%s inlinks: 0 aplicados de %d validas, cobrando so URLs (custo=%d, sem base)",
        execucao_id, n_processadas, custo,
    )

saldo_ok = await credito_service.verificar_saldo_suficiente(...)
# ... resto igual
```

Também ajustar a descrição do débito quando aplica:

```python
descricao_extra = " (sem base - nenhum inlink aplicado)" if n_aplicados == 0 else ""
await credito_service.debitar_creditos(
    db,
    str(execucao.usuario_id),
    custo,
    descricao=(
        f"Inlinks automaticos: {custo} creditos "
        f"(base={'0' if n_aplicados == 0 else ferramenta_service.CUSTO_BASE_INLINKS}, "
        f"urls={n_processadas}){descricao_extra}"
    ),
    ferramenta="inlinks_automaticos",
    execucao_id=execucao_id,
)
```

### `CUSTO_BASE_INLINKS` está em `ferramenta_service`

Apenas referenciar, sem mudar a constante.

---

## 4. Entrega 3 — Agentes inlinks usam guard de concorrência

### A.1 Helper novo em `backend/app/core/llm_guard.py`

Adicionar (após `chamada_llm_com_retry`):

```python
async def chamada_llm_mensagem_segura(llm, mensagens: list, usuario_id: str):
    """Chama llm.ainvoke(mensagens) respeitando rate limit + semaforos."""
    await _rate_limit_wait()
    async with _llm_semaphore, get_user_semaphore(usuario_id):
        return await llm.ainvoke(mensagens)


async def chamada_llm_mensagem_com_retry(llm, mensagens: list, usuario_id: str):
    """Wrapper com retry para llm.ainvoke(mensagens)."""
    for tentativa in range(MAX_RETRIES + 1):
        try:
            return await chamada_llm_mensagem_segura(llm, mensagens, usuario_id)
        except Exception as e:
            if tentativa == MAX_RETRIES:
                raise WorkflowError(f"LLM falhou apos {MAX_RETRIES + 1} tentativas: {e}") from e
            erro_str = str(e)
            delay = min(30 * (tentativa + 1), 180) if "429" in erro_str else min(BACKOFF_BASE * (tentativa + 1), 60)
            logger.warning("LLM error, tentativa %d/%d, aguardando %ds: %s", tentativa + 1, MAX_RETRIES + 1, delay, e)
            await asyncio.sleep(delay)
```

### A.2 Refatorar `_invoke_llm` nos 6 agentes inlinks

Padrão atual (Inseridor, Reranker, Revisor, Cleaner, Enriquecedor, Formatador):

```python
async def _invoke_llm(self, prompt: str) -> str:
    from langchain_core.messages import HumanMessage
    response = await self.llm.ainvoke([HumanMessage(content=prompt)])
    return response.content
```

Trocar para:

```python
async def _invoke_llm(self, prompt: str) -> str:
    from langchain_core.messages import HumanMessage
    from app.core.llm_guard import chamada_llm_mensagem_com_retry
    response = await chamada_llm_mensagem_com_retry(
        self.llm, [HumanMessage(content=prompt)], self.usuario_id
    )
    return response.content
```

Aplicar em:

- `backend/app/agents/inlinks/inseridor.py` (`_InseridorAgent`)
- `backend/app/agents/inlinks/reranker.py` (`_RerankerAgent`)
- `backend/app/agents/inlinks/revisor.py` (`_RevisorAgent`)
- `backend/app/agents/inlinks/cleaner.py` (`_CleanerAgent`)
- `backend/app/agents/inlinks/enriquecedor_metadados.py` (`_EnriquecedorAgent`)
- `backend/app/agents/inlinks/formatador.py` (`_FormatadorAgent`)

**Resultado:** concorrência por usuário, rate limit e retry funcionam uniformemente em todos os agentes inlinks.

---

## 5. Entrega 4 — Batch embeddings no Inseridor

### `backend/app/agents/inlinks/inseridor.py:inserir_inlinks`

Atualmente (`:113-135`), o loop chama `_validar_relevancia_semantica` por candidato, que gera 2 embeddings via `gerar_embeddings_batch([contexto, destino], usuario_id)` — uma round-trip por candidato.

Refatorar para pré-computar tudo em um único batch:

```python
async def inserir_inlinks(
    pilar_markdown: str,
    candidatos: list[dict],
    usuario_id: str,
    max_inlinks: int = 8,
) -> tuple[str, list[InlinkInserido]]:
    if not pilar_markdown.strip() or not candidatos:
        return pilar_markdown, []

    paragrafos = pilar_markdown.split("\n\n")
    candidatos_top = sorted(candidatos, key=lambda c: c.get("score_total", 0), reverse=True)[:max_inlinks]

    textos_paragrafos = [p[:2000] for p in paragrafos]
    paragrafos_embeddings = await gerar_embeddings_batch(textos_paragrafos, usuario_id)

    # 1) Propostas LLM por candidato (sequencial - cada chamada e independente)
    propostas_por_candidato: list[tuple[dict, dict | None]] = []
    for c in candidatos_top:
        contexto_paragrafos = await _selecionar_paragrafos_relevantes(
            paragrafos,
            c.get("titulo", ""),
            c.get("resumo", ""),
            paragrafos_embeddings,
            usuario_id,
        )
        if not contexto_paragrafos:
            logger.info("Inseridor: candidato %s sem paragrafos elegiveis", c.get("url"))
            propostas_por_candidato.append((c, None))
            continue
        proposta = await _propor_insercao_para_candidato(c, contexto_paragrafos, usuario_id)
        propostas_por_candidato.append((c, proposta))

    # 2) Validacao semantica em BATCH unico para todas as propostas
    pares_para_validar: list[tuple[int, dict, dict]] = []  # (idx, candidato, proposta)
    textos_batch: list[str] = []
    for idx, (c, proposta) in enumerate(propostas_por_candidato):
        if not proposta:
            continue
        p_idx = proposta.get("paragrafo_idx", -1)
        trecho = proposta.get("trecho_original", "")
        paragrafo = paragrafos[p_idx] if 0 <= p_idx < len(paragrafos) else ""
        contexto = f"{trecho} {paragrafo[:200]}"
        destino = f"{c.get('titulo', '')} {c.get('resumo', '')[:300]}"
        pares_para_validar.append((idx, c, proposta))
        textos_batch.append(contexto)
        textos_batch.append(destino)

    embs_batch: list = []
    if textos_batch:
        embs_batch = await gerar_embeddings_batch(textos_batch, usuario_id)

    # 3) Aplicar resultado da validacao
    todas_insercoes: list[dict] = []
    for i, (idx, c, proposta) in enumerate(pares_para_validar):
        emb_ctx = embs_batch[i * 2] if i * 2 < len(embs_batch) else None
        emb_dst = embs_batch[i * 2 + 1] if i * 2 + 1 < len(embs_batch) else None
        if emb_ctx is None or emb_dst is None:
            todas_insercoes.append(proposta)
            continue
        try:
            cosine = float(dot(emb_ctx, emb_dst) / (norm(emb_ctx) * norm(emb_dst) + 1e-8))
        except Exception:
            cosine = 0.0
        if cosine < _MIN_INSERCAO_SEMANTICA:
            proposta["forcar_sugestao_manual"] = True
            proposta["motivo_sugestao"] = "Baixa relacao semantica entre ancora e destino."
        todas_insercoes.append(proposta)

    return _aplicar_insercoes(pilar_markdown, paragrafos, candidatos_top, todas_insercoes)
```

**Remover** `_validar_relevancia_semantica` (não usada mais) ou converter em helper de cosine puro caso outra ferramenta use.

**Ganho:** 5 candidatos × 2 textos = 10 textos. Antes: 5 chamadas. Depois: 1 chamada. Reduz latência do `inserir` em ~3-5s.

---

## 6. Entrega 5 — SAVEPOINT por chunk no insert

### `backend/app/agents/workflow_inlinks.py:333-351`

Substituir o `try/except IntegrityError` que faz rollback global:

```python
# ANTES (linhas 333-351):
try:
    session.add(vetor)
    await session.flush()
except IntegrityError:
    await session.rollback()
    stmt2 = (...)
    result2 = await session.execute(stmt2)
    existing = result2.scalars().first()
    if existing:
        emb = existing.embedding
```

```python
# DEPOIS:
try:
    async with session.begin_nested():
        session.add(vetor)
        await session.flush()
except IntegrityError:
    # Conflito (mesma url_canonica + chunk_index ja existe) — buscar o existente
    stmt2 = (
        sel(ConteudoVetor)
        .where(
            ConteudoVetor.usuario_id == uid,
            ConteudoVetor.url_canonica == url_c,
            ConteudoVetor.chunk_index == ch.ordem,
            ConteudoVetor.ativo == True,
        )
        .order_by(ConteudoVetor.chunk_index)
    )
    result2 = await session.execute(stmt2)
    existing = result2.scalars().first()
    if existing:
        emb = existing.embedding
```

`session.begin_nested()` cria um SAVEPOINT na transação atual. O `IntegrityError` reverte só o SAVEPOINT (descartando o vetor problemático), preservando os chunks já inseridos. O `commit` na linha 369 finaliza os chunks bem-sucedidos.

**Garantia:** em race condition (testes concorrentes), chunks 1..N-1 não são mais perdidos.

---

## 7. Entrega 6 — Pré-filtrar top-15 antes do reranker

### `backend/app/agents/workflow_inlinks.py:447-448`

```python
# ANTES:
scored = sorted(best_by_url.values(), key=lambda x: x["score_semantico"], reverse=True)
scored = scored[:30]

# DEPOIS:
scored = sorted(best_by_url.values(), key=lambda x: x["score_semantico"], reverse=True)
scored = scored[:15]
```

**Ganho:** prompt do reranker ~50% menor → menos tokens, latência menor, qualidade melhor (LLM tem atenção mais densa nos 15 itens). Se em produção 30 candidatas viram comuns (raro hoje, com 4–10 URLs por execução), revisitar.

---

## 8. Verificação ponta a ponta

### 8.1 Sanidade de import e config

```bash
grep -rn "chamada_llm_mensagem_com_retry\|chamada_llm_mensagem_segura" backend/app | head -10
grep -rn "self.llm.ainvoke" backend/app/agents/inlinks/ | head
# Deve mostrar APENAS o helper em llm_guard.py — nenhum agente inlinks chamando diretamente.
```

### 8.2 Restart

```bash
pkill -f "uvicorn app.main"; pkill -f "arq app.worker"
cd backend && nohup python3 -u -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
cd backend && nohup python3 -u -m arq app.worker.WorkerSettings > /tmp/worker.log 2>&1 &
sleep 3
curl -sf -o /dev/null -w "Backend: %{http_code}\n" http://localhost:8000/health
```

### 8.3 Cenários

1. **Execução normal (4 URLs reais):** workflow conclui em ~50-60s. Compare com baseline pré-SPEC — esperado: 5-10s mais rápido (batch embeddings).
2. **Execução com URL inexistente (DNS fail):** status `concluida`, `creditos_cobrados=0`, `erro_msg` populado com a frase nova.
3. **Execução com URLs válidas mas tema desconexo (todas filtradas):** status `concluida`, `creditos_cobrados = N` (sem base 15), inlinks lista vazia.
4. **Execução concorrente (mesmo usuário, 2 jobs em paralelo):** ambos completam sem `AttributeError`/loss de chunks. Confirmar via `SELECT count(*) FROM conteudos_vetores WHERE usuario_id=... AND url_canonica=...` antes/depois.
5. **Reranker recebe 15:** worker.log mostra `Top 15 por similaridade semantica, aplicando re-rank LLM...` (não mais 30).
6. **Concorrência LLM:** disparar 3 execuções simultâneas. Log deve mostrar `Rate limit: aguardando Xs entre chamadas LLM` — confirma que o guard está sendo respeitado.

### 8.4 SQL de auditoria

```sql
-- Execucoes que cobraram 0 (zero candidatas validas)
SELECT id, criado_em, erro_msg, creditos_cobrados
FROM execucoes_ferramentas
WHERE ferramenta = 'inlinks_automaticos' AND creditos_cobrados = 0
ORDER BY criado_em DESC LIMIT 10;

-- Execucoes que cobraram so URLs (n_aplicados == 0)
SELECT id, criado_em, creditos_cobrados, resultado_json->>'n_aplicadas' AS n_aplicadas, resultado_json->>'n_candidatas_validas' AS n_validas
FROM execucoes_ferramentas
WHERE ferramenta = 'inlinks_automaticos'
  AND (resultado_json->>'n_aplicadas')::int = 0
  AND (resultado_json->>'n_candidatas_validas')::int > 0
ORDER BY criado_em DESC LIMIT 10;
```

---

## 9. Fora de escopo

- **Pré-filtro por score_semantico ANTES do reranker** (poderia eliminar candidatos com cosine muito baixo antes mesmo de mandar pro LLM). Avaliar se o top-15 já basta antes de adicionar lógica.
- **Cobrança totalmente proporcional ao `n_aplicados/n_validas`** (atualmente é cobrança binária: cheia ou só URLs). Ficar binário enquanto não tem demanda real.
- **Refactor de cache de embeddings** para deduplicar entre tenants (problema A2 da revisão).
- **Resolver assimetria pilar mean-pool vs candidata max-chunk** (problema A1).
- **Backfill de `resumo`/`categoria`** em vetores antigos. Vetores rerunados naturalmente populam.
- **Retry granular por node LangGraph** (atualmente o retry é só dentro de cada `_invoke_llm`).

---

## 10. Riscos

- **B6 (cobrança parcial)** muda a lógica de débito. Se algum teste/cliente depende do valor exato cobrado, vai ver inlinks "mais baratos" em execuções sem aplicação. Aceitável: corrige injustiça, alinha com o que o usuário espera.
- **Refactor batch do Inseridor (B3)** muda fluxo de controle — pode introduzir bug se a ordem de propostas ↔ embeddings desalinhar. Mitigação: estrutura `pares_para_validar` carrega `(idx, c, proposta)` explicitamente, indexa embs por `i * 2` / `i * 2 + 1` com bounds check.
- **SAVEPOINT (B1)** muda o controle transacional. Bibliotecas SQLAlchemy async com `begin_nested` funcionam, mas certificar que o driver (asyncpg + pgvector) suporta. Em geral suporta — pgvector é só tipo de coluna, não interfere em transações.
- **Concorrência via `chamada_llm_mensagem_com_retry`** introduz uma camada de bloqueio. Se o semáforo global (`llm_global_concurrency=3`) for muito apertado, pode reduzir throughput. Aceitável: é o mesmo limite que outros workflows respeitam.

---

## 11. Arquivos críticos

### Backend — alterados
- `backend/app/agents/workflow_inlinks.py` — `_finalizar_sucesso_inlinks` (B7 + B6), `node_match_rerank` (B5), `node_enriquecer` (B1).
- `backend/app/core/llm_guard.py` — adicionar `chamada_llm_mensagem_segura` e `chamada_llm_mensagem_com_retry`.
- `backend/app/agents/inlinks/inseridor.py` — refactor batch (B3) + `_invoke_llm` via guard (A6).
- `backend/app/agents/inlinks/reranker.py` — `_invoke_llm` via guard.
- `backend/app/agents/inlinks/revisor.py` — `_invoke_llm` via guard.
- `backend/app/agents/inlinks/cleaner.py` — `_invoke_llm` via guard.
- `backend/app/agents/inlinks/enriquecedor_metadados.py` — `_invoke_llm` via guard.
- `backend/app/agents/inlinks/formatador.py` — `_invoke_llm` via guard.

### Backend — sem mudança
- `backend/app/services/ferramenta_service.py` — referencia `CUSTO_BASE_INLINKS` (sem alterar).

### Frontend
- Nenhuma alteração obrigatória.

---

## 12. Verificação (sumário)

1. Grep confirma todos os agentes inlinks chamando guard.
2. Restart sem erro.
3. Execução com DNS fail → 0 créditos + erro_msg.
4. Execução com candidatas reprovadas → cobra só URLs (sem base).
5. Concorrência → log de rate limit visível, sem chunks perdidos.
6. Reranker prompt menor (top 15).
