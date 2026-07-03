# SPEC — Inlinks: corrigir qualidade de match e julgamento

**Status:** ✅ implementado
**Escopo:** backend + frontend (1 linha)
**Crédito:** não muda
**Depende de:** `SPEC_Inlinks_Remover_Aprendizado.md` + `SPEC_Inlinks_AntiAlucinacao_UI.md` aplicadas

---

## Contexto

Execução real de 13/05/2026 (`d7b50a52`) sobre o pilar "CNAE comércio varejista" (2387 palavras, 4 candidatas Agilize) resultou em apenas **1 inlink claramente bom** (score 0.86 — "escolher o CNAE certo" → `cnae-prestacao-de-servico`). Os outros 3 ficaram entre 0.44–0.56:

- "o código adequado" → `contratacao-pj` — âncora forçada, frase truncada.
- "Priorize a atividade de maior faturamento" → `contabilidade-online-MEI-ME` — tema desconectado.
- "comércio eletrônico" → `marketplace` — corretamente rejeitado pelo Revisor.

**Diagnóstico**: 5 causas-raiz combinadas (não é só modelo).

### Causas-raiz

1. **Bug crítico no `pilar_embedding`**: `workflow_inlinks.py:271-273` e `:357-360` definem o embedding do pilar como APENAS o primeiro chunk. Em um pilar de 2400 palavras (~4 chunks), descarta-se 75% do sinal semântico. Explica scores baixos sistematicamente entre artigos correlatos.
2. **Modelo errado nos pontos de decisão**: Reranker e Revisor ainda usam `gpt-4o-mini`. Esses agentes fazem julgamento contextual fino — `gpt-4o-mini` é inconsistente nessa tarefa.
3. **Reranker recebe sinal pobre**: passa apenas 2000 chars do pilar (= o início) e ignora `pilar_metadados.resumo`, `categoria`, `palavras_chave` produzidos pelo Enriquecedor. O `resumo` das candidatas é forçado a `""` em `match_rerank` (linha 428).
4. **Inseridor pode forçar links**: mesmo com regra "retorne `{}` se não cabe", gpt-4.1 tem viés de sempre encontrar algo.
5. **Revisor permissivo**: aprova links com âncora desconectada do tema do destino se a frase gramaticalmente fechar.

### Resultado esperado após esta SPEC

- Scores semânticos reais sobem em pilares longos (mean pooling).
- Reranker decide com gpt-4.1 + metadados estruturados simétricos.
- Inserções com âncora x destino fracos viram `sugestao_manual` em vez de `aplicado`.
- Revisor rejeita links com tema desconectado.
- Densidade alvo (4–5 inlinks por 1000 palavras) com qualidade preservada.

### Decisão sobre embeddings

**Mean pooling de todos os chunks do pilar** como abordagem primária:

- Chunks já existem em `conteudos_vetores` e são reusados via `html_hash` — zero chamada nova de API.
- Chunker (`app/core/chunker.py`) gera ~4 chunks de 800 tokens com overlap de 100 palavras: a redundância já cobre início/fim, mean pooling consolida o sinal central.
- Cosine é dimensão-preservante: `mean(emb_1...emb_n)` continua sendo um vetor de 1024 dims comparável.
- Prática NLP estabelecida para "document-level embedding" a partir de chunks.

Alternativa rejeitada: embedding focado em `titulo + resumo + palavras_chave`. Mais caro (1 chamada extra) e introduz dependência da qualidade do Enriquecedor (gpt-4o-mini), que é justamente um ponto fraco. Pode ser v2 se mean pooling não bastar.

Não há helper existente de mean pooling no projeto — será criado em `app/core/embeddings.py`.

---

## 1. Resumo

Sete entregas em 3 fases. Pode ser 1 PR com 3 commits separados (1 por fase) para facilitar review e bissecção.

| Fase | Mudança | Arquivos | Esforço |
|---|---|---|---|
| **1** | A — Mean pooling do `pilar_embedding` | `workflow_inlinks.py`, `embeddings.py` | 10 min |
| **1** | B — gpt-4.1 no Reranker e Revisor | `config.py`, `reranker.py`, `revisor.py` | 5 min |
| **1** | F — Threshold default `0.6` | `formulario-inlinks.tsx` | 1 min |
| **2** | C — Reranker recebe metadados estruturados | `reranker.py`, `workflow_inlinks.py` | 15 min |
| **2** | E — Endurecer prompt do Revisor | `revisor.py` | 10 min |
| **3** | D — Validação semântica pós-inserção (cosine âncora x titulo_destino) | `inseridor.py` | 20 min |
| — | G — Verificar que Cleaner/Formatador permanecem em gpt-4o-mini (no-op) | — | 0 min |

Total: ~60 min de implementação.

---

## 2. Fase 1 — Fundamentos

### Entrega A — Mean pooling do `pilar_embedding`

#### `backend/app/core/embeddings.py` (novo helper)

Adicionar função utilitária após `gerar_embedding_single`:

```python
def media_embeddings(embeddings: list[list[float] | None]) -> list[float] | None:
    """Mean pooling de uma lista de embeddings. Ignora None.

    Retorna o vetor médio (mesma dimensionalidade dos inputs), ou None se
    nenhum embedding válido foi passado. Usado para gerar uma representação
    document-level a partir de chunks.
    """
    import numpy as np

    validos = [e for e in embeddings if e is not None]
    if not validos:
        return None
    arr = np.array(validos, dtype=float)
    media = arr.mean(axis=0)
    return media.tolist()
```

#### `backend/app/agents/workflow_inlinks.py` — `node_enriquecer`

Atualmente em `:226–390`, o pilar acumula apenas o primeiro chunk (linhas `:271-273` e `:357-360`). Refatorar para:

1. Acumular **todos** os embeddings dos chunks do pilar em uma lista local.
2. Após o loop sobre `todas_urls`, computar `pilar_embedding = media_embeddings(pilar_chunk_embeddings)`.

Inicializar no topo do `async with async_session_factory()`:
```python
pilar_chunk_embeddings: list[list[float]] = []
```

Trocar as duas seções:

```python
# ANTES (existing rows, ~linhas 270-274):
if item["is_pilar"]:
    if pilar_embedding is None:
        pilar_embedding = row_emb
        pilar_metadados = meta_dict

# DEPOIS:
if item["is_pilar"]:
    pilar_chunk_embeddings.append(row_emb)
    if not pilar_metadados:
        pilar_metadados = meta_dict
```

```python
# ANTES (cold, ~linhas 357-360):
if item["is_pilar"]:
    if pilar_embedding is None:
        pilar_embedding = emb
        pilar_metadados = meta_dict

# DEPOIS:
if item["is_pilar"]:
    pilar_chunk_embeddings.append(emb)
    if not pilar_metadados:
        pilar_metadados = meta_dict
```

Após o loop (substitui as linhas 366-367):
```python
from app.core.embeddings import media_embeddings
pilar_embedding = media_embeddings(pilar_chunk_embeddings)
```

Logar quantos chunks foram consolidados:
```python
logger.info(
    "enriquecer: pilar_embedding=%s (%d chunks consolidados via mean pooling)",
    "OK" if pilar_embedding else "NONE",
    len(pilar_chunk_embeddings),
)
```

### Entrega B — gpt-4.1 no Reranker e Revisor

#### `backend/app/config.py`

Adicionar (após `inseridor_llm_model`):

```python
reranker_llm_model: str = "gpt-4.1"
revisor_llm_model: str = "gpt-4.1"
```

#### `backend/app/agents/inlinks/reranker.py`

Modificar `_RerankerAgent` para sobrescrever modelo, seguindo o padrão do Inseridor:

```python
class _RerankerAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        super().__init__(usuario_id)
        from app.config import settings
        if settings.llm_provider == "openai" and settings.reranker_llm_model:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=settings.reranker_llm_model,
                temperature=settings.llm_temperature,
                api_key=settings.openai_api_key,
            )

    async def _invoke_llm(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.content
```

#### `backend/app/agents/inlinks/revisor.py`

Mesmo padrão para `_RevisorAgent`:

```python
class _RevisorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        super().__init__(usuario_id)
        from app.config import settings
        if settings.llm_provider == "openai" and settings.revisor_llm_model:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=settings.revisor_llm_model,
                temperature=settings.llm_temperature,
                api_key=settings.openai_api_key,
            )

    async def _invoke_llm(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.content
```

### Entrega F — Threshold default `0.6`

#### `frontend/src/components/ferramentas/formulario-inlinks.tsx`

Localizar `useState(0.5)` (threshold) e trocar para `useState(0.6)`. Atualizar label de dica abaixo do slider se mencionar valor explícito.

---

## 3. Fase 2 — Refinamento de sinal e julgamento

### Entrega C — Reranker recebe metadados estruturados

#### `backend/app/agents/workflow_inlinks.py` — `node_match_rerank`

1. Preservar `categoria`, `palavras_chave`, `resumo` de cada candidata ao montar `best_by_url[url]`. Hoje em `:424-430` o dict só tem `url`, `url_canonica`, `titulo`, `resumo:""` (vazio fixo) e `score_semantico`. Trocar para:

```python
best_by_url[url] = {
    "url": url,
    "url_canonica": c.get("url_canonica", url),
    "titulo": c.get("titulo", ""),
    "resumo": c.get("resumo", ""),                # ← vinha do meta_dict, perdido
    "categoria": c.get("categoria", ""),
    "palavras_chave": c.get("palavras_chave", []),
    "score_semantico": cosine,
}
```

2. Em `:447-452`, passar `pilar_metadados` ao reranker:

```python
reranked = await rerank_candidatos(
    pilar_titulo=pilar_resultado.get("titulo", ""),
    pilar_resumo=pilar_resultado.get("conteudo_md", "")[:2000],
    pilar_metadados=estado.get("pilar_metadados", {}),
    candidatos=scored,
    usuario_id=estado["usuario_id"],
)
```

#### `backend/app/agents/inlinks/reranker.py`

Estender assinatura e prompt para usar metadados estruturados:

```python
async def rerank_candidatos(
    pilar_titulo: str,
    pilar_resumo: str,
    pilar_metadados: dict,
    candidatos: list[dict],
    usuario_id: str,
) -> list[dict]:
    ...
```

No prompt, substituir o bloco "TEMA DO PILAR" por bloco estruturado e simétrico ao das candidatas:

```
TEMA DO PILAR:
- Título: {pilar_titulo}
- Categoria: {pilar_metadados.get("categoria", "")}
- Palavras-chave: {", ".join(pilar_metadados.get("palavras_chave", []))}
- Resumo: {pilar_metadados.get("resumo", "")[:500]}

CANDIDATAS (cada uma é uma URL que pode receber link a partir do pilar):
1. URL: {c['url']}
   Título: {c['titulo']}
   Categoria: {c.get('categoria', '')}
   Palavras-chave: {", ".join(c.get('palavras_chave', []))}
   Resumo: {c.get('resumo', '')[:300]}
   Score semântico: {c['score_semantico']:.3f}
...
```

Isso elimina a assimetria atual (pilar = texto bruto; candidatas = título + resumo vazio).

### Entrega E — Endurecer prompt do Revisor

#### `backend/app/agents/inlinks/revisor.py`

Atualizar `prompt` em `revisar_inlinks`:

1. Em "REGRAS DE REJEIÇÃO — rejeite SOMENTE se:", adicionar item:
   - **A âncora não tem relação clara de tema com a página de destino** (ex.: âncora sobre "preço de produto" linkando para página sobre "como abrir empresa").

2. Adicionar few-shot ao final do prompt (antes do JSON de resposta):

```
EXEMPLO de rejeição correta:
- Âncora: "o código adequado" → Destino: "Contratação PJ: guia completo"
  Status: rejeitado_revisor
  Motivo: A âncora fala de código CNAE; o destino fala de contratação PJ. Temas tangenciais, não há ligação direta para o leitor.

EXEMPLO de aprovação correta:
- Âncora: "escolher o CNAE certo" → Destino: "CNAE prestação de serviço: escolha o ideal"
  Status: aplicado
  Motivo: ""
```

3. Manter as 4 regras de "NÃO rejeite por" intactas — elas seguem válidas.

---

## 4. Fase 3 — Defesa em profundidade

### Entrega D — Validação semântica pós-inserção (Inseridor)

#### `backend/app/agents/inlinks/inseridor.py`

Após `_propor_insercao_para_candidato` retornar uma proposta válida e antes de adicioná-la a `todas_insercoes`, calcular cosine entre:

- embedding do `trecho_original + " " + paragrafo_local[:200]` (contexto curto)
- embedding do `candidato.titulo + " " + candidato.resumo[:300]`

Se cosine < `_MIN_INSERCAO_SEMANTICA = 0.50`, marcar `status = "sugestao_manual"` com motivo `"Baixa relação semântica entre âncora e destino."`. Não é um descarte total — vira sugestão para o usuário avaliar manualmente.

Implementação (após `_TOP_N_PARAGRAFOS`):

```python
_MIN_INSERCAO_SEMANTICA = 0.50

async def _validar_relevancia_semantica(
    proposta: dict,
    paragrafos: list[str],
    candidato: dict,
    usuario_id: str,
) -> bool:
    idx = proposta["paragrafo_idx"]
    trecho = proposta.get("trecho_original", "")
    paragrafo = paragrafos[idx] if 0 <= idx < len(paragrafos) else ""
    contexto = f"{trecho} {paragrafo[:200]}"
    destino = f"{candidato.get('titulo', '')} {candidato.get('resumo', '')[:300]}"

    embs = await gerar_embeddings_batch([contexto, destino], usuario_id)
    if not embs or embs[0] is None or embs[1] is None:
        return True  # falha-aberta: na dúvida, permite

    from numpy import dot
    from numpy.linalg import norm
    cosine = float(dot(embs[0], embs[1]) / (norm(embs[0]) * norm(embs[1]) + 1e-8))
    return cosine >= _MIN_INSERCAO_SEMANTICA
```

Aplicar no loop de `inserir_inlinks`:

```python
for c in candidatos_top:
    contexto_paragrafos = await _selecionar_paragrafos_relevantes(...)
    if not contexto_paragrafos:
        continue
    proposta = await _propor_insercao_para_candidato(c, contexto_paragrafos, usuario_id)
    if not proposta:
        continue

    if not await _validar_relevancia_semantica(proposta, paragrafos, c, usuario_id):
        proposta["forcar_sugestao_manual"] = True
        proposta["motivo_sugestao"] = "Baixa relação semântica entre âncora e destino."

    todas_insercoes.append(proposta)
```

E em `_aplicar_insercoes`, logo após validar `p_idx >= 0`:

```python
if ins.get("forcar_sugestao_manual"):
    sugestoes.append({**ins, "motivo_sugestao": ins.get("motivo_sugestao", "Baixa relevância semântica.")})
    continue
```

### Entrega G — Cleaner e Formatador permanecem em gpt-4o-mini

Verificação apenas: `Cleaner` e `Formatador` herdam de `BaseAgent` sem override, então usam `settings.llm_model` global (= `gpt-4o-mini` no `.env`). Já é o desejado para tarefas mecânicas. **Sem mudança de código.**

---

## 5. Verificação ponta a ponta

### 5.1 Restart

```bash
pkill -f "uvicorn app.main"; pkill -f "arq app.worker"
cd backend && nohup python3 -u -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
cd backend && nohup python3 -u -m arq app.worker.WorkerSettings > /tmp/worker.log 2>&1 &
sleep 3
curl -sf -o /dev/null -w "Backend: %{http_code}\n" http://localhost:8000/health
```

### 5.2 Frontend

```bash
cd frontend && npm run build && cp -r out/* ../backend/static/
```

### 5.3 Execução real e checks

Rodar mesma execução E2E que produziu `d7b50a52` (CNAE comércio varejista + 4 candidatas Agilize). Comparar antes/depois:

- **Scores semânticos**: devem subir notavelmente. Antes (chunk único): 0.48–0.82. Depois (mean pooling): esperar 0.55–0.85.
- **Reranker**: prompt deve estar usando metadados estruturados — confirmar no log via `grep "Categoria:" /tmp/worker.log`.
- **Decisões do Reranker**: candidatos com tema realmente desconectado (ex.: marketplace para CNAE varejo) devem ter `score_contexto` < 0.4 (vs. 0.55 hoje).
- **Revisor**: pelo menos uma das âncoras forçadas anteriores ("o código adequado" → contratação PJ) deve cair em `rejeitado_revisor` com motivo temático.
- **Inseridor + validação D**: links com `score_total` ≥ threshold mas trecho desconectado do destino caem para `sugestao_manual` em vez de aplicados.
- **Threshold UI**: formulário inicia em `0.6`.

### 5.4 Sanidade de imports

```bash
grep -rn "media_embeddings\|reranker_llm_model\|revisor_llm_model" backend/app | head -10
```

Deve mostrar as ocorrências esperadas e nenhum erro de import (lint/runtime).

### 5.5 Custo

4 chamadas a gpt-4.1 por execução de 4 URLs (Reranker + Revisor + Inseridor × 1–4). Custo estimado: ~$0.06–0.10 por execução. Aceitável dado o crédito interno (15 base + N urls).

---

## 6. Fora de escopo

- Substituir Revisor por validação determinística (regex + cosine). Avaliar em v3 se Revisor continuar inconsistente.
- Embedding focado em metadados (titulo + resumo + palavras_chave) como representação do pilar. Mean pooling cobre por enquanto.
- Tunar pesos `0.5 / 0.5` do `score_total` no Reranker. Manter atual.
- Telemetria de CTR via UTM.

---

## 7. Riscos

- **Mean pooling dilui pilar com seções tangenciais**: se um pilar tem 1 chunk focado e 3 chunks divagando, a média pode ficar ruim. Mitigação: monitorar; se sintoma reaparecer, ir para embedding focado em metadados (v2).
- **gpt-4.1 mais lento que gpt-4o-mini**: cada execução pode ganhar +5–10s. Aceitável dado custo já é de 60s.
- **Validação D pode rejeitar bons links** se Enriquecedor produziu resumo ruim. Mitigação: threshold conservador (0.50), e o resultado é `sugestao_manual` (não descarte) — usuário ainda vê.
- **Mudança nos prompts do Revisor pode quebrar parsing**: o few-shot está em PT-BR e parseamos JSON pelo `_parse_revisao` que extrai `{...}` por delimitadores. Robusto.

---

## 8. Arquivos críticos

### Backend — alterados (em ordem de fase)

**Fase 1:**
- `backend/app/core/embeddings.py` — adicionar `media_embeddings()`.
- `backend/app/agents/workflow_inlinks.py` — `node_enriquecer` acumula chunks e faz mean pooling do pilar.
- `backend/app/config.py` — adicionar `reranker_llm_model` e `revisor_llm_model`.
- `backend/app/agents/inlinks/reranker.py` — `_RerankerAgent.__init__` com override de modelo.
- `backend/app/agents/inlinks/revisor.py` — `_RevisorAgent.__init__` com override de modelo.

**Fase 2:**
- `backend/app/agents/workflow_inlinks.py` — `node_match_rerank` preserva `resumo`, `categoria`, `palavras_chave` nas candidatas e passa `pilar_metadados` ao reranker.
- `backend/app/agents/inlinks/reranker.py` — assinatura `rerank_candidatos(..., pilar_metadados)` e prompt estruturado simétrico.
- `backend/app/agents/inlinks/revisor.py` — prompt com regra de rejeição temática + few-shot.

**Fase 3:**
- `backend/app/agents/inlinks/inseridor.py` — `_validar_relevancia_semantica` + integração no loop + `forcar_sugestao_manual` em `_aplicar_insercoes`.

### Frontend — alterado
- `frontend/src/components/ferramentas/formulario-inlinks.tsx` — default threshold `0.6` (era `0.5`).
