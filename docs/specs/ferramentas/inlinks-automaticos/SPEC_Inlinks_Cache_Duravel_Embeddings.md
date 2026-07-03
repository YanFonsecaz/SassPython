# SPEC — Inlinks: cache durável de embeddings (sobreviver à evicção do Redis de 25MB)

**Status:** ✅ implementada (2026-07-03) — migration `0022`, L1→L2→API em `core/embeddings.py`,
limpeza semanal em `scheduler.py`. Telemetria L1/L2/API sai nos **logs** por chamada de batch;
a exposição no funil de `resultado_json` (§3) fica para iteração futura
**Escopo:** backend (`core/embeddings.py`, migration nova, scheduler) — transparente para as ferramentas
**Crédito:** não muda (reduz custo de API de embeddings)
**Depende de:** nada

---

## Contexto (correção de diagnóstico)

Ao contrário do que a análise inicial supôs, `gerar_embeddings_batch` **já consulta cache por
texto** (`embeddings.py:42-58`: Redis, chave `emb:{provider}:{modelo}:{dims}:{sha256}`, TTL 30
dias) — parágrafos repetidos entre execuções não são re-embedados *enquanto a chave viver*.

O problema real é **durabilidade**: produção usa o Key-Value free do Render (**25MB**). Uma
execução de inlinks gera dezenas de chaves de ~13KB (1024 floats em JSON) — o cache inteiro
comporta ~2 mil textos e sofre evicção contínua conforme outras chaves (scrape 7d, robots 24h,
buckets de rate limit) disputam o espaço. Na prática o cache de embeddings é efêmero em produção,
e cada re-execução paga API de novo.

## Mudanças

### 1. Camada durável em Postgres (L2 atrás do Redis)

Migration nova — tabela enxuta, **sem** FK com conteúdo (é cache, não dado de domínio):

```sql
CREATE TABLE embeddings_cache (
  chave VARCHAR(120) PRIMARY KEY,     -- mesma chave do Redis (provider:modelo:dims:sha256)
  embedding VECTOR(1024) NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  usado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Fluxo de leitura em `gerar_embeddings_batch` (e `gerar_embedding_single`):
1. Redis (rápido) → 2. Postgres em lote (`SELECT ... WHERE chave IN (...)`, 1 query para todos os
misses; re-hidrata o Redis; atualiza `usado_em` em lote) → 3. API (grava nas duas camadas).

- pgvector armazena binário (~4KB/linha vs ~13KB do JSON) — 10 mil textos ≈ 40MB no Postgres
  (Supabase free = 500MB; aceitável com limpeza).
- Falha do Postgres no caminho de cache = log warning + segue para API (cache nunca derruba
  execução — mesmo contrato fail-soft do Redis hoje).

### 2. Limpeza por uso

Job no scheduler existente (`app/scheduler.py`): semanalmente, `DELETE FROM embeddings_cache
WHERE usado_em < NOW() - INTERVAL '90 days'` + teto de segurança (se tabela > N linhas, apagar
as mais antigas por `usado_em`). Settings: `embeddings_cache_ttl_dias=90`,
`embeddings_cache_max_linhas=50000`.

### 3. Telemetria

Estender o log existente ("embeddings cache: X/Y hits") para separar hits L1/L2 e expor os
contadores no funil das execuções de inlinks (`n_emb_cache_l1`, `n_emb_cache_l2`, `n_emb_api`)
— é o dado que dirá se a spec cumpriu o objetivo.

## Verificação

- Unit: miss no Redis + hit no Postgres re-hidrata Redis e não chama API (mockar as camadas);
  falha do Postgres degrada para API sem exceção; limpeza respeita `usado_em`.
- E2E: rodar o mesmo pilar 2× com `redis-cli FLUSHDB` entre as execuções → 2ª execução loga
  0 chamadas de API de embeddings (tudo L2).
- Produção: após 1 semana, `n_emb_api` por execução repetida ≈ 0.

## Riscos

- **Latência da L2**: 1 SELECT em lote por chamada de batch — desprezível vs chamadas de API que
  substitui. Não fazer SELECT por item.
- **Crescimento da tabela**: teto por linhas + TTL de uso; monitorar tamanho no dashboard Supabase.
- **Chave inclui modelo/dims**: troca de modelo de embedding invalida naturalmente (chaves novas);
  a limpeza recolhe as órfãs.
