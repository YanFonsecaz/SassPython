# SPEC — Inlinks: ancorar `palavra_chave_destino` nas palavras_chave/título do destino

**Status:** a aplicar · **Escopo:** `inseridor.py` (prompt + helper) · **Crédito:** não muda
**Contexto:** E2E #7 e #8 mostraram que o Inseridor (gpt-4.1) escolhe `palavra_chave_destino` baseado em conceitos do PILAR ("dropshipping"), mesmo quando esses termos não existem no DESTINO (`como-abrir-uma-loja-virtual`). Resultado: validação falha → `sugestao_manual`. Upgrade do Enriquecedor (gpt-4o-mini → gpt-4.1) não resolveu — "dropshipping" não aparece no corpo do artigo de destino, então nenhum enriquecedor honesto vai incluí-lo.

## 1. Causa raiz

O prompt do Inseridor (`_build_prompt_focado`):

- Mostra apenas `título + resumo[:200]` do destino, **não as `palavras_chave`**.
- Tem regra 7 dizendo que o termo pode ser "sinônimo direto, como dropshipping para loja virtual". Isso encoraja o gpt-4.1 a chutar sinônimos do pilar, sem garantia de que esse sinônimo está no destino.
- Tem `EXEMPLO de sinônimo válido` reforçando o uso de "dropshipping" — anti-padrão se o destino não tem dropshipping nas palavras_chave.

## 2. Mudanças

### 2.1 `_build_prompt_focado` — expor palavras_chave do destino

Adicionar bloco no prompt:

```text
URL DESTINO:
- URL: {candidato['url']}
- Título: {candidato.get('titulo', '')}
- Palavras-chave do destino: {", ".join(palavras_chave_destino)}
- Resumo: {candidato.get('resumo', '')[:200]}
```

Onde `palavras_chave_destino = candidato.get("palavras_chave") or []`.

### 2.2 Regra 7 — ancorar no destino

Reescrever:

> 7. **`palavra_chave_destino`**: ESCOLHA OBRIGATORIAMENTE uma das **palavras-chave do destino** listadas acima (ou um substantivo presente no título do destino). NÃO invente sinônimos do pilar — se o conceito do parágrafo não está na lista de palavras-chave do destino, retorne `{}`. Exemplos:
>   - Destino com palavras-chave `["loja virtual", "e-commerce", "Shopify"]` + parágrafo sobre "revenda sem estoque" → escolha `palavra_chave_destino="e-commerce"` (presente na lista) OU retorne `{}` se "e-commerce" não cabe na âncora. NÃO use "dropshipping" se não estiver na lista.

### 2.3 Substituir `EXEMPLO de sinônimo válido`

Trocar pelo seguinte (ancorado, não permissivo):

```text
EXEMPLO de palavra_chave_destino válida (presente nas palavras-chave):

Parágrafo: "Revenda sem estoque é uma opção barata."
URL destino: como-abrir-uma-loja-virtual
Palavras-chave do destino: ["loja virtual", "e-commerce", "loja online", "Shopify"]

"dropshipping" NÃO está nas palavras-chave do destino — não use. Escolha um termo da lista que se aplique ao parágrafo, ou retorne {}. Resposta válida:
{"paragrafo_idx": 1, "trecho_original": "Revenda sem estoque", "anchor_text": "Revenda sem estoque", "palavra_chave_destino": "e-commerce", "justificativa": "Trecho descreve modelo de e-commerce, que é uma das palavras-chave do destino."}
```

### 2.4 `_validar_palavra_chave_destino` — endurecer

Quando `palavra_chave_destino` NÃO está em título nem em `palavras_chave` do destino:

- **Hoje**: cai em cosine fallback (`_MIN_SEMANTIC_FALLBACK=0.40`).
- **Novo**: rejeitar diretamente (sem cosine fallback) e retornar motivo "Termo X não está nas palavras-chave do destino — Inseridor deveria escolher um da lista."

Razão: agora o Inseridor recebe a lista no prompt. Se mesmo assim escolhe fora, é alucinação dele, não limitação do embedding bi-encoder. O cosine fallback foi adicionado antes para compensar a falta dessa lista no prompt; agora redundante.

Manter cosine fallback apenas como log de diagnóstico (não como aceitação).

## 3. Verificação

Rodar E2E #9 com mesmo pilar + 4 candidatas. Esperado:

- **loja-virtual**: `aplicado`. Inseridor escolhe `palavra_chave_destino` entre `["loja virtual", "e-commerce", "loja online", "Shopify", "Nuvemshop", ...]`. Anchor pode ser "revenda sem estoque" mas a kw_destino deve ser "e-commerce" ou "loja virtual" (ambas estão no destino).
- **restaurante**: ainda em `sugestao_manual` pela Entrega D (gating semântico, threshold 0.50) — fix diferente, fora desta SPEC.
- **imobiliária**: ainda incerto (Inseridor devolveu `{}` no E2E #8).
- **agência viagens**: 404 — não processa.

## 4. Riscos

- Inseridor pode ficar mais conservador e devolver `{}` em mais casos (não acha termo aplicável da lista). Aceitável: melhor recusar do que forçar.
- Se Enriquecedor falhar em listar palavras_chave (lista vazia), o Inseridor não tem âncora possível. Mitigação: cai em `{}`, vira "sem sugestão" — não vira link ruim.

## 5. Fora de escopo

- Fix da imobiliária (Inseridor devolveu `{}` — diagnosticar separado).
- Ajuste do threshold da Entrega D (validação semântica) para restaurante.
- Cross-encoder (Cenário C) — reservado se este fix não bastar.
