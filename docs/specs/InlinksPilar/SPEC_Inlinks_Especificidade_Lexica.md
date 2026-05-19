# SPEC — Inlinks: filtro de especificidade léxica via palavra-chave do destino

**Status:** pendente
**Escopo:** backend (`inseridor.py` apenas)
**Crédito:** não muda (mesma chamada LLM)
**Depende de:** `SPEC_Inlinks_Qualidade_Ancora_e_Densidade.md` aplicada (parte da Entrega 2 revertida)

---

## Contexto

Teste E2E #3 (`a239c6dc`, 13/05/2026) mostrou que a Validação D por cosine (`_MIN_ANCORA_TITULO = 0.35`) **não distingue âncora genérica de específica quando o domínio é compartilhado**:

| Âncora | Título destino | Cosine medido | Resultado |
|---|---|---|---|
| "que tipo de negócio devo abrir" | "Como abrir uma imobiliária..." | **0.49** | passou (forçado) ❌ |
| "revenda sem estoque (como dropshipping)" | "Como abrir uma loja virtual..." | 0.44 | passou ✓ |
| "o investimento cresce" | "Como abrir um restaurante..." | 0.23 | caiu ✓ |
| "formalize seu empreendimento" | "Como abrir uma agência..." | 0.39 | caiu ✓ (por cosine_contexto) |

Janela entre 0.44 e 0.49 é apertada demais — qualquer threshold derruba também o caso bom (loja-virtual) ou deixa passar o forçado (imobiliária).

Pesquisa em LangChain docs + web confirma: **embeddings bi-encoder genéricos não conseguem fazer essa distinção**. Padrão recomendado pela indústria SEO 2026 é **entity-level matching** — exigir que a âncora mencione o termo central do destino.

### Resultado esperado

Forçar o LLM Inseridor a **nomear** a palavra-chave específica do destino que a âncora menciona (ou alude). Pós-processamento valida lexicalmente que essa palavra existe tanto no destino quanto na âncora. Caso contrário, vira `sugestao_manual`.

**Por que isso resolve o caso problemático:**
- LLM tenta `palavra_chave_destino="imobiliária"` → não está em "que tipo de negócio devo abrir" → falha → `sugestao_manual` ✓
- LLM tenta `palavra_chave_destino="negócio"` → está em ambos, mas "negócio" está na blacklist de termos genéricos → falha → `sugestao_manual` ✓
- LLM tenta `palavra_chave_destino="dropshipping"` → está em resumo do destino + na âncora ("revenda sem estoque (como dropshipping)") → passa ✓

---

## 1. Resumo

Uma única entrega. Esforço ~20 min. Tudo isolado em `backend/app/agents/inlinks/inseridor.py`.

| # | Mudança | Esforço |
|---|---|---|
| 1 | Stopwords genéricas + helper de normalização | 3 min |
| 2 | Prompt do Inseridor exige campo `palavra_chave_destino` (com regra e exemplo) | 5 min |
| 3 | `_parse_proposta_unica` extrai o campo novo | 2 min |
| 4 | `_propor_insercao_para_candidato` valida lexicalmente e marca `forcar_sugestao_manual` | 10 min |

---

## 2. Implementação

### 2.1 Stopwords + helper

No topo de `backend/app/agents/inlinks/inseridor.py`, após as constantes existentes:

```python
_STOPWORDS_GENERICAS = {
    # verbos comuns e auxiliares
    "abrir", "fazer", "criar", "montar", "começar", "iniciar", "ter", "ser", "estar",
    "ir", "vir", "saber", "conhecer", "ver",
    # substantivos demasiado abrangentes
    "negócio", "negocio", "empresa", "negócios", "negocios", "empresas",
    "investimento", "investimentos", "dinheiro", "lucro", "ganhar", "renda",
    "guia", "passos", "dicas", "tipo", "tipos", "opção", "opcao", "opções", "opcoes",
    # filler
    "como", "qual", "quais", "que", "tudo", "completo", "completa", "ideal", "melhor",
    "novo", "nova", "pratico", "prático",
}


def _normalize_token(s: str) -> str:
    """Lowercase + strip accents para comparação léxica robusta."""
    return _strip_accents(s.lower())


def _contem_termo(haystack: str, needle: str) -> bool:
    """Substring match insensitive a case e acentos."""
    if not haystack or not needle or len(needle.strip()) < 2:
        return False
    return _normalize_token(needle) in _normalize_token(haystack)
```

(`_strip_accents` já é importado de `injector.py:8`.)

### 2.2 Prompt do Inseridor

Em `_build_prompt_focado`, adicionar regra 7 e atualizar o JSON exemplo + instruções finais:

```python
return f"""Você é um especialista em SEO. Recebe 3 parágrafos candidatos e UMA URL de destino.
Sua tarefa: escolher UM parágrafo e UM trecho contínuo desse parágrafo para virar âncora do link.

URL DESTINO:
- URL: {candidato['url']}
- Título: {candidato.get('titulo', '')}
- Resumo: {candidato.get('resumo', '')[:200]}

PARÁGRAFOS DISPONÍVEIS:
{blocos}

REGRAS (em ordem de prioridade):
1. Escolha o parágrafo cujo TEMA bate com o destino, não pela palavra solta.
2. `trecho_original`: 2-5 palavras CONTÍNUAS, COPIADAS EXATAMENTE de um dos parágrafos acima. NÃO PARAFRASEIE.
3. `anchor_text`: por padrão igual ao trecho_original.
4. Conectores `conector_antes` / `conector_depois` (até 3 palavras cada). Use SOMENTE quando o trecho_original já estiver naturalmente conectado ao redor e faltarem palavras de transição. NÃO use para criar contexto que não existe no parágrafo. Se o tema do parágrafo não tem relação clara com o destino, prefira NÃO propor inserção. O conector NÃO deve repetir palavras que já existem imediatamente após o trecho_original.
5. PROIBIDO inserir em: cabeçalhos, listas, blocos de código (já filtramos, dupla checagem).
6. **NÃO force link onde não há conexão temática.** Se o tema do parágrafo é diferente do destino, retorne `{{}}`. É melhor ter menos links com qualidade do que links forçados.
7. **`palavra_chave_destino`**: substantivo ou nome próprio ESPECÍFICO do destino que aparece (ou é sinônimo direto de) algo na sua âncora. Exemplos válidos: "restaurante", "loja virtual", "imobiliária", "dropshipping", "MEI". NÃO use palavras genéricas como "negócio", "empresa", "abrir", "tipo", "investimento", "como". Se a âncora NÃO menciona nem alude a nenhum termo específico do destino, retorne `{{}}` — não force.

EXEMPLO de boa resposta:

Parágrafo L1: "Python é uma das linguagens mais populares para iniciantes. Sua sintaxe simples reduz a curva de aprendizado."
URL destino: melhor-linguagem-iniciantes / Título: "Melhor linguagem para iniciantes em programação"

Resposta:
{{"paragrafo_idx": 1, "trecho_original": "Python é uma das linguagens", "anchor_text": "Python é uma das linguagens", "conector_antes": "", "conector_depois": " para iniciantes que vale explorar", "palavra_chave_destino": "linguagem", "justificativa": "Trecho menciona 'linguagem'; destino aprofunda o tema 'linguagem para iniciantes'."}}

Note: trecho_original é cópia LITERAL do parágrafo L1. "linguagem" aparece tanto na âncora quanto no título do destino.

EXEMPLO de quando recusar:

Parágrafo: "Antes de empreender, faça um estudo de mercado completo."
URL destino: como-abrir-uma-imobiliaria

A única palavra forte do destino é "imobiliária" — que NÃO aparece no parágrafo nem em variações. Resposta: {{}}.

Agora responda APENAS com JSON, no mesmo formato, para o caso real. Use `paragrafo_idx` 0, 1, 2, 3 ou 4 referente a L0/L1/L2/L3/L4."""
```

### 2.3 Parser

`_parse_proposta_unica` continua aceitando JSON livre — a chave nova já vira atributo do dict automaticamente. Só ajustar a sanidade mínima para também aceitar `{}` retornado pelo LLM como recusa válida:

```python
def _parse_proposta_unica(response: str) -> dict | None:
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(response[start:end])
            # Recusa explícita do LLM: retorna {} sem campos
            if not data:
                return None
            if "trecho_original" in data and "paragrafo_idx" in data:
                return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None
```

(Comportamento atual já trata `{}` como recusa porque `"trecho_original" in {}` é `False`. Mas o comentário explicita o contrato.)

### 2.4 Validação léxica

Em `_propor_insercao_para_candidato`, após `parsed["url_destino"] = candidato["url"]`, validar a `palavra_chave_destino`:

```python
def _validar_palavra_chave_destino(parsed: dict, candidato: dict) -> str | None:
    """Retorna motivo de rejeição (string) ou None se passa.

    Critérios:
    1. palavra_chave_destino deve estar presente e não vazia.
    2. NÃO pode ser stopword genérica (após normalização).
    3. Deve aparecer no destino (título + resumo + palavras_chave) — anti-alucinação.
    4. Deve aparecer no anchor_text ou trecho_original — overlap léxico real.
    """
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
        return f"Termo '{kw_raw}' não aparece em título/resumo do destino (alucinação do LLM)."

    anchor = parsed.get("anchor_text") or ""
    trecho = parsed.get("trecho_original") or ""
    ancora_texto = f"{anchor} {trecho}"

    if not _contem_termo(ancora_texto, kw_raw):
        return f"Âncora não menciona termo específico '{kw_raw}' do destino."

    return None
```

E uso dentro de `_propor_insercao_para_candidato`:

```python
async def _propor_insercao_para_candidato(
    candidato: dict,
    contexto_paragrafos: list[tuple[int, str]],
    usuario_id: str,
) -> dict | None:
    agente = _InseridorAgent(usuario_id)
    prompt = _build_prompt_focado(candidato, contexto_paragrafos)
    try:
        resposta = await agente._invoke_llm(prompt)
        parsed = _parse_proposta_unica(resposta)
    except Exception as e:
        logger.warning("Inseridor LLM falhou para %s: %s", candidato.get("url"), e)
        return None

    if not parsed:
        logger.warning(
            "Inseridor: LLM não propôs inserção para %s. Resposta: %s",
            candidato.get("url"), (resposta or "")[:400],
        )
        return None

    idx_local = parsed.get("paragrafo_idx", -1)
    if not isinstance(idx_local, int) or not (0 <= idx_local < len(contexto_paragrafos)):
        logger.warning(
            "Inseridor: paragrafo_idx fora do contexto local (%s) para %s",
            idx_local, candidato.get("url"),
        )
        return None

    idx_global, _ = contexto_paragrafos[idx_local]
    parsed["paragrafo_idx"] = idx_global
    parsed["url_destino"] = candidato["url"]

    motivo_kw = _validar_palavra_chave_destino(parsed, candidato)
    if motivo_kw:
        logger.info(
            "Inseridor: palavra_chave_destino falhou para %s: %s",
            candidato.get("url"), motivo_kw,
        )
        parsed["forcar_sugestao_manual"] = True
        parsed["motivo_sugestao"] = motivo_kw

    return parsed
```

`forcar_sugestao_manual` já é tratado em `_aplicar_insercoes` (linha 343–345) — vira `sugestao_manual` com motivo específico na UI.

---

## 3. Validação ponta a ponta

### 3.1 Sanidade de import

```bash
grep -n "_STOPWORDS_GENERICAS\|_validar_palavra_chave_destino\|palavra_chave_destino" backend/app/agents/inlinks/inseridor.py | head -10
```

### 3.2 Restart

```bash
pkill -f "arq app.worker"
cd backend && nohup python3 -u -m arq app.worker.WorkerSettings > /tmp/worker.log 2>&1 &
sleep 3
```

### 3.3 Re-rodar mesmo E2E (pilar "o-que-montar-para-ganhar-dinheiro")

Esperado:

| Candidata | LLM provavelmente preenche kw | Validação | Resultado |
|---|---|---|---|
| loja-virtual | "loja virtual" ou "dropshipping" | ✓ aparece em anchor + destino | **aplicado** |
| imobiliária | "imobiliária" (não cabe em "que tipo de negócio devo abrir") OU "negócio" (stopword) | ✗ | **sugestao_manual** |
| restaurante | "restaurante" (se LLM achar parágrafo que cite) ou nada | depende do trecho | **aplicado** ou **sugestao_manual** |
| agência-viagens | "viagens" ou "agência" | ✗ se anchor for "formalize..." | **sugestao_manual** |

Densidade ideal: 2-3 aplicados (loja-virtual sempre, restaurante possível, imobiliária e agência viram sugestões).

### 3.4 SQL de auditoria

```sql
SELECT
  url_destino,
  status,
  anchor_text,
  motivo_rejeicao,
  ROUND(score_total::numeric, 3) AS total
FROM inlinks_sugeridos
WHERE execucao_id = '<eid>'
ORDER BY score_total DESC;
```

`motivo_rejeicao` para os caso forçados deve agora ser:
- "Termo 'imobiliária' não aparece em título/resumo do destino..." (se LLM tentou alucinação)
- "Âncora não menciona termo específico 'imobiliária' do destino." (caso mais provável)
- "Termo 'negócio' é muito genérico..." (se LLM tentou stopword)

---

## 4. Fora de escopo

- **Synonym expansion** (sinônimos via embedding word-level ou WordNet) — Voyage Rerank / Cohere Rerank cobrem isso. Avaliar opção C (cross-encoder dedicado) se este filtro for restritivo demais.
- **Substituir parser manual por `with_structured_output()` + Pydantic** — mais idiomático, requer refactor do `_InseridorAgent`. Adiar.
- **Re-prompt automático** quando o LLM falha o filtro 1ª vez — pode duplicar custo do Inseridor; medir antes.
- **Stopwords expandidas via análise de corpus do tenant** — `STOPWORDS_GENERICAS` é estática; tunar via log.

---

## 5. Riscos

- **Falso-positivo** (link bom rejeitado): se o destino usa termo técnico que o pilar parafraseia ("loja virtual" no destino, "ecommerce" no pilar), validação léxica não pega o match. Mitigação: `palavras_chave` do destino é incluída no `destino_texto`, e o Enriquecedor extrai sinônimos. Se o caso aparecer, expandir verificação para `categoria` também.
- **LLM aprende a sempre devolver uma stopword no campo** para não falhar — filtro de stopwords cobre. Em última instância, o LLM pode entregar termo válido só porque foi forçado, ainda que o link não seja realmente bom; mas isso é melhor que o caso atual (links 100% forçados aplicados).
- **`_STOPWORDS_GENERICAS` precisa ser tunada por domínio** (ex: para nicho jurídico, "empresa" é específico). Mitigação: começar com lista mínima de PT-BR para nicho "abrir empresa"; ajustar via observação de logs.
- **Custo zero adicional**: mesma chamada LLM, sem chamada nova. Apenas mais 1 campo no JSON e validação Python.

---

## 6. Arquivos críticos

### Backend — alterado
- `backend/app/agents/inlinks/inseridor.py`:
  - `_STOPWORDS_GENERICAS` (constante novo).
  - `_normalize_token`, `_contem_termo` (helpers novos).
  - `_build_prompt_focado` (regra 7 + exemplo de recusa + campo no JSON).
  - `_parse_proposta_unica` (comentário; comportamento atual já correto).
  - `_validar_palavra_chave_destino` (helper novo).
  - `_propor_insercao_para_candidato` (chama validação + marca `forcar_sugestao_manual`).

### Frontend / Migration
- Nenhuma alteração.

---

## 7. Verificação (sumário)

1. Grep confirma `_STOPWORDS_GENERICAS`, `_validar_palavra_chave_destino`, `palavra_chave_destino` no `inseridor.py`.
2. Restart sem erro.
3. Re-E2E com pilar "o-que-montar-para-ganhar-dinheiro" + 4 satélites Agilize:
   - **imobiliária deve cair em sugestao_manual** com motivo "Âncora não menciona termo específico 'imobiliária'..." ou "Termo '<X>' é muito genérico...".
   - **loja-virtual continua aplicado** (palavra-chave "dropshipping" ou "loja virtual" presente).
4. Tempo de execução não muda (sem chamada LLM extra).
