# SPEC — Inlinks: destravar re-extração de vetores (constraint condicional) + relaxar cosine fallback

**Status:** pendente
**Escopo:** backend (migration nova + `inseridor.py`)
**Crédito:** não muda
**Depende de:** `SPEC_Inlinks_UX_Enriquecedor_e_Tolerancia_Semantica.md` aplicada

---

## Contexto

Teste E2E #6 (`a50ce794`, 13/05/2026) executou cold path forçado (`UPDATE ativo=false` nos vetores Agilize) para validar o Enriquecedor melhorado. **Resultado expôs 2 problemas estruturais:**

### Problema 1 — Índice único bloqueia re-inserção

```sql
CREATE UNIQUE INDEX uniq_vetor_url_chunk ON conteudos_vetores
USING btree (usuario_id, url_canonica, chunk_index)
WHERE (url_canonica IS NOT NULL);
```

O índice **não condiciona em `ativo=true`**. Registros antigos com `ativo=false` continuam ocupando o slot. Cold path tenta inserir novo vetor com (usuario_id, url, chunk_idx) já usados → `IntegrityError`. SAVEPOINT aborta inserção do chunk; `try/except` busca `existing.ativo=True` mas não acha (porque o existente está inativo) → retorna sem persistir.

**Impacto**: a Entrega 2 da SPEC anterior (Enriquecedor mais agressivo extraindo "dropshipping", "shopify", etc) **não pode ser validada** porque as palavras_chave novas não chegam ao banco. Workflow roda em memória mas reuso futuro continua com palavras_chave antigas pobres.

Confirmado:
```sql
SELECT count(*) FROM conteudos_vetores WHERE url_canonica LIKE '%agilize%' AND ativo=true;
-- 0
```

### Problema 2 — Cosine fallback rejeita sinônimos técnicos legítimos

E2E #6 mostrou: cosine entre "dropshipping" e "Como abrir uma loja virtual: guia completo e prático" = **0.26**. Threshold atual `_MIN_SEMANTIC_FALLBACK = 0.55` rejeita.

`text-embedding-3-small` é **bi-encoder genérico** — não captura relação técnica entre "dropshipping" (modalidade de e-commerce) e "loja virtual" (categoria). Termos próximos no domínio aparecem **distantes no espaço de embedding** porque o modelo foi treinado em corpus geral.

**Tradeoff**: threshold 0.55 é seguro contra alucinação genuína mas mata sinônimos válidos. Threshold 0.30 captura "dropshipping ≡ loja virtual" mas pode aceitar relações irrelevantes.

### Estratégia: defesa em duas camadas

1. **Camada primária** (Entrega A): destravar Enriquecedor melhorado. Se "dropshipping" estiver em `palavras_chave` extraídas (Entrega 2 da SPEC anterior), check léxico passa direto sem precisar de cosine.
2. **Camada secundária** (Entrega B): relaxar `_MIN_SEMANTIC_FALLBACK` para 0.40 — captura sinônimos técnicos não capturados pelo Enriquecedor. Threshold ainda exclui claras alucinações (cosine < 0.40).

Decisão de não trocar para cross-encoder real (Voyage/Cohere) agora: adiciona dependência paga + refactor grande; aguardar até confirmar que A+B não bastam.

### Resultado esperado

Após esta SPEC:
- Re-extração de vetores funciona (cold path persiste, reusos futuros usam palavras_chave novas).
- Em pilar de "ganhar dinheiro" × candidatas Agilize, a loja-virtual deve **voltar a ser aplicada** (via palavras_chave novas OU via cosine 0.40 mais permissivo).
- Imobiliária, restaurante, agência-viagens **continuam recusados** (nenhum termo específico nem sinônimo no pilar genérico).

---

## 1. Resumo

Duas entregas. ~15 min total.

| # | Entrega | Arquivo | Esforço |
|---|---|---|---|
| **A** | Migration 0011 — tornar índice único condicional em `ativo=true` | `migrations/versions/0011_*.py` | 10 min |
| **B** | Relaxar `_MIN_SEMANTIC_FALLBACK` de 0.55 para 0.40 | `inseridor.py` | 1 min |

---

## 2. Entrega A — Índice único condicional em `ativo=true`

### A.1 Migration

Criar `backend/migrations/versions/0011_uniq_vetor_url_chunk_ativo.py`:

```python
"""tornar uniq_vetor_url_chunk condicional em ativo=true

Permite re-inserir vetor para a mesma (usuario_id, url_canonica, chunk_index)
quando o registro antigo foi desativado (ativo=false). Necessário para
re-extração via Enriquecedor melhorado.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-14
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uniq_vetor_url_chunk", table_name="conteudos_vetores")
    op.create_index(
        "uniq_vetor_url_chunk",
        "conteudos_vetores",
        ["usuario_id", "url_canonica", "chunk_index"],
        unique=True,
        postgresql_where="url_canonica IS NOT NULL AND ativo = true",
    )


def downgrade() -> None:
    op.drop_index("uniq_vetor_url_chunk", table_name="conteudos_vetores")
    op.create_index(
        "uniq_vetor_url_chunk",
        "conteudos_vetores",
        ["usuario_id", "url_canonica", "chunk_index"],
        unique=True,
        postgresql_where="url_canonica IS NOT NULL",
    )
```

### A.2 Sem mudança de código no workflow

O workflow já faz `WHERE ativo=true` no SELECT de reuso (`workflow_inlinks.py:244`) e o `try/except IntegrityError` continua valendo como rede de segurança para corridas concorrentes legítimas (mesmo usuário lendo a mesma URL em duas execuções paralelas).

A migration sozinha resolve: registros com `ativo=false` deixam de "ocupar slot", inserções cold path passam.

### A.3 Validação

```bash
cd backend && alembic upgrade head
docker exec seo_saas_postgres psql -U postgres -d seo_saas -c "
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename='conteudos_vetores' AND indexname='uniq_vetor_url_chunk'"
# Deve mostrar WHERE (url_canonica IS NOT NULL AND ativo = true)
```

---

## 3. Entrega B — Relaxar cosine fallback

### `backend/app/agents/inlinks/inseridor.py:23`

```python
# ANTES:
_MIN_SEMANTIC_FALLBACK = 0.55

# DEPOIS:
_MIN_SEMANTIC_FALLBACK = 0.40
```

### Justificativa

Medições empíricas com `text-embedding-3-small`:
- "dropshipping" vs "Como abrir uma loja virtual..." = **0.26** (relação técnica real, embedding falha)
- "que tipo de negócio" vs "Como abrir uma imobiliária..." = **0.49** (link forçado, cosine alto enganoso)
- "o investimento cresce" vs "Como abrir um restaurante..." = **0.23** (genuinamente desconectado)

Não há threshold no `text-embedding-3-small` que separe (1) e (2) com folga. **0.40 é compromisso**:
- Aceita (1) **se** "dropshipping" estiver em palavras_chave (camada primária) — então cosine fallback nem dispara.
- Captura sinônimos técnicos médios (cos 0.40-0.55).
- Rejeita relações tangenciais (cos < 0.40) e claros pareamentos genéricos puros sem suporte léxico.

Para o caso `que tipo de negócio → imobiliária` (cos=0.49 > 0.40 — aceitaria!), a defesa fica em **outra camada**: validação léxica de stopwords genéricas em `_termos_validos_destino` rejeita "negócio" como palavra-chave válida. Se LLM tentar "imobiliária" como palavra-chave, falha o check de overlap léxico com a âncora (não há "imobiliária" em "que tipo de negócio devo abrir").

---

## 4. Verificação ponta a ponta

### 4.1 Aplicar migration

```bash
cd backend && alembic upgrade head
docker exec seo_saas_postgres psql -U postgres -d seo_saas -c "
SELECT indexdef FROM pg_indexes WHERE indexname='uniq_vetor_url_chunk'"
```

Esperado: `... WHERE ((url_canonica IS NOT NULL) AND (ativo = true))`

### 4.2 Reativar / desativar para forçar cold path

```sql
UPDATE conteudos_vetores SET ativo=false
WHERE usuario_id='b9afa7ad-12c7-40b8-a4a7-3d0bcd4f1f31'
  AND url_canonica LIKE '%agilize.com.br%abrir-sua-empresa%';
```

### 4.3 Restart worker

```bash
pkill -f "arq app.worker"
cd backend && nohup python3 -u -m arq app.worker.WorkerSettings > /tmp/worker.log 2>&1 &
sleep 3
```

### 4.4 Re-rodar E2E

Mesmo pilar e candidatas Agilize.

**Confirmações pós-execução**:

```sql
-- Confirmar que vetores novos foram inseridos com ativo=true
SELECT count(*), tipo_recurso FROM conteudos_vetores
WHERE usuario_id='b9afa7ad-...' AND ativo=true
  AND url_canonica LIKE '%agilize%abrir-sua-empresa%'
GROUP BY tipo_recurso;
-- Esperado: count > 0 para pilar + candidatas

-- Conferir palavras_chave novas (Entrega 2 da SPEC anterior aplicada)
SELECT url_canonica, palavras_chave
FROM conteudos_vetores
WHERE ativo=true AND url_canonica LIKE '%loja-virtual%' AND chunk_index=0;
-- Esperado: ["loja virtual", "e-commerce", "dropshipping", "marketplace", "shopify", "CNPJ", ...]
```

**Resultado esperado dos inlinks**:

| Candidata | Status | Por quê |
|---|---|---|
| loja-virtual | **aplicado** | Enriquecedor agora popula "dropshipping" em palavras_chave → validação léxica passa direto |
| imobiliária | recusado/sugestao_manual | Termos: imobiliária, imóveis, corretagem — nenhum no pilar |
| restaurante | recusado/sugestao_manual | Termos: restaurante, alimentação, cozinha — depende do pilar |
| agência-viagens | recusado/sugestao_manual | Termos: viagens, turismo, agência — depende do pilar |

Densidade ideal: 1–2 aplicados. UX clara ("Nenhum link orgânico...") quando 0 aplicados.

---

## 5. Fora de escopo

- **Cross-encoder real (Voyage/Cohere)** — aguardar se A+B não bastam.
- **Deletar registros antigos com ativo=false** — não obrigatório agora; podem servir para auditoria. SQL manual quando desejar limpar: `DELETE FROM conteudos_vetores WHERE ativo=false AND criado_em < now() - interval '30 days'`.
- **Re-extrair vetores antigos automaticamente** — decisão de produto, scripts ad-hoc.

---

## 6. Riscos

- **Migration drop+create de índice**: tabela pode ficar com índice ausente por milissegundos. Em produção com tráfego, considerar `CONCURRENTLY` (mas Alembic não dá direto sem `op.execute(...)`). Para volume atual (dev), seguro.
- **Cosine 0.40 mais permissivo**: pode aceitar relações tangenciais. Mitigação: validação léxica (stopwords + overlap âncora) é a defesa principal; cosine fallback é só segunda camada.
- **Inserts cold path em volume**: se vários usuários re-extrair simultaneamente, IntegrityError pode aparecer por corrida real (não por ativo=false). O `try/except` existente continua tratando.

---

## 7. Arquivos críticos

### Backend — novo
- `backend/migrations/versions/0011_uniq_vetor_url_chunk_ativo.py` — drop + recreate do índice com `WHERE ativo=true`.

### Backend — alterado
- `backend/app/agents/inlinks/inseridor.py:23` — `_MIN_SEMANTIC_FALLBACK = 0.40` (era 0.55).

### Frontend / Schemas
- Nenhuma alteração.

---

## 8. Verificação (sumário)

1. `alembic upgrade head` aplica migration sem erro.
2. `pg_indexes` mostra índice com `WHERE (...AND ativo=true)`.
3. Após `UPDATE ativo=false` + restart + E2E, vetores novos persistem com `ativo=true`.
4. `palavras_chave` da loja-virtual nova inclui "dropshipping" (validação do Enriquecedor da SPEC anterior).
5. loja-virtual volta a ser **aplicado** no resultado.
6. Imobiliária, restaurante, agência-viagens continuam recusados (corretos).
