# SPEC — Inlinks: refinamentos finais (multi-tenant, fallbacks e observabilidade)

**Status:** ✅ implementado
**Escopo:** backend (workflow + inseridor) — sem migration, sem frontend
**Crédito:** não muda
**Depende de:** `SPEC_Inlinks_Robustez_e_Performance.md` aplicada

---

## Contexto

Após as 4 SPECs anteriores (`Qualidade_Match_e_Julgamento`, `Bugs_Pos_Spec_Qualidade`, `Robustez_e_Performance`), restam 5 problemas mapeados em revisão crítica:

1. **`cliente_id` nunca é setado em `ConteudoVetor`** — bug real para SaaS multi-tenant. `workflow_inlinks.py:313-332` cria vetores sem cliente_id mesmo quando a `execucao` tem cliente associado. Conteúdos misturam-se no namespace do usuário, e busca por cliente fica vazia.
2. **Vetores antigos (`resumo=NULL`) sabotam a Validação D do Inseridor** — migration 0010 adicionou `resumo`/`categoria`, mas vetores pré-migration permanecem com NULL. Em reuso, vira `""` e a Validação D compara contexto rico contra apenas o título do candidato → cosine baixo → tudo vira `sugestao_manual`. Diagnóstico: muitas execuções iterativas terminam com inlinks "aplicado=0" sem motivo aparente.
3. **NaN escapa como cosine** — se embedding vier com NaN (caso raro de API/cache), `NaN < threshold` retorna `False` em todas comparações → vetor lixo passa silenciosamente. Aparece em `workflow_inlinks.py:431` (match_rerank) e `inseridor.py:141, 198`.
4. **Sem fallback quando reranker filtra todos os candidatos** — usuário paga zero (graças à SPEC anterior), mas continua sem resultado útil. Se o sistema tem 4 candidatas válidas e zero passa em `threshold=0.6`, vale tentar `threshold * 0.85` antes de desistir.
5. **Logs do workflow não levam `execucao_id`** — quando 3 execuções rodam concorrentes, logs misturam-se. Difícil isolar uma execução específica em debug.

Todos os 5 são fixes pequenos. Total ~20 minutos.

---

## 1. Resumo

Cinco entregas. Pode ser 1 PR com 5 commits.

| # | Entrega | Arquivos | Esforço |
|---|---|---|---|
| **1** | `cliente_id` propagado e setado em `ConteudoVetor` | `workflow_inlinks.py` | 5 min |
| **2** | Fallback de `destino` no Inseridor quando `resumo` vazio | `inseridor.py` | 5 min |
| **3** | NaN check em todos os cosines | `workflow_inlinks.py`, `inseridor.py` | 3 min |
| **4** | Fallback de threshold no Reranker (retry com 0.85x) | `workflow_inlinks.py` | 5 min |
| **5** | Prefixo `[eid=...]` em logs do workflow e dos nodes | `workflow_inlinks.py` | 5 min |

---

## 2. Entrega 1 — `cliente_id` propagado e setado em `ConteudoVetor`

### Alterações em `backend/app/agents/workflow_inlinks.py`

#### a) `EstadoInlinks` (TypedDict, linhas 53-79)

Adicionar campo:

```python
class EstadoInlinks(TypedDict):
    execucao_id: str
    usuario_id: str
    cliente_id: str | None    # ← novo
    ...
```

#### b) `executar_workflow_inlinks` (~linha 704)

Após buscar a `execucao`, ler `cliente_id` e incluir em `estado_inicial`:

```python
estado_inicial: EstadoInlinks = {
    "execucao_id": execucao_id,
    "usuario_id": str(execucao.usuario_id),
    "cliente_id": str(execucao.cliente_id) if execucao.cliente_id else None,    # ← novo
    "pilar_url": entrada.get("pilar_url", ""),
    ...
}
```

#### c) `node_enriquecer` (~linha 313)

Setar `cliente_id` no `ConteudoVetor` cold-path:

```python
cliente_id_val = estado.get("cliente_id")

vetor = ConteudoVetor(
    usuario_id=uid,
    cliente_id=cliente_id_val,     # ← novo
    execucao_id=eid,
    titulo=titulo,
    conteudo=ch.texto,
    ...
)
```

Inicializar `cliente_id_val` no topo de `node_enriquecer` (após `uid = estado["usuario_id"]`).

#### d) Query de reuso (~linha 237-248)

Manter `usuario_id` como chave primária de busca; **opcionalmente** restringir por cliente para evitar vazamento entre clientes do mesmo usuário. Decisão de produto — preferir manter `usuario_id` como single tenant até o produto exigir o contrário.

Comentário inline:

```python
# A busca por html_hash + url_canonica + usuario_id basta;
# vetores não são por-cliente nesta versão. Para multi-cliente real,
# adicionar `ConteudoVetor.cliente_id == cliente_id_val` aqui.
```

---

## 3. Entrega 2 — Fallback de `destino` no Inseridor quando `resumo` vazio

### `backend/app/agents/inlinks/inseridor.py`

#### a) Helper privado

Adicionar no topo do módulo (após os REs):

```python
def _texto_destino(candidato: dict) -> str:
    """Monta a 'descricao' do candidato para validacao semantica.

    Usa resumo se preenchido; caso contrario, derive de titulo + categoria
    + palavras-chave para nao virar comparacao so contra o titulo.
    """
    titulo = candidato.get("titulo", "") or ""
    resumo = candidato.get("resumo", "") or ""
    if resumo.strip():
        return f"{titulo} {resumo[:300]}"

    categoria = candidato.get("categoria", "") or ""
    palavras = candidato.get("palavras_chave", []) or []
    palavras_str = ", ".join(palavras[:10]) if isinstance(palavras, list) else str(palavras)
    fallback = " ".join(filter(None, [titulo, categoria, palavras_str]))
    return fallback or titulo
```

#### b) Usar em `inserir_inlinks` (~linha 125)

```python
# ANTES:
destino = f"{c.get('titulo', '')} {c.get('resumo', '')[:300]}"

# DEPOIS:
destino = _texto_destino(c)
```

#### c) Usar também em `_selecionar_paragrafos_relevantes` (~linha 185)

Atualmente:
```python
consulta = f"{candidato_titulo}. {candidato_resumo}"[:1500]
```

Refatorar a função para receber o dict completo (preserva sinal quando resumo é vazio):

```python
# ANTES:
async def _selecionar_paragrafos_relevantes(
    paragrafos: list[str],
    candidato_titulo: str,
    candidato_resumo: str,
    paragrafos_embeddings: list,
    usuario_id: str,
    top_n: int = _TOP_N_PARAGRAFOS,
) -> list[tuple[int, str]]:
    consulta = f"{candidato_titulo}. {candidato_resumo}"[:1500]

# DEPOIS:
async def _selecionar_paragrafos_relevantes(
    paragrafos: list[str],
    candidato: dict,
    paragrafos_embeddings: list,
    usuario_id: str,
    top_n: int = _TOP_N_PARAGRAFOS,
) -> list[tuple[int, str]]:
    consulta = _texto_destino(candidato)[:1500]
```

E ajustar o chamador (~linha 95):

```python
# ANTES:
contexto_paragrafos = await _selecionar_paragrafos_relevantes(
    paragrafos,
    c.get("titulo", ""),
    c.get("resumo", ""),
    paragrafos_embeddings,
    usuario_id,
)

# DEPOIS:
contexto_paragrafos = await _selecionar_paragrafos_relevantes(
    paragrafos, c, paragrafos_embeddings, usuario_id,
)
```

---

## 4. Entrega 3 — NaN check em todos os cosines

### `backend/app/agents/workflow_inlinks.py:431`

```python
# ANTES:
try:
    cosine = float(dot(pilar_embedding, emb_c) / (norm(pilar_embedding) * norm(emb_c) + 1e-8))
except Exception:
    cosine = 0.0

# DEPOIS:
import math
try:
    cosine = float(dot(pilar_embedding, emb_c) / (norm(pilar_embedding) * norm(emb_c) + 1e-8))
    if math.isnan(cosine) or math.isinf(cosine):
        cosine = 0.0
except Exception:
    cosine = 0.0
```

(Import `math` no topo do módulo se ainda não existir.)

### `backend/app/agents/inlinks/inseridor.py:141` (batch validation)

```python
# ANTES:
try:
    cosine = float(dot(emb_ctx, emb_dst) / (norm(emb_ctx) * norm(emb_dst) + 1e-8))
except Exception:
    cosine = 0.0

# DEPOIS:
import math
try:
    cosine = float(dot(emb_ctx, emb_dst) / (norm(emb_ctx) * norm(emb_dst) + 1e-8))
    if math.isnan(cosine) or math.isinf(cosine):
        cosine = 0.0
except Exception:
    cosine = 0.0
```

### `backend/app/agents/inlinks/inseridor.py:198` (selecionar parágrafos)

```python
# ANTES:
try:
    cosine = dot(emb_consulta, emb_p) / (
        norm(emb_consulta) * norm(emb_p) + 1e-8
    )
except Exception:
    cosine = 0.0

# DEPOIS:
try:
    cosine = float(dot(emb_consulta, emb_p) / (
        norm(emb_consulta) * norm(emb_p) + 1e-8
    ))
    if math.isnan(cosine) or math.isinf(cosine):
        cosine = 0.0
except Exception:
    cosine = 0.0
```

Centralizar em helper se preferir DRY (`backend/app/core/embeddings.py`):

```python
def cosine_seguro(a, b) -> float:
    """Cosine similarity com fallback 0.0 para NaN/Inf/exceptions."""
    import math
    try:
        result = float(dot(a, b) / (norm(a) * norm(b) + 1e-8))
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception:
        return 0.0
```

E os 3 sites trocam para `cosine = cosine_seguro(a, b)`. Versão recomendada — reduz duplicação e fixa o comportamento num só lugar.

---

## 5. Entrega 4 — Fallback de threshold no Reranker

### `backend/app/agents/workflow_inlinks.py:node_match_rerank` (~linhas 470-483)

Atualmente o filtro é one-shot. Adicionar 1 retry com threshold relaxado quando o filtro descartar tudo:

```python
threshold = estado.get("threshold_score", 0.6)

# ... chamada ao reranker ...

filtered = [
    c for c in reranked
    if c.get("score_total", 0) >= threshold
    and c.get("score_semantico", 0) >= _MIN_SEMANTIC_SCORE
]

# Fallback: se o filtro descartou tudo (ou quase tudo),
# relaxar threshold uma vez para tentar atingir densidade alvo
if len(filtered) == 0 and len(reranked) > 0:
    threshold_relaxado = round(threshold * 0.85, 2)
    if threshold_relaxado < threshold:
        filtered_relax = [
            c for c in reranked
            if c.get("score_total", 0) >= threshold_relaxado
            and c.get("score_semantico", 0) >= _MIN_SEMANTIC_SCORE
        ]
        if filtered_relax:
            logger.info(
                "match_rerank: threshold relaxado de %.2f para %.2f, recuperando %d candidatos",
                threshold, threshold_relaxado, len(filtered_relax),
            )
            filtered = filtered_relax
            threshold = threshold_relaxado  # reflete o threshold real usado no log final

n_descartadas_piso = len(reranked) - len(filtered)
await publish_event(
    eid,
    "node_complete",
    "match_rerank",
    f"Top {len(filtered)} candidatos acima de {threshold} (piso semântico {_MIN_SEMANTIC_SCORE}; {n_descartadas_piso} descartadas pelo piso)",
)
```

**Decisão de não estender:** apenas 1 retry com 0.85x. Não cair em loop infinito de relaxamento — se mesmo a 0.85x não passar, é sinal de candidatas genuinamente irrelevantes.

---

## 6. Entrega 5 — Prefixo `[eid=...]` em logs do workflow

### `backend/app/agents/workflow_inlinks.py`

#### Estratégia

Adicionar um helper local que prefixa qualquer log com o `execucao_id` curto. Aplica em todos os `logger.info`/`logger.warning`/`logger.error` dos nodes que já têm `eid` em escopo.

#### a) Helper no topo

```python
def _log_prefix(eid: str) -> str:
    return f"[eid={eid[:8]}]"
```

#### b) Substituições principais

Em cada node, mudar:

```python
# ANTES:
logger.info("match_rerank: pilar_embedding len=%d candidatas_emb count=%d", len(pilar_embedding), len(candidatas_emb))

# DEPOIS:
logger.info("%s match_rerank: pilar_embedding len=%d candidatas_emb count=%d",
            _log_prefix(eid), len(pilar_embedding), len(candidatas_emb))
```

Aplica em todos os `logger.*` dentro de `node_*` que já têm `eid` definido (ver `grep -n "logger\." backend/app/agents/workflow_inlinks.py`).

#### c) Log do enriquecer

```python
logger.info(
    "%s enriquecer: pilar_embedding=%s (%d chunks consolidados via mean pooling)",
    _log_prefix(eid),
    "OK" if pilar_embedding else "NONE",
    len(pilar_chunk_embeddings),
)
```

E o resumo final:

```python
logger.info("%s enriquecer: candidatas_embeddings=%d (%s)", _log_prefix(eid), n_emb, msg)
```

#### d) `_finalizar_sucesso_inlinks`

```python
logger.info("%s inlinks status=concluida sem creditos (0 candidatas validas)", _log_prefix(execucao_id))
logger.info("%s inlinks: 0 aplicados de %d validas, cobrando so URLs (custo=%d, sem base)",
            _log_prefix(execucao_id), n_processadas, custo)
logger.info("%s inlinks status=concluida creditos=%d", _log_prefix(execucao_id), custo)
```

#### e) `executar_workflow_inlinks` (catch externo)

```python
logger.error("%s Workflow inlinks falhou: %s", _log_prefix(execucao_id), e)
```

**Resultado:** `grep "[eid=abc12345]" /tmp/worker.log` isola uma execução completa em 1 comando.

---

## 7. Verificação ponta a ponta

### 7.1 Sanidade de import

```bash
grep -n "math.isnan\|cosine_seguro\|_texto_destino\|_log_prefix\|cliente_id_val" backend/app | head -30
```

### 7.2 Restart

```bash
pkill -f "uvicorn app.main"; pkill -f "arq app.worker"
cd backend && nohup python3 -u -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
cd backend && nohup python3 -u -m arq app.worker.WorkerSettings > /tmp/worker.log 2>&1 &
sleep 3
curl -sf -o /dev/null -w "Backend: %{http_code}\n" http://localhost:8000/health
```

### 7.3 Cenários

1. **Execução com cliente associado:** após uma execução cold, `SELECT cliente_id FROM conteudos_vetores WHERE execucao_id = '...' LIMIT 1` deve retornar o UUID do cliente (não NULL).
2. **Execução em reuso (vetores antigos com `resumo=NULL`):** worker.log mostra Validação D usando `titulo + categoria + palavras_chave`. Inlinks aplicados sobem (não cai mais tudo em `sugestao_manual`).
3. **NaN forçado:** simular embedding zerado — comparações continuam funcionando, cosine = 0.0.
4. **Reranker filtra tudo:** worker.log mostra `threshold relaxado de 0.60 para 0.51, recuperando N candidatos`. Execução conclui com inlinks recuperados.
5. **Log isolado:** `grep "[eid=abc12345]" /tmp/worker.log` traz todas as linhas de uma execução específica em ordem cronológica.

### 7.4 SQL de auditoria

```sql
-- Conferir que cliente_id passou a ser populado
SELECT id, usuario_id, cliente_id, criado_em
FROM conteudos_vetores
WHERE criado_em > now() - interval '1 day'
ORDER BY criado_em DESC LIMIT 10;
```

---

## 8. Fora de escopo

- **Backfill de `resumo`/`categoria` em vetores antigos** (decisão de produto: deletar com `UPDATE ativo=false WHERE resumo IS NULL` força regeneração na próxima execução). Não obrigatório porque o fallback da Entrega 2 já mitiga.
- **Restringir query de reuso por `cliente_id`** (multi-cliente real). Comentário inline marca onde mexer quando o produto exigir.
- **Cache de embeddings deduplicado entre tenants** (eficiência, problema A2 da revisão original).
- **Refactor para retry granular por node LangGraph** (cada `_invoke_llm` já tem retry via `chamada_llm_mensagem_com_retry`).
- **Reduzir número de agentes LLM** (problema A4) — Cleaner e Formatador opt-in via config seria refactor; manter como está.

---

## 9. Riscos

- **Entrega 1 (`cliente_id`)**: vetores antigos continuam com `cliente_id=NULL`. Se algum código consumir essas linhas e filtrar por cliente, vai ignorá-las. Mitigação: backfill manual via UPDATE quando o produto formalizar multi-cliente.
- **Entrega 2 (`_texto_destino` fallback)**: o fallback pode ficar muito curto se categoria + palavras_chave também estiverem vazias. Mitigação: cai para `titulo` puro, comportamento idêntico ao atual.
- **Entrega 3 (`cosine_seguro`)**: se introduzir o helper, fazer import sem ciclo. `numpy.dot` + `numpy.linalg.norm` já estão importados nos sites de uso.
- **Entrega 4 (threshold relaxado)**: pode passar candidatos ruins se o reranker scorou tudo baixo por motivo legítimo (pilar pequeno, candidatas tangenciais). Mitigação: piso `_MIN_SEMANTIC_SCORE = 0.40` ainda atua; relaxar só `threshold_total`, não o piso semântico.
- **Entrega 5 (logs com prefixo)**: muitas substituições mecânicas. Risco de typo. Mitigação: testar uma execução real, conferir `grep "[eid=" /tmp/worker.log` antes/depois.

---

## 10. Arquivos críticos

### Backend — alterados
- `backend/app/agents/workflow_inlinks.py` — `EstadoInlinks` (cliente_id), `executar_workflow_inlinks` (propagação), `node_enriquecer` (insert + reuso), `node_match_rerank` (fallback threshold), todos os `logger.*` com prefixo, NaN check no cosine.
- `backend/app/agents/inlinks/inseridor.py` — helper `_texto_destino`, uso em batch validation e `_selecionar_paragrafos_relevantes`, NaN check.
- `backend/app/core/embeddings.py` — adicionar `cosine_seguro()` (recomendado).

### Backend — sem mudança
- `backend/app/models/conteudo_vetor.py` — campo `cliente_id` já existe; só popular nos inserts.
- Não há migration nova.

### Frontend
- Nenhuma alteração.

---

## 11. Verificação (sumário)

1. Grep confirma `cliente_id_val`, `_texto_destino`, `cosine_seguro`/`math.isnan`, `_log_prefix` aplicados.
2. Restart sem erro.
3. Execução cold: `cliente_id` populado em `conteudos_vetores`.
4. Execução reuso: Validação D não derruba tudo para `sugestao_manual`.
5. Reranker em pilar difícil: threshold relaxado uma vez antes de desistir.
6. Logs isolados por `eid` via grep.
