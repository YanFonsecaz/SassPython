# SPEC — Inlinks: UX para 0 aplicados + Enriquecedor mais agressivo + tolerância semântica anti-alucinação

**Status:** pendente
**Escopo:** backend (`workflow_inlinks.py`, `enriquecedor_metadados.py`, `inseridor.py`)
**Crédito:** não muda
**Depende de:** `SPEC_Inlinks_Sinonimos_via_Palavras_Chave.md` aplicada

---

## Contexto

Teste E2E #5 (`851195b1`, 13/05/2026) com pilar genérico "o que montar para ganhar dinheiro" + 4 candidatas específicas (Agilize) resultou em **0 aplicados / 1 sugestao_manual / 3 recusas LLM**.

Diagnóstico:

1. **Enriquecedor (gpt-4o-mini)** extraiu `palavras_chave` da loja-virtual como `["loja virtual", "e-commerce", "CNPJ", "documentos", "custos"]` — **sem "dropshipping"** (que está no conteúdo do destino).
2. **Inseridor** propôs corretamente trecho "revenda sem estoque" com `palavra_chave_destino="dropshipping"`.
3. **Validação anti-alucinação** rejeitou porque "dropshipping" não aparece em `titulo+resumo+palavras_chave` do destino. Validação **literalmente correta**, mas perde o link.

Cenário estrutural: pilar genérico × candidatos específicos = nenhum match léxico. Os 3 caminhos resolvem em frentes diferentes:

- **Caminho 1 (UX)** — quando 0 aplicados, comunicar claramente que pilar pode estar genérico demais.
- **Caminho 2 (Enriquecedor)** — prompt mais agressivo para extrair sinônimos do nicho (incluindo termos técnicos do conteúdo do destino).
- **Caminho 3 (tolerância semântica)** — quando check léxico falha, fallback via cosine `kw_raw` vs `titulo+resumo`. Captura "dropshipping" ≡ "loja virtual" via embedding mesmo sem match literal.

---

## 1. Resumo

Três entregas. ~30 min. Pode ser 1 PR com 3 commits separados.

| # | Entrega | Arquivo | Esforço |
|---|---|---|---|
| **1** | UX: mensagem específica quando `n_aplicados == 0` e `n_validas > 0` | `workflow_inlinks.py` | 5 min |
| **2** | Enriquecedor: prompt mais agressivo + few-shot de nicho | `enriquecedor_metadados.py` | 10 min |
| **3** | Tolerância semântica no anti-alucinação (cosine fallback) | `inseridor.py` | 15 min |

---

## 2. Entrega 1 — UX para 0 aplicados

### `backend/app/agents/workflow_inlinks.py:_finalizar_sucesso_inlinks`

Já existe a branch `n_aplicados == 0` (cobra só URLs, sem base). Falta popular `erro_msg` com mensagem clara para a UI:

```python
n_aplicados = resultado_json.get("n_aplicadas", 0)
if n_aplicados == 0:
    custo = max(0, custo - ferramenta_service.CUSTO_BASE_INLINKS)
    execucao.erro_msg = (
        "Nenhum link orgânico cabe neste pilar — os destinos avaliados não "
        "compartilham termos específicos com o texto. Reveja as sugestões "
        "manuais ou reescreva o pilar para citar nichos com mais detalhes."
    )
    logger.info(
        "execucao_id=%s inlinks: 0 aplicados de %d validas, cobrando so URLs (custo=%d, sem base)",
        execucao_id, n_processadas, custo,
    )
```

**Verificar** que o frontend (`ferramentas-inlinks` ou `execucao-detalhe-conteudo`) já exibe `erro_msg`. Se sim, nenhuma mudança de UI. Caso contrário, adicionar um banner amarelo (não vermelho — execução foi sucesso parcial, não falha).

---

## 3. Entrega 2 — Enriquecedor mais agressivo

### `backend/app/agents/inlinks/enriquecedor_metadados.py`

Atualizar `_build_prompt` (função existente) para forçar extração de termos específicos do nicho, incluindo sinônimos técnicos:

```python
def _build_prompt(markdown: str, titulo: str) -> str:
    truncated = markdown[:8000]
    return f"""Você é um analista de conteúdo SEO. Recebe título e markdown de uma
página e produz metadados estruturados.

REGRAS:
- tipo: um de [blog, produto, categoria, landing, tutorial].
- intencao: um de [informacional, comercial, transacional, navegacional].
- categoria: tema principal em 1-3 palavras (ex.: "Programação iniciante").
- palavras_chave: 7-15 termos centrais do texto. INCLUA OBRIGATORIAMENTE:
  * Substantivos do título (ex.: "loja virtual", "imobiliária", "restaurante").
  * Sinônimos técnicos e regionalismos mencionados no corpo (ex.: para "loja
    virtual" inclua "e-commerce", "dropshipping", "marketplace" SE aparecerem).
  * Termos do nicho que distinguem este artigo de artigos genéricos (ex.: para
    "abrir restaurante" inclua "alimentação", "cozinha", "delivery").
  * NÃO inclua palavras genéricas como "empresa", "negócio", "abrir", "como"
    — essas não diferenciam o conteúdo.
- entidades: nomes próprios, ferramentas, tecnologias, frameworks
  mencionados (até 10).
- resumo: 2-3 frases sobre o que a página oferece ao leitor, citando o nicho
  específico (não apenas "guia sobre empresa").

EXEMPLO de palavras_chave bem extraídas:

Título: "Como abrir uma loja virtual: guia completo"
Markdown menciona: "dropshipping", "marketplaces", "shopify", "CNPJ", "frete"

palavras_chave: ["loja virtual", "e-commerce", "dropshipping", "marketplace",
                  "shopify", "CNPJ", "frete", "vendas online"]

Note: "empresa", "negócio", "abrir" foram EXCLUÍDOS por serem genéricos.
"shopify" foi INCLUÍDO porque é termo técnico mencionado.

Saída APENAS em JSON:
{{
  "tipo": "blog",
  "categoria": "...",
  "intencao": "informacional",
  "palavras_chave": ["..."],
  "entidades": ["..."],
  "resumo": "..."
}}

Título: {titulo}

Markdown:
<<<
{truncated}
>>>"""
```

### Backfill (opcional)

Vetores antigos (pré-SPEC) continuam com palavras_chave ruins. Decisão de produto:
- Manter como está: novos vetores cold path populam corretamente, vetores antigos mantém comportamento velho até `html_hash` mudar.
- Re-extrair: SQL `UPDATE conteudos_vetores SET ativo=false WHERE criado_em < '2026-05-13'` força regeneração na próxima execução. Custo: re-extrair embeddings.

**Não obrigatório nesta SPEC.** Decisão do usuário.

---

## 4. Entrega 3 — Tolerância semântica no anti-alucinação

### Problema

Atualmente em `_validar_palavra_chave_destino`:

```python
if not _contem_termo(destino_texto, kw_raw):
    return f"Termo '{kw_raw}' não aparece em título/resumo do destino (alucinação do LLM)."
```

Esse check é **léxicamente cego** a sinônimos conceituais. "dropshipping" não aparece literal em "Como abrir uma loja virtual: guia completo e prático" + resumo curto, mesmo sendo conceitualmente sinônimo. Validação rejeita por "alucinação", mas o LLM acertou.

### Solução

Quando o check léxico falhar, tentar fallback semântico: cosine entre `kw_raw` e `titulo + resumo`. Threshold conservador (0.55) para evitar aceitar termos genuinamente alucinados.

### `backend/app/agents/inlinks/inseridor.py`

Adicionar constante:

```python
_MIN_SEMANTIC_FALLBACK = 0.55
```

Refatorar `_validar_palavra_chave_destino` para ser async (precisa fazer chamada de embedding) e receber `usuario_id`:

```python
async def _validar_palavra_chave_destino(
    parsed: dict,
    candidato: dict,
    paragrafo_completo: str,
    usuario_id: str,
) -> str | None:
    kw_raw = (parsed.get("palavra_chave_destino") or "").strip()
    if not kw_raw or len(kw_raw) < 2:
        return "Inseridor não nomeou termo específico do destino."

    kw_norm = _normalize_token(kw_raw)
    if kw_norm in _STOPWORDS_GENERICAS:
        return f"Termo '{kw_raw}' é muito genérico para servir de âncora específica."

    titulo = candidato.get("titulo", "") or ""
    resumo = candidato.get("resumo", "") or ""
    palavras_chave = candidato.get("palavras_chave") or []
    palavras_chave_str = " ".join(palavras_chave) if isinstance(palavras_chave, list) else str(palavras_chave)
    destino_texto = f"{titulo} {resumo} {palavras_chave_str}"

    if not _contem_termo(destino_texto, kw_raw):
        # Fallback semântico: cosine entre kw_raw e título+resumo.
        # Pega sinônimo conceitual ("dropshipping" ≡ "loja virtual") via embedding.
        destino_curto = f"{titulo} {resumo[:300]}"
        embs = await gerar_embeddings_batch([kw_raw, destino_curto], usuario_id)
        if embs and embs[0] is not None and embs[1] is not None:
            cos = cosine_seguro(embs[0], embs[1])
            if cos >= _MIN_SEMANTIC_FALLBACK:
                logger.info(
                    "Inseridor: kw '%s' não-literal mas semanticamente próxima (cos=%.3f) ao destino — aceito",
                    kw_raw, cos,
                )
            else:
                return f"Termo '{kw_raw}' não aparece em destino e cosine baixo (cos={cos:.2f}) — provável alucinação."
        else:
            return f"Termo '{kw_raw}' não aparece em título/resumo do destino (alucinação do LLM)."

    termos_validos = _termos_validos_destino(candidato, kw_raw)
    if not termos_validos:
        return f"Nenhum termo específico do destino disponível para validação (kw='{kw_raw}')."

    anchor = parsed.get("anchor_text") or ""
    trecho = parsed.get("trecho_original") or ""
    ancora_texto = f"{anchor} {trecho} {paragrafo_completo}"

    for termo in termos_validos:
        if _contem_termo(ancora_texto, termo):
            return None

    termos_str = ", ".join(f"'{t}'" for t in termos_validos[:5])
    return (
        f"Âncora não menciona nenhum termo específico do destino. "
        f"Esperado um de: {termos_str}."
    )
```

### Atualizar chamador em `_propor_insercao_para_candidato`

Mudar para `await`:

```python
motivo_kw = await _validar_palavra_chave_destino(
    parsed, candidato, paragrafo_completo, usuario_id
)
```

### Custo

Por candidato que falha o check léxico:
- 2 embeddings adicionais (kw_raw + destino_curto)
- Texto curto, alta cache hit rate em re-execuções
- Estimativa: +0.5s no Inseridor em casos de fallback (a maioria não precisa)

Sem custo extra quando o check léxico passa direto (caso comum em vetores novos com Enriquecedor melhorado da Entrega 2).

---

## 5. Verificação ponta a ponta

### 5.1 Sanidade

```bash
grep -n "Nenhum link orgânico\|7-15 termos\|_MIN_SEMANTIC_FALLBACK\|cosine_seguro" backend/app | head -10
```

### 5.2 Restart

```bash
pkill -f "arq app.worker"
cd backend && nohup python3 -u -m arq app.worker.WorkerSettings > /tmp/worker.log 2>&1 &
sleep 3
```

### 5.3 Forçar re-extração das candidatas para testar Enriquecedor novo

```sql
UPDATE conteudos_vetores SET ativo=false
WHERE usuario_id='b9afa7ad-12c7-40b8-a4a7-3d0bcd4f1f31'
  AND url_canonica LIKE '%loja-virtual%';
```

(Repetir para imobiliária/restaurante/agência se quiser testar todos. Próxima execução fará cold path.)

### 5.4 Re-rodar E2E com mesmo pilar

Cenários esperados:

| Candidata | Antes (#5) | Depois | Por quê |
|---|---|---|---|
| loja-virtual | sugestao_manual (alucinação) | **aplicado** | Enriquecedor agora extrai "dropshipping" em palavras_chave (Entrega 2). Mesmo se não extrair, fallback cosine ≥ 0.55 aceita (Entrega 3). |
| imobiliária | recusado | **continua recusado** | Pilar não menciona "imóveis", "corretagem", etc — nem por sinônimo |
| restaurante | recusado | possivelmente aplicado | Se Enriquecedor extrair "cozinha"/"alimentação" e pilar mencionar — caso a caso |
| agência-viagens | recusado | possivelmente aplicado | Idem |

### 5.5 Validar mensagem UX

Se ainda houver execução com 0 aplicados, conferir no banco:

```sql
SELECT erro_msg FROM execucoes_ferramentas WHERE id='<eid>' AND status='concluida';
```

Deve retornar a mensagem da Entrega 1.

### 5.6 SQL de auditoria do Enriquecedor

```sql
SELECT url_canonica, palavras_chave
FROM conteudos_vetores
WHERE criado_em > now() - interval '5 minutes'
  AND tipo_recurso='candidata'
  AND chunk_index=0
ORDER BY criado_em DESC LIMIT 5;
```

Esperado: palavras_chave com 7-15 itens, incluindo termos técnicos como "dropshipping", "shopify", etc para destinos específicos.

---

## 6. Fora de escopo

- **Backfill automático de vetores antigos** — decisão do usuário (delete manual).
- **Validar Enriquecedor com mais nichos** (advocacia, saúde, beleza) — adiar até dados reais aparecerem.
- **Cross-encoder real (Voyage/Cohere)** — adiar. Entregas 2 + 3 podem ser suficientes.
- **LLM judge na validação** — adiar.

---

## 7. Riscos

- **Entrega 1 — Mensagem alarmante**: o texto sugere "reescreva o pilar". Pode confundir usuário que esperava magia. Mitigação: tom de aviso (não de erro); mostra como banner amarelo no front.
- **Entrega 2 — Enriquecedor mais longo = LLM mais lento e caro**: gpt-4o-mini ainda dá conta; aumento marginal de tokens. Pode-se medir e ajustar.
- **Entrega 3 — Fallback cosine 0.55 pode ser frouxo demais**: se cosine "dropshipping" vs "Como abrir uma loja virtual" for 0.40, ainda rejeita. Mitigação: ajustar threshold após medir.
- **Embeddings batch extra adiciona ~0.5s/candidato em fallback**: aceitar. Em produção, cache reduz para 1ª execução.

---

## 8. Arquivos críticos

### Backend — alterados
- `backend/app/agents/workflow_inlinks.py` — `_finalizar_sucesso_inlinks` ganha `erro_msg` específico quando `n_aplicados == 0`.
- `backend/app/agents/inlinks/enriquecedor_metadados.py` — `_build_prompt` reescrito com regras + few-shot.
- `backend/app/agents/inlinks/inseridor.py`:
  - `_MIN_SEMANTIC_FALLBACK = 0.55` (constante nova).
  - `_validar_palavra_chave_destino` vira `async` com `usuario_id` e fallback cosine.
  - `_propor_insercao_para_candidato` usa `await`.

### Frontend
- Nenhuma alteração obrigatória — `erro_msg` já é exibido na UI da execução. Conferir e estilizar banner amarelo se necessário.

---

## 9. Verificação (sumário)

1. Grep confirma mudanças nos 3 arquivos.
2. Restart sem erro.
3. Re-extração das candidatas (UPDATE ativo=false) → próxima execução popula palavras_chave com Enriquecedor melhorado.
4. E2E real: **loja-virtual deve voltar a aplicado**; outros candidatos genuinamente desconectados continuam recusados.
5. Se 0 aplicados, mensagem em `erro_msg` clara para o usuário.
6. Log de Inseridor mostra cosine fallback quando ativado.
