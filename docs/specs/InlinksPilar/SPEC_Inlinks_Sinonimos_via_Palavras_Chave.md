# SPEC — Inlinks: aceitar sinônimos do destino via `palavras_chave` e parágrafo inteiro

**Status:** pendente
**Escopo:** backend (`inseridor.py` apenas)
**Crédito:** não muda (sem chamada LLM extra)
**Depende de:** `SPEC_Inlinks_Especificidade_Lexica.md` aplicada

---

## Contexto

Teste E2E #4 (`8603cf2a`) mostrou que `SPEC_Inlinks_Especificidade_Lexica.md` **eliminou os links forçados** (imobiliária, restaurante, agência-viagens recusados com `{}`), mas **também derrubou um link bom**: a loja-virtual.

### O que aconteceu

- LLM escolheu `palavra_chave_destino = "loja virtual"`.
- Validação léxica exigiu "loja virtual" em `anchor_text + trecho_original`.
- "loja virtual" não aparece literal no pilar genérico → LLM alucinou trecho.
- Fallback derrubou: "Trecho 'loja virtual' não encontrado em nenhum parágrafo elegível."

### Histórico do mesmo link (execução `39b2a020`, antes da SPEC anterior)

- LLM havia escolhido âncora **"Negócios digitais, consultorias, serviços por demanda ou revenda sem estoque (como dropshipping)"**.
- "dropshipping" estava em `palavras_chave` do destino (Enriquecedor extrai sinônimos).
- O link foi aplicado e era semanticamente perfeito.

### Diagnóstico

A regra 7 atual é **léxicamente cega a sinônimos**: exige a palavra exata do título no âncora. Em SaaS multi-tenant onde Enriquecedor já extrai `palavras_chave` (sinônimos do conteúdo), essa informação está sendo ignorada.

### Resultado esperado

Expandir validação léxica para considerar:
1. Qualquer termo em `palavras_chave` do destino (extraído pelo Enriquecedor) — captura sinônimos legítimos como "dropshipping" ≡ "loja virtual".
2. Match no **parágrafo inteiro** onde a âncora vive (não só `anchor + trecho`) — captura quando o LLM escolheu o trecho **porque o parágrafo fala do tema**.

Casos:
- **loja-virtual**: palavra_chave_destino = "loja virtual". `palavras_chave` do destino inclui "dropshipping" (Enriquecedor). Âncora "...revenda sem estoque (como dropshipping)" → contém "dropshipping" → ✓ aceitar.
- **imobiliária**: palavra_chave_destino = "imobiliária". `palavras_chave` do destino tipicamente: "imobiliária", "imóveis", "corretagem". Âncora "que tipo de negócio devo abrir" → nenhum dos termos aparece → ✗ rejeitar (correto).
- **restaurante**: `palavras_chave` típicas: "restaurante", "alimentação", "cozinha". Se LLM escolher trecho que cita "cozinha" ou "alimentação", aceita; senão rejeita.

---

## 1. Resumo

Uma única entrega, tudo em `_validar_palavra_chave_destino` + prompt do Inseridor. Esforço ~10 min.

| # | Mudança | Esforço |
|---|---|---|
| 1 | Expandir conjunto de termos aceitos: `{palavra_chave_destino} ∪ palavras_chave do destino` (sem stopwords) | 4 min |
| 2 | Expandir escopo do match no pilar: incluir parágrafo inteiro onde está a âncora | 3 min |
| 3 | Atualizar prompt do Inseridor para mencionar flexibilidade (LLM pode escolher trecho com sinônimo) | 3 min |

---

## 2. Implementação

### 2.1 Refatorar `_validar_palavra_chave_destino`

`backend/app/agents/inlinks/inseridor.py`:

```python
def _termos_validos_destino(candidato: dict, palavra_chave_principal: str) -> list[str]:
    """Conjunto de termos do destino que podem servir como ponte léxica.

    Inclui:
    - palavra_chave_destino nomeada pelo LLM
    - palavras_chave extraídas pelo Enriquecedor (sinônimos/variações)

    Exclui:
    - stopwords genéricas
    - termos com menos de 3 caracteres
    """
    termos = [palavra_chave_principal]
    palavras = candidato.get("palavras_chave") or []
    if isinstance(palavras, list):
        termos.extend(str(p) for p in palavras)

    validos: list[str] = []
    vistos: set[str] = set()
    for t in termos:
        t_raw = (t or "").strip()
        if len(t_raw) < 3:
            continue
        t_norm = _normalize_token(t_raw)
        if t_norm in _STOPWORDS_GENERICAS:
            continue
        if t_norm in vistos:
            continue
        vistos.add(t_norm)
        validos.append(t_raw)
    return validos


def _validar_palavra_chave_destino(
    parsed: dict,
    candidato: dict,
    paragrafo_completo: str = "",
) -> str | None:
    """Valida que a âncora menciona termo específico do destino ou um sinônimo.

    Critérios:
    1. palavra_chave_destino não-vazia e não-stopword.
    2. Pelo menos UM termo válido (palavra_chave OU palavras_chave do destino)
       aparece em anchor + trecho_original + parágrafo_completo.
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

**Diferenças vs versão atual:**
- Agora o terceiro check (overlap léxico) busca em **qualquer um** dos termos válidos (palavra_chave + palavras_chave do destino), não só na palavra_chave nomeada pelo LLM.
- Aceita parágrafo completo como contexto de busca, não só âncora+trecho.
- Mensagem de erro lista quais termos eram esperados — facilita debug.

### 2.2 Passar parágrafo completo do call site

Em `_propor_insercao_para_candidato`, após `parsed["paragrafo_idx"] = idx_global`, recuperar o parágrafo:

```python
_, paragrafo_completo = contexto_paragrafos[idx_local]

motivo_kw = _validar_palavra_chave_destino(parsed, candidato, paragrafo_completo)
```

(O `contexto_paragrafos` é `list[tuple[int, str]]` — `(idx_global, texto)`. Já temos o texto na mão.)

### 2.3 Atualizar prompt do Inseridor

Em `_build_prompt_focado`, ajustar a regra 7 para refletir a flexibilidade:

```python
7. **`palavra_chave_destino`**: substantivo ou nome próprio ESPECÍFICO do destino que está presente no parágrafo escolhido (ou via sinônimo direto, como "dropshipping" para "loja virtual"). Exemplos válidos: "restaurante", "loja virtual", "imobiliária", "dropshipping", "MEI". NÃO use palavras genéricas como "negócio", "empresa", "abrir", "tipo", "investimento", "como". Se o parágrafo não menciona o destino nem alude a ele (nem por sinônimo), retorne `{{}}` — não force.
```

Substituir o segundo exemplo (de recusa) para reforçar o conceito de sinônimo:

```
EXEMPLO de quando recusar:

Parágrafo: "Antes de empreender, faça um estudo de mercado completo."
URL destino: como-abrir-uma-imobiliaria (palavras-chave: imobiliária, imóveis, corretagem)

Nenhum termo específico do destino ("imobiliária", "imóveis", "corretagem") aparece. Resposta: {{}}.

EXEMPLO de sinônimo válido:

Parágrafo: "Revenda sem estoque, como dropshipping, é uma opção barata."
URL destino: como-abrir-uma-loja-virtual (palavras-chave: loja virtual, e-commerce, dropshipping)

"dropshipping" aparece no parágrafo E está nas palavras-chave do destino. Resposta:
{{"paragrafo_idx": 1, "trecho_original": "Revenda sem estoque", "anchor_text": "Revenda sem estoque", "palavra_chave_destino": "dropshipping", ...}}
```

### 2.4 Logging

Manter o `logger.info("Inseridor: palavra_chave_destino falhou...")`. Em DEBUG, pode adicionar lista de termos válidos para facilitar diagnóstico:

```python
if motivo_kw:
    logger.info(
        "Inseridor: palavra_chave_destino falhou para %s: %s (termos válidos: %s)",
        candidato.get("url"), motivo_kw, termos_validos[:5] if "termos_validos" in locals() else [],
    )
```

(Opcional. Pode ficar fora se simplificar.)

---

## 3. Validação ponta a ponta

### 3.1 Sanidade

```bash
grep -n "_termos_validos_destino\|paragrafo_completo" backend/app/agents/inlinks/inseridor.py | head -10
```

### 3.2 Restart

```bash
pkill -f "arq app.worker"
cd backend && nohup python3 -u -m arq app.worker.WorkerSettings > /tmp/worker.log 2>&1 &
sleep 3
```

### 3.3 Re-rodar E2E com mesmo pilar

Esperado:

| Candidata | Termos válidos (esperados via palavras_chave) | Resultado |
|---|---|---|
| **loja-virtual** | "loja virtual", "e-commerce", "dropshipping", "ecommerce" | **aplicado** — LLM escolhe trecho com "dropshipping" |
| imobiliária | "imobiliária", "imóveis", "corretagem" | **sugestao_manual** — nenhum termo aparece no pilar genérico |
| restaurante | "restaurante", "alimentação", "cozinha", "delivery" | provavelmente sugestao_manual — pilar não cita |
| agência-viagens | "agência de viagens", "turismo", "viagens" | provavelmente sugestao_manual |

Densidade esperada: 1–2 aplicados (loja-virtual fixo, mais 1 se algum sinônimo de outros casos aparecer no pilar).

### 3.4 SQL de auditoria

```sql
-- ver palavras_chave geradas pelo Enriquecedor para cada destino
SELECT url_canonica, palavras_chave
FROM conteudos_vetores
WHERE usuario_id = 'b9afa7ad-12c7-40b8-a4a7-3d0bcd4f1f31'
  AND tipo_recurso = 'candidata'
  AND chunk_index = 0
ORDER BY criado_em DESC LIMIT 5;
```

Espera-se ver "dropshipping" e similares nas palavras_chave da loja-virtual. Se não estiver, o Enriquecedor não está captando sinônimos suficientes — sintoma diferente, fora de escopo desta SPEC.

---

## 4. Fora de escopo

- **Synonym expansion via WordNet/Word2Vec** — palavras_chave do Enriquecedor são a fonte canonical de sinônimos do destino; suficiente para v1.
- **LLM judge fallback** (opção B do diagnóstico) — adiar até medir se A resolve.
- **Cross-encoder rerank** (opção C) — adiar.
- **Backfill de palavras_chave em vetores antigos** — se Enriquecedor melhorou após migration 0010, vetores velhos podem ter `palavras_chave=[]`. Decisão de produto: deletar e re-extrair, ou aceitar.

---

## 5. Riscos

- **`palavras_chave` ruidoso**: se o Enriquecedor extraiu palavras irrelevantes (ex: "blog", "artigo") como palavras-chave, a validação aceita match com elas e o link forçado volta. Mitigação: filtro de stopwords genéricas atual cobre os casos óbvios. Adicionar palavras como "blog", "artigo", "post" ao set se aparecer.
- **Sinônimo falso**: Enriquecedor pode ligar "ecommerce" a um destino sobre "lojas físicas" (overgeneralization). Mitigação: o critério `kw_raw` (palavra-chave nomeada pelo LLM) ainda precisa estar em `título+resumo`, então a validação anti-alucinação continua robusta para o termo principal.
- **Parágrafo grande aceita demais**: aceitar match no parágrafo inteiro pode amenizar a regra. Mitigação: parágrafos têm tipicamente 50–200 palavras; se o termo específico aparece, é um sinal forte. Se virar problema, restringir ao trecho_original + 60 chars de contexto antes/depois.

---

## 6. Arquivos críticos

### Backend — alterado
- `backend/app/agents/inlinks/inseridor.py`:
  - `_termos_validos_destino` (helper novo).
  - `_validar_palavra_chave_destino` (assinatura ganha `paragrafo_completo`; lógica de match expande termos e escopo).
  - `_propor_insercao_para_candidato` (passa `paragrafo_completo`).
  - `_build_prompt_focado` (regra 7 reescrita + novo exemplo de sinônimo).

### Frontend / Migration
- Nenhuma alteração.

---

## 7. Verificação (sumário)

1. Grep confirma `_termos_validos_destino`, `paragrafo_completo` no `inseridor.py`.
2. Restart sem erro.
3. Re-E2E com pilar "o-que-montar-para-ganhar-dinheiro":
   - **loja-virtual deve voltar a ser aplicado** (anchor com "dropshipping" passa via palavras_chave).
   - **imobiliária continua sugestao_manual** (nenhum sinônimo no pilar).
4. Log mostra termos válidos quando falha (debug).
5. Custo: 0 LLM extra; mesma performance.
