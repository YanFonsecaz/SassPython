# SPEC — Inlinks: corrigir bugs encontrados após `SPEC_Inlinks_Qualidade_Match_e_Julgamento`

**Status:** pendente
**Escopo:** backend (modelo + migration + scraper + workflow + service) + frontend (mensagens de erro)
**Crédito:** muda — não cobrar quando `n_candidatas_validas == 0`
**Depende de:** `SPEC_Inlinks_Qualidade_Match_e_Julgamento.md` aplicada

---

## Contexto

Durante revisão pós-aplicação da SPEC anterior, 3 bugs foram identificados em código vivo e em log de execução real (`656fff7c`, 13/05/2026 11:41):

### Bug 1 (CRÍTICO) — Workflow lê colunas inexistentes em `ConteudoVetor`

`backend/app/agents/workflow_inlinks.py:258-259` faz:
```python
"resumo": existing_rows[0].resumo or "",
"categoria": existing_rows[0].categoria or "",
```

Mas `backend/app/models/conteudo_vetor.py` **não tem `resumo` nem `categoria`** (modelo só tem `tipo`, `intencao`, `palavras_chave`, `atividades`, `embedding`, …). A SPEC anterior assumiu que esses campos existiam.

**Consequência operacional:**
- Primeira execução de um pilar/candidata novo passa pelo caminho **cold** (`else` em workflow:279) — funciona.
- Qualquer re-execução do mesmo pilar (html_hash bate) cai no caminho **reuso** (`if existing_rows:` em workflow:251) — `AttributeError` silencioso, capturado pelo handler externo do workflow, executado termina com markdown vazio. **Cobra 15 créditos base por nada.**
- Como reuso de embedding é o caminho comum em qualquer teste/iteração, a ferramenta está efetivamente travada em modo "primeira execução".

### Bug 2 (UX) — Mensagem "Host bloqueado" engana o usuário em falha de DNS

`backend/app/core/scraper.py:76-77` em `_is_private_host`:
```python
except socket.gaierror:
    return True   # ← trata DNS fail como host privado
```

E `:153-155`:
```python
if _is_private_host(parsed.hostname):
    resultado.erro = "Host bloqueado (IP privado ou loopback)"
```

Confirmado no log: usuário digitou `www.agilizecontabilidade.com.br` (domínio inexistente — `dig` e `curl` confirmam: NXDOMAIN). DNS falhou → função retorna `True` → erro mostra "Host bloqueado", como se o sistema tivesse banido o host de propósito.

**Consequência operacional:**
- Usuário não entende por que a URL não foi processada.
- Não há sinalização para corrigir typo (sugerir domínio existente).
- Telemetria fica poluída: "Host bloqueado" cobre dois cenários muito diferentes (SSRF defesa vs. domínio inexistente).

### Bug 3 (financeiro) — Cobra `CUSTO_BASE_INLINKS` mesmo com `n_candidatas_validas == 0`

`backend/app/agents/workflow_inlinks.py:_finalizar_sucesso_inlinks` chama `ferramenta_service.calcular_custo_inlinks(n_processadas)` com `n_processadas == 0` quando todas as candidatas falham. Custo base (15) é cobrado mesmo assim. Execução `656fff7c` debitou 15 créditos com `n_candidatas_validas=0, n_aplicadas=0, top_scores=[]`.

**Consequência:**
- Usuário paga por uma execução que produziu literalmente nada (markdown vazio, zero inlinks).
- Em produção isso vira chamado de suporte e perda de confiança.

---

## 1. Resumo

Quatro entregas:

| # | Entrega | Arquivos | Esforço |
|---|---|---|---|
| **A** | Adicionar `resumo` e `categoria` em `ConteudoVetor` + migration 0010 + popular nos inserts + ler corretamente em reusos | `conteudo_vetor.py`, `migrations/0010_*.py`, `workflow_inlinks.py` | 15 min |
| **B** | Scraper distingue DNS fail de bloqueio real + mensagem mais clara | `scraper.py` | 5 min |
| **C** | Não cobrar créditos quando `n_candidatas_validas == 0` (apenas marca execução como concluída com aviso) | `workflow_inlinks.py` | 5 min |
| **D** | Limpezas: linha duplicada `llm_provider` em `config.py`, log duplicado em `node_enriquecer`, default `threshold_score` backend para `0.6` | `config.py`, `workflow_inlinks.py` | 2 min |

Total: ~25 min. Pode ser 1 PR com 4 commits separados.

---

## 2. Entrega A — Adicionar `resumo` e `categoria` em `ConteudoVetor`

### A.1 Modelo

`backend/app/models/conteudo_vetor.py` — adicionar após `atividades` (linha 28):

```python
resumo: Mapped[str | None] = mapped_column(Text, nullable=True)
categoria: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

### A.2 Migration

Criar `backend/migrations/versions/0010_conteudos_vetores_resumo_categoria.py`:

```python
"""adicionar resumo e categoria em conteudos_vetores

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conteudos_vetores", sa.Column("resumo", sa.Text(), nullable=True))
    op.add_column("conteudos_vetores", sa.Column("categoria", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("conteudos_vetores", "categoria")
    op.drop_column("conteudos_vetores", "resumo")
```

### A.3 Popular no insert (caminho cold)

`backend/app/agents/workflow_inlinks.py:313-330` — adicionar `resumo` e `categoria` ao `ConteudoVetor(...)`:

```python
vetor = ConteudoVetor(
    usuario_id=uid,
    execucao_id=eid,
    titulo=titulo,
    conteudo=ch.texto,
    tipo=meta.tipo,
    intencao=meta.intencao,
    palavras_chave=meta.palavras_chave,
    atividades=meta.entidades,
    embedding=emb,
    url_canonica=url_c,
    chunk_index=ch.ordem,
    tipo_recurso="pilar" if item["is_pilar"] else "candidata",
    html_hash=html_hash,
    tokens=ch.tokens,
    score_base=0.0,
    ativo=True,
    resumo=meta.resumo,           # ← novo
    categoria=meta.categoria,     # ← novo
)
```

### A.4 Ler corretamente em reuso

`backend/app/agents/workflow_inlinks.py:258-259` — já está correto após a migration:
```python
"resumo": existing_rows[0].resumo or "",
"categoria": existing_rows[0].categoria or "",
```

**Atenção:** linhas que estão dentro do bloco `if existing_rows:` (reuso). Como vetores antigos foram inseridos sem essas colunas, elas voltam `NULL`. O `or ""` já cobre. Nenhuma alteração de código adicional — só a migration desbloqueia o acesso ao atributo.

### A.5 Backfill (opcional, fora de escopo desta SPEC)

Vetores antigos ficam com `resumo=NULL` e `categoria=NULL`. Como a SPEC anterior introduziu essa dependência só agora, o reranker simplesmente recebe vazio nesses casos — o pior é uma execução sem metadados estruturados (volta ao comportamento anterior à SPEC anterior, mas sem crash). **Não há regressão.**

Para repor metadados em vetores antigos, basta deletar os registros (próxima execução re-extrai). Decisão do usuário, não obrigatório.

---

## 3. Entrega B — Mensagem de erro do scraper mais clara

### `backend/app/core/scraper.py`

Refatorar `_is_private_host` (linhas 66-78) para distinguir DNS fail de bloqueio real:

```python
class HostCheckResult:
    OK = "ok"
    DNS_FAIL = "dns_fail"
    BLOCKED = "blocked"


def _check_host(hostname: str) -> str:
    import socket

    if not hostname:
        return HostCheckResult.DNS_FAIL
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return HostCheckResult.DNS_FAIL
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                return HostCheckResult.BLOCKED
    return HostCheckResult.OK
```

E em `scrape_url` (linha ~153), substituir:

```python
# ANTES:
if _is_private_host(parsed.hostname):
    resultado.falhou = True
    resultado.erro = "Host bloqueado (IP privado ou loopback)"
    return resultado

# DEPOIS:
host_status = _check_host(parsed.hostname)
if host_status == HostCheckResult.DNS_FAIL:
    resultado.falhou = True
    resultado.erro = "Domínio não encontrado (DNS falhou). Verifique se a URL está correta."
    return resultado
if host_status == HostCheckResult.BLOCKED:
    resultado.falhou = True
    resultado.erro = "Host bloqueado (IP privado ou loopback)"
    return resultado
```

Manter `_is_private_host` como alias backward-compat (delega ao `_check_host` e retorna `True` para qualquer não-OK), ou remover se nenhum outro arquivo usa.

**Verificar uso externo:** `grep -rn "_is_private_host" backend/app | head` — se só usado dentro do `scraper.py`, remover.

---

## 4. Entrega C — Não cobrar créditos quando `n_candidatas_validas == 0`

### `backend/app/agents/workflow_inlinks.py:_finalizar_sucesso_inlinks` (linhas ~764-798)

Antes de chamar `calcular_custo_inlinks` e debitar, checar se a execução foi efetivamente útil:

```python
async def _finalizar_sucesso_inlinks(db, execucao_id: str, resultado_json: dict) -> None:
    from datetime import datetime
    from app.services import credito_service, ferramenta_service

    execucao = await ferramenta_service.buscar_execucao(db, execucao_id)
    if not execucao:
        raise ValueError(f"Execucao {execucao_id} nao encontrada")

    n_processadas = resultado_json.get("n_candidatas_validas", 0)

    # Sem candidatas válidas → marca como concluída sem cobrar
    if n_processadas <= 0:
        execucao.status = "concluida"
        execucao.creditos_cobrados = 0
        execucao.erro_msg = "Nenhuma URL candidata pôde ser processada (DNS, robots.txt ou bloqueio)"
        execucao.resultado_json = resultado_json
        execucao.concluida_em = datetime.utcnow()
        await db.flush()
        logger.info("execucao_id=%s inlinks status=concluida creditos=0 (n_candidatas_validas=0)", execucao_id)
        return

    custo = ferramenta_service.calcular_custo_inlinks(n_processadas)
    saldo_ok = await credito_service.verificar_saldo_suficiente(db, str(execucao.usuario_id), custo)
    if not saldo_ok:
        execucao.status = "falhou"
        execucao.erro_msg = "Saldo insuficiente"
        execucao.concluida_em = datetime.utcnow()
        await db.flush()
        return

    await credito_service.debitar_creditos(
        db,
        str(execucao.usuario_id),
        custo,
        descricao=f"Inlinks automaticos: {custo} creditos (base={ferramenta_service.CUSTO_BASE_INLINKS}, urls={n_processadas})",
        ferramenta="inlinks_automaticos",
        execucao_id=execucao_id,
    )

    execucao.status = "concluida"
    execucao.creditos_cobrados = custo
    execucao.resultado_json = resultado_json
    execucao.concluida_em = datetime.utcnow()
    await db.flush()
    logger.info("execucao_id=%s inlinks status=concluida creditos=%d", execucao_id, custo)
```

**Comportamento esperado:**
- Execução com 0 candidatas válidas → status `concluida`, `creditos_cobrados=0`, `erro_msg` informativo.
- Frontend já exibe `erro_msg` na UI da execução; nenhuma mudança de UI necessária.
- Quem testa pode iterar sem queimar créditos por URLs com typo.

---

## 5. Entrega D — Limpezas

### D.1 `backend/app/config.py:53`

Remover a linha duplicada `llm_provider: str = "zhipuai"`. Já está em `:47`.

### D.2 `backend/app/agents/workflow_inlinks.py:393`

O log de `pilar_embedding=...` aparece duas vezes (linhas 372-376 e 393). Remover o segundo bloco (linha 393), mantendo apenas o do mean pooling, que é mais informativo.

### D.3 `backend/app/agents/workflow_inlinks.py:722`

Trocar `entrada.get("threshold_score", 0.5)` para `entrada.get("threshold_score", 0.6)`. Alinha com o default do frontend e evita confusão se algum chamador externo (testes, API direta) não mandar o campo.

Mesma troca em `node_match_rerank` linha 455 (`estado.get("threshold_score", 0.5)`).

---

## 6. Verificação ponta a ponta

### 6.1 Migration

```bash
cd backend && alembic upgrade head
# Verificar:
docker exec -i seo_saas_postgres psql -U postgres -d seo_saas -c "\d conteudos_vetores" | grep -E "resumo|categoria"
# Deve mostrar:
#  resumo    | text                  |
#  categoria | character varying(100)|
```

### 6.2 Restart

```bash
pkill -f "uvicorn app.main"; pkill -f "arq app.worker"
cd backend && nohup python3 -u -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
cd backend && nohup python3 -u -m arq app.worker.WorkerSettings > /tmp/worker.log 2>&1 &
sleep 3
curl -sf -o /dev/null -w "Backend: %{http_code}\n" http://localhost:8000/health
```

### 6.3 Execução E2E — reuso

Rodar a **mesma execução** que produziu `d7b50a52` (CNAE varejo + 4 candidatas `agilize.com.br`). Como o html_hash bate com vetores existentes:

- Caminho **reuso** é tomado → `existing_rows[0].resumo` e `.categoria` devem ler `NULL` (vetores antigos) sem crash.
- Worker log mostra: `Reuso completo: N URLs do banco vetorial` sem `AttributeError`.
- `pilar_metadados` chega ao reranker com `resumo` e `categoria` vazios — log do reranker mostra `Categoria: ` em branco. Aceitável: reranker só pode usar título + palavras_chave + trecho do pilar. Sem regressão vs. antes.

### 6.4 Execução E2E — cold (URLs novas)

Rodar com URLs novas (de outro blog) para forçar caminho cold:

- Worker log mostra `Gerando embeddings + metadados (cold) para N URLs`.
- INSERTs em `conteudos_vetores` agora populam `resumo` e `categoria` (verificar com `SELECT url_canonica, resumo, categoria FROM conteudos_vetores ORDER BY criado_em DESC LIMIT 5`).
- Após esta execução, re-rodar a mesma — agora cai em reuso E com `resumo`/`categoria` preenchidos. Reranker recebe metadados estruturados completos. Confirmação: `grep "Categoria:" /tmp/worker.log` deve mostrar valores não-vazios.

### 6.5 Erro de DNS

Submeter execução com URL inexistente (ex.: `https://www.agilizecontabilidade.com.br/blog/xyz`):

- Worker log: `extrair_candidatas: ... -> FALHOU: Domínio não encontrado (DNS falhou). Verifique se a URL está correta.`
- Resultado da execução: `status=concluida`, `creditos_cobrados=0`, `erro_msg` com a mensagem nova.
- Conta de créditos do usuário NÃO foi debitada — confirmar com `SELECT saldo_plano FROM contas_creditos WHERE usuario_id=...` antes/depois.

### 6.6 Sanidade

```bash
grep -rn "_is_private_host\|HostCheckResult\|resumo\|categoria" backend/app | head -20
grep -n "llm_provider" backend/app/config.py     # deve aparecer 1 vez só
```

---

## 7. Fora de escopo

- Backfill de `resumo`/`categoria` em vetores antigos (limpar e re-extrair é decisão do usuário).
- Validação de URL no frontend antes de submeter (sugerir typo correction). Pode ser uma melhoria de UX posterior.
- Refund automático de créditos para execuções passadas que cobraram com `n_candidatas_validas == 0` (decisão de negócio).

---

## 8. Riscos

- **Vetores antigos com `resumo=NULL`**: o reranker recebe vazio. Não há regressão — antes da SPEC anterior não havia esse campo. O ganho da Entrega C da SPEC anterior só aparece em vetores novos. Aceitável.
- **`_is_private_host` ainda usado em algum lugar**: grep antes de remover; manter como alias se necessário.
- **Mudança em `_finalizar_sucesso_inlinks`**: se `n_processadas` for falsamente zero (bug no extrator que não reporta sucessos), pular cobrança em execução real. Mitigação: linha de log explícita facilita debug; pode-se monitorar via SELECT por execucao com `creditos_cobrados=0`.

---

## 9. Arquivos críticos

### Backend — alterados
- `backend/app/models/conteudo_vetor.py` — adicionar `resumo`, `categoria`.
- `backend/app/agents/workflow_inlinks.py` — popular `resumo`/`categoria` no insert; pular cobrança em `n_candidatas_validas==0`; remover log duplicado; default `threshold_score=0.6`.
- `backend/app/core/scraper.py` — `_check_host` que distingue DNS_FAIL / BLOCKED / OK; mensagem específica para DNS.
- `backend/app/config.py` — remover linha duplicada `llm_provider`.

### Backend — novo
- `backend/migrations/versions/0010_conteudos_vetores_resumo_categoria.py`.

### Frontend
- Nenhuma alteração obrigatória. UI da execução já exibe `erro_msg` quando presente.

---

## 10. Verificação (sumário)

1. `alembic upgrade head` aplica migration 0010 sem erro.
2. Restart de uvicorn + arq sem `AttributeError` no log.
3. E2E com URLs reusadas: workflow conclui sem crash, reranker recebe `resumo: ""` em vetores antigos.
4. E2E com URLs novas: INSERTs populam `resumo` e `categoria`; re-execução posterior usa essas colunas via reuso.
5. URL com DNS inexistente: mensagem clara, status `concluida`, `creditos_cobrados=0`.
