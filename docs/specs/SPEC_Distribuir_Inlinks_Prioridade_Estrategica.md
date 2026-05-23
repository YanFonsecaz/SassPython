# SPEC — Distribuir Inlinks: priorizacao estrategica das ancoras preferidas

**Status:** pendente · **Escopo:** backend + frontend · **Credito:** nao muda · **Depende de:** SPEC_Distribuir_Inlinks_Ancoras_Preferidas.md aplicada

## 1. Resumo executivo

Apos validacao com cliente real (Mundo Cristao, URL alvo `/categoria-produto/livros/mulheres/`), identificamos 4 problemas que reduzem o aproveitamento das ancoras preferidas e a confianca do usuario no resultado:

| # | Sintoma | Causa-raiz | Severidade |
|---|---|---|---|
| A | Ancora preferida valida foi marcada como "sugestao_manual" com motivo "termo nao esta nas palavras-chave do destino" | Validador rejeita antes do bypass de ancora preferida | **Critica** |
| B | Label "URL que vai receber os links internos" confunde o time | UX ambigua | Baixa |
| C | 4 de 5 candidatas aplicadas escolheram ancoras genericas em vez das preferidas | Prompt instrui de forma branda; LLM prefere variantes "naturais" | **Alta** |
| D | Ferramenta substitui links existentes sem aviso | `_find_trecho_in_paragrafo` ignora `[texto](url)` ja presente | Media |

Alem disso, cliente solicitou duas features:

- **E — CTA "Leia tambem"**: quando nenhuma ancora preferida cabe no texto, gerar CTA `> Leia tambem: [ancora](url-alvo)` no fim do paragrafo mais tematicamente relevante.
- **F — Campo "objetivo da linkagem"**: campo opcional para mini-prompt estrategico (ex.: "foco em conversao para categoria de produto"), incorporado ao prompt do Inseridor.

Entrega em 3 fases, ~1h45min de implementacao total. 1 PR com 3 commits.

| Fase | Entregas | Esforco |
|---|---|---|
| **1** | A (bug validador) + B (label UX) | 10 min |
| **2** | C (endurecer prioridade) + D (trecho ja-linkado) | 45 min |
| **3** | E (CTA Leia tambem) + F (objetivo linkagem) | 55 min |

## 2. Diagnostico tecnico das causas-raiz

### Causa-raiz A — bypass de ancora preferida vem DEPOIS do return

Arquivo: `backend/app/agents/inlinks/inseridor.py:532-588` em `_validar_palavra_chave_destino`.

Ordem atual:

```python
async def _validar_palavra_chave_destino(parsed, candidato, paragrafo_completo, usuario_id, ancoras_preferidas=None):
    kw_raw = (parsed.get("palavra_chave_destino") or "").strip()
    # ... validacoes basicas ...

    destino_texto = f"{titulo} {resumo} {palavras_chave_str}"

    if not _contem_termo(destino_texto, kw_raw):
        # ... log + return ...
        return (
            f"Termo '{kw_raw}' nao esta nas palavras-chave do destino. "
            f"Inseridor deveria escolher um da lista: {amostra}."
        )

    # ⚠️ ESTE CHECK NUNCA RODA SE _contem_termo FALHA ACIMA
    if ancoras_preferidas and _ancora_preferida_match(kw_raw, ancoras_preferidas):
        return None

    # ... resto da validacao ...
```

**Sintoma observado**: alvo em modo `slug_only` tem palavras-chave restritas a `["livro", "livros", "mulher", "mulheres", "livros mulheres"]`. LLM corretamente escolheu "livros para mulheres" como `palavra_chave_destino` (porque o trecho continha a ancora preferida "livros para mulheres cristas"). Validador rejeitou porque "livros para mulheres" nao esta literalmente em "Arquivo de Mulheres livro livros mulher mulheres livros mulheres".

**Por que o sistema esta certo em ter esse gating em geral**: protege contra LLM inventar sinonimos que nao tem relacao com o destino. **Mas a ancora preferida e uma autorizacao explicita do usuario** — quando o LLM escolhe um termo que bate com ancora preferida, deve passar.

### Causa-raiz C — instrucao branda + boost insuficiente

Arquivo: `inseridor.py:411-483` em `_build_prompt_focado`.

O bloco atual de ancoras preferidas:

```
ANCORAS PREFERIDAS (use uma destas quando o paragrafo permitir naturalmente):
- "livros para mulheres cristas"
- "livros cristaos para mulheres"
- "literatura crista para mulheres"

REGRA: se algum paragrafo contem uma destas ancoras (literal ou flexionada), USE-A como `anchor_text`. ...
```

Problemas:

1. "quando o paragrafo permitir naturalmente" e abertura para o LLM nao usar.
2. A regra principal aparece no final do prompt, depois das 7 regras gerais. LLMs costumam priorizar regras anteriores.
3. O LLM pode escolher trecho mais curto/natural (ex.: "o papel da mulher") dentro do mesmo paragrafo, mesmo o paragrafo contendo a ancora preferida.
4. `_aplicar_insercoes:759-762` define `ancora_preferida_usada=True` so se `_ancora_preferida_match(v["anchor_text"], ancoras_preferidas)` der match — se o LLM truncou, o badge nao aparece.

### Causa-raiz D — `_find_trecho_in_paragrafo` ignora links existentes

Arquivo: `inseridor.py:591-603`.

```python
def _find_trecho_in_paragrafo(paragrafo: str, trecho_original: str) -> int | None:
    # ... busca offset literal do trecho ...
```

Nao filtra trechos dentro de `[texto](url)`. Em `_aplicar_insercoes`, o offset retornado e usado para inserir `[anchor](url-alvo)`, podendo:

- Quebrar markdown se o trecho cair dentro de `[...]` (gera `[text [novo](alvo) o]`)
- Substituir intencao do link existente (cliente reclamou disso explicitamente)

**Decisao de produto**: quando o trecho esta dentro de link existente, virar `sugestao_manual` com motivo claro, **exceto** quando o link existente ja aponta para a `url-alvo` (caso em que e redundante e a sugestao deve ser silenciada).

## 3. Fase 1 — Bugs criticos + UX

### Entrega A — Bug do validador (10 min)

Arquivo: `backend/app/agents/inlinks/inseridor.py`

Reordenar `_validar_palavra_chave_destino` para que o bypass de ancora preferida ocorra **antes** do gating por `_contem_termo(destino_texto, kw_raw)`. Justificativa: ancoras preferidas sao autorizacao explicita do usuario e devem dominar a validacao por palavras-chave do destino.

**Diff conceitual**:

```python
async def _validar_palavra_chave_destino(
    parsed, candidato, paragrafo_completo, usuario_id, ancoras_preferidas=None,
):
    kw_raw = (parsed.get("palavra_chave_destino") or "").strip()
    if not kw_raw or len(kw_raw) < 2:
        return "Inseridor nao nomeou termo especifico do destino."

    kw_norm = _normalize_token(kw_raw)
    if kw_norm in _STOPWORDS_GENERICAS:
        return f"Termo '{kw_raw}' e muito generico para servir de ancora especifica."

    # ✅ MOVIDO PARA ANTES — ancora preferida e autorizacao explicita do usuario
    if ancoras_preferidas and _ancora_preferida_match(kw_raw, ancoras_preferidas):
        return None

    titulo = candidato.get("titulo", "") or ""
    resumo = candidato.get("resumo", "") or ""
    palavras_chave = candidato.get("palavras_chave", []) or []
    palavras_chave_str = " ".join(palavras_chave) if isinstance(palavras_chave, list) else str(palavras_chave)
    destino_texto = f"{titulo} {resumo} {palavras_chave_str}"

    if not _contem_termo(destino_texto, kw_raw):
        # ... log + return mensagem de erro (como hoje) ...

    # ... resto da validacao (verifica termos validos no contexto da ancora) ...
```

Tambem checar a ancora preferida no fluxo do `anchor_text` real (nao so na `palavra_chave_destino`): se o `anchor_text` ou o `trecho_original` contem variante da ancora preferida, validador aceita mesmo se a `palavra_chave_destino` informada pelo LLM for irregular. Adicionar essa verificacao tambem antes do gating:

```python
if ancoras_preferidas:
    anchor = (parsed.get("anchor_text") or "").strip()
    trecho = (parsed.get("trecho_original") or "").strip()
    if _ancora_preferida_match(anchor, ancoras_preferidas) or _ancora_preferida_match(trecho, ancoras_preferidas):
        return None
```

### Entrega B — Label UX (1 min)

Arquivo: `frontend/src/components/ferramentas/formulario-distribuir-inlinks.tsx:248-250`

```tsx
{/* ANTES */}
<p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
  URL que vai receber os links internos
</p>

{/* DEPOIS */}
<p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
  URL alvo a ser linkada nas paginas satelites
</p>
```

Sem mudanca em campo, hint ou label do input — so o titulo do bloco. Atualiza tambem o titulo do Step 0 no array `STEPS` se necessario (atualmente "URL alvo", esta OK).

## 4. Fase 2 — Refinamento da prioridade e seguranca

### Entrega C — Endurecer prioridade da ancora preferida (25 min)

#### C.1 — Reescrever bloco do prompt para regra dura

Arquivo: `backend/app/agents/inlinks/inseridor.py:411-483` em `_build_prompt_focado`.

O bloco `ANCORAS PREFERIDAS` passa a ser **regra zero**, antes das 7 regras gerais, com instrucao imperativa:

```
ANCORAS PREFERIDAS (PRIORIDADE MAXIMA):
- "livros para mulheres cristas"
- "livros cristaos para mulheres"
- "literatura crista para mulheres"

REGRA ZERO (sobrepõe todas as outras): se QUALQUER paragrafo contem uma destas ancoras
(literal, flexionada, ou cobertura por todas as palavras), VOCE DEVE:
1. Escolher esse paragrafo (mesmo se outro pareca mais natural).
2. Usar a ancora preferida LITERAL como `anchor_text` (sem truncar).
3. Copiar `trecho_original` do paragrafo de forma que CONTENHA a ancora.
4. Reportar `palavra_chave_destino` como a propria ancora preferida.

So aplique as 7 regras abaixo quando NENHUM paragrafo contem variante de
uma ancora preferida.
```

E exemplo concreto adicional:

```
EXEMPLO 0 — ancora preferida no paragrafo (PRIORIDADE):

ANCORAS PREFERIDAS: ["livros para mulheres cristas"]
Paragrafo L0: "... livros para mulheres cristas representam mais de 40% do nosso catalogo ..."
URL destino: /categoria-produto/livros/mulheres/

Resposta CORRETA:
{"paragrafo_idx": 0, "trecho_original": "livros para mulheres cristas representam",
 "anchor_text": "livros para mulheres cristas",
 "palavra_chave_destino": "livros para mulheres cristas",
 "justificativa": "Trecho contem ancora preferida literal."}

Resposta INCORRETA (truncou ancora preferida):
{"anchor_text": "livros", "palavra_chave_destino": "livros", ...}
```

#### C.2 — Boost determinístico no `_selecionar_paragrafos_relevantes`

Arquivo: `inseridor.py:299-336`.

Atualmente boost de `0.30` competindo com cosine + keyword_boost. Subir para `0.60` (acima do range natural do cosine, que e tipicamente 0.4–0.85). Garante que paragrafo com ancora preferida sempre rankeie no top-1.

```python
def _ancora_preferida_boost(paragrafo: str, ancoras: list[str]) -> float:
    if not ancoras or not paragrafo:
        return 0.0
    return 0.60 if _ancora_preferida_match(paragrafo, ancoras) else 0.0
```

#### C.3 — Reorder do top-N: paragrafos com ancora preferida primeiro

Em `_selecionar_paragrafos_relevantes`, depois do `scored.sort`, reorganizar para que paragrafos com ancora preferida sejam os primeiros do top-N:

```python
scored.sort(key=lambda x: x[2], reverse=True)
top = scored[:top_n]

if ancoras_preferidas:
    top.sort(key=lambda x: _ancora_preferida_match(x[1], ancoras_preferidas) is not None, reverse=True)

return [(i, p) for i, p, _, _ in top]
```

Isso garante que no prompt o paragrafo L0 sempre tenha a ancora preferida (quando existe).

#### C.4 — Forcar anchor_text correto quando o LLM truncar

No `_propor_insercao_para_candidato:339-408`, apos parsear a resposta e antes de validar:

```python
if ancoras_preferidas and parsed:
    paragrafo_escolhido = contexto_paragrafos[parsed.get("paragrafo_idx", 0)][1]
    ancora_no_paragrafo = _ancora_preferida_match(paragrafo_escolhido, ancoras_preferidas)
    anchor_llm = (parsed.get("anchor_text") or "").strip()
    if ancora_no_paragrafo and not _ancora_preferida_match(anchor_llm, ancoras_preferidas):
        # LLM escolheu trecho do paragrafo que contem ancora preferida, mas truncou.
        # Forcar o anchor_text para a ancora preferida e ajustar trecho_original.
        parsed["anchor_text"] = ancora_no_paragrafo
        # trecho_original mantem o que LLM extraiu (deve conter a ancora pela regra zero do prompt)
        # mas se nao contiver, fallback: usar a propria ancora se ela aparecer no paragrafo literal
        if ancora_no_paragrafo.lower() in paragrafo_escolhido.lower():
            parsed["trecho_original"] = ancora_no_paragrafo
        parsed["palavra_chave_destino"] = ancora_no_paragrafo
        logger.info(
            "Inseridor: forcando anchor_text para ancora preferida '%s' (LLM havia escolhido '%s')",
            ancora_no_paragrafo, anchor_llm,
        )
```

### Entrega D — Detectar trecho ja-linkado (20 min)

Arquivo: `backend/app/agents/inlinks/inseridor.py`

Adicionar funcao auxiliar para checar se um offset esta dentro de `[texto](url)` no paragrafo:

```python
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

def _link_existente_em(paragrafo: str, offset: int) -> str | None:
    """Retorna a URL do link existente se `offset` cai dentro de um [texto](url). None caso contrario."""
    for m in _MD_LINK_RE.finditer(paragrafo):
        if m.start() <= offset < m.end():
            return m.group(2)
    return None
```

E aplicar em `_aplicar_insercoes`, logo apos `local_offset` ser determinado e antes da insercao:

```python
local_offset = _find_trecho_in_paragrafo(paragrafo, trecho_original)
if local_offset is None:
    # ... fallback existente ...

# ✅ NOVO — detecta trecho dentro de link existente
url_existente = _link_existente_em(paragrafo, local_offset)
if url_existente:
    url_alvo_norm = _normalizar_url(url)
    url_existente_norm = _normalizar_url(url_existente)
    if url_alvo_norm == url_existente_norm:
        # Link ja existe para a URL alvo — pulando silenciosamente
        sugestoes.append({
            **ins,
            "motivo_sugestao": f"Trecho ja e link para a URL alvo. Nenhuma acao necessaria.",
        })
        continue
    else:
        # Link existente para outra URL — virar sugestao manual
        sugestoes.append({
            **ins,
            "motivo_sugestao": (
                f"Trecho '{trecho_original[:50]}' ja e link para outra URL ({url_existente[:60]}). "
                f"Avalie manualmente se substituir traz ganho estrategico."
            ),
        })
        continue
```

Importar `_normalizar_url` no topo:

```python
from app.core.scraper import _normalizar_url
```

## 5. Fase 3 — Features novas

### Entrega E — CTA "Leia tambem" como fallback (30 min)

#### E.1 — Comportamento

Quando o usuario forneceu pelo menos 1 ancora preferida E nenhum paragrafo da candidata contem variante dela, o sistema:

1. Identifica o paragrafo top-1 da candidata por relevancia tematica (cosine).
2. Adiciona ao final daquele paragrafo: `\n\n> Leia tambem: [{ancora_preferida_1}]({url_alvo})`

A primeira ancora preferida fornecida pelo usuario tem prioridade. O CTA usa formato de blockquote markdown (`>`) para ser visualmente distinto.

**Restricoes**:

- Aplicar apenas se o cosine entre o paragrafo top-1 e o destino for >= 0.55 (evita CTA em paragrafo nao relacionado).
- Aplicar apenas se o paragrafo nao termina em `>` (ja e blockquote, nao misturar).
- Skip se o markdown da candidata ja contem string "Leia tambem:" (idempotencia).

#### E.2 — Feature flag

Novo campo opcional no `DistribuirInlinksRequest`:

```python
permitir_cta_fallback: bool = Field(default=True)
```

Frontend: checkbox no Step 1 (junto com max_inlinks / threshold / rel_attr): "Permitir CTA 'Leia tambem' quando ancora nao cabe naturalmente".

#### E.3 — Implementacao

Em `inserir_inlinks` (`inseridor.py:114-220`), apos o loop normal de candidatos, se nenhuma proposta foi `aplicado` e ha ancoras preferidas:

```python
# Apos o loop principal, antes de retornar
if (
    ancoras_preferidas and permitir_cta_fallback
    and not any(p for _, p in propostas_por_candidato if p and not p.get("forcar_sugestao_manual"))
):
    cta_proposta = await _gerar_cta_fallback(
        paragrafos, paragrafos_embeddings, candidatos_top[0], ancoras_preferidas, usuario_id,
    )
    if cta_proposta:
        todas_insercoes.append(cta_proposta)
```

E nova funcao:

```python
async def _gerar_cta_fallback(
    paragrafos: list[str],
    paragrafos_embeddings: list[Any],
    candidato: dict[str, Any],
    ancoras_preferidas: list[str],
    usuario_id: str,
) -> dict[str, Any] | None:
    consulta = _texto_destino(candidato)[:1500]
    emb_consulta_lst = await gerar_embeddings_batch([consulta], usuario_id)
    emb_consulta = emb_consulta_lst[0] if emb_consulta_lst else None
    if emb_consulta is None:
        return None

    scored: list[tuple[int, str, float]] = []
    for i, (p, emb_p) in enumerate(zip(paragrafos, paragrafos_embeddings, strict=False)):
        if emb_p is None or not _paragrafo_elegivel(p):
            continue
        if "leia tambem:" in p.lower() or p.strip().endswith(">"):
            continue
        cosine = cosine_seguro(emb_consulta, emb_p)
        scored.append((i, p, float(cosine)))

    if not scored:
        return None

    scored.sort(key=lambda x: x[2], reverse=True)
    p_idx, paragrafo, cos = scored[0]
    if cos < 0.55:
        return None

    ancora = ancoras_preferidas[0]
    return {
        "url_destino": candidato["url"],
        "paragrafo_idx": p_idx,
        "anchor_text": ancora,
        "trecho_original": "",
        "_modo_cta": True,
        "_ancora_cta": ancora,
        "justificativa": (
            f"Nenhum paragrafo continha variante da ancora preferida. "
            f"CTA adicionado no fim do paragrafo {p_idx} (cosine={cos:.2f})."
        ),
    }
```

E em `_aplicar_insercoes`, tratamento especial para `_modo_cta`:

```python
for ins in insercoes_raw:
    # ...
    if ins.get("_modo_cta"):
        p_idx = ins.get("paragrafo_idx", -1)
        if p_idx < 0 or p_idx >= len(paragrafos):
            continue
        ancora = ins.get("_ancora_cta", "")
        cta = f"\n\n> Leia tambem: [{ancora}]({ins['url_destino']})"
        # Insere apos o paragrafo, no markdown completo
        # (sera processado no final, junto com as outras insercoes)
        validas.append({
            "url": ins["url_destino"],
            "paragrafo_idx": p_idx,
            "global_offset": sum(len(p) + 2 for p in paragrafos[:p_idx + 1]) - 2,
            "trecho_original": "",
            "anchor_text": ancora,
            "conector_antes": cta,
            "conector_depois": "",
            "justificativa": ins.get("justificativa", ""),
            "candidato": candidatos_by_url[ins["url_destino"]],
            "_modo_cta": True,
        })
        continue
    # ... resto da logica ...
```

E na hora da substituicao do texto (loop `for v in validas`), modo CTA insere `ca` direto sem `[anchor](url)` (porque ja esta no `ca`):

```python
for v in validas:
    if v.get("_modo_cta"):
        offset = v["global_offset"]
        texto = texto[:offset] + v["conector_antes"] + texto[offset:]
        v["link_md_len"] = len(v["conector_antes"])
        continue
    # ... logica normal ...
```

### Entrega F — Campo "objetivo da linkagem" (25 min)

#### F.1 — Schema

Arquivo: `backend/app/schemas/inlinks_reversos.py`

```python
class DistribuirInlinksRequest(BaseModel):
    # ... campos existentes ...
    objetivo_linkagem: str | None = Field(default=None, max_length=300)

    @field_validator("objetivo_linkagem")
    @classmethod
    def validar_objetivo(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        return s
```

#### F.2 — Workflow

`backend/app/agents/workflow_inlinks_reversos.py`

- Adicionar `objetivo_linkagem: str | None` em `EstadoDistribuir`
- Ler de `entrada.get("objetivo_linkagem")` em `executar_workflow_distribuir_inlinks`
- Propagar em `node_inserir_em_cada` para `inserir_inlinks(..., objetivo_linkagem=objetivo)`

#### F.3 — Inseridor

`backend/app/agents/inlinks/inseridor.py`

Adicionar parametro `objetivo_linkagem: str | None = None` em `inserir_inlinks` e `_propor_insercao_para_candidato`. Propagar para `_build_prompt_focado` e injetar bloco no prompt antes das regras:

```python
if objetivo_linkagem:
    bloco_objetivo = f"""
OBJETIVO ESTRATEGICO DA LINKAGEM:
{objetivo_linkagem}

Use esse objetivo como filtro de qualidade: prefira ancoras e trechos
alinhados a essa intencao. Se o objetivo mencionar "conversao" ou
"categoria de produto", priorize ancoras com substantivos especificos
do nicho comercial (nao termos vagos como "tema" ou "papel").
"""
else:
    bloco_objetivo = ""
```

#### F.4 — Frontend

`frontend/src/components/ferramentas/formulario-distribuir-inlinks.tsx`

Novo state:

```tsx
const [objetivoLinkagem, setObjetivoLinkagem] = useState("");
```

Novo bloco no Step 0, depois de Ancoras preferidas:

```tsx
<div className="space-y-2 pt-2">
  <div className="flex items-center gap-1.5">
    <Label htmlFor="objetivo" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
      Objetivo da linkagem (opcional)
    </Label>
    <span title="Direcionamento estrategico que a ferramenta usa para escolher ancoras alinhadas ao seu objetivo. Ex.: 'foco em conversao para categoria de produto', 'fortalecimento semantico'.">
      <InfoIcon className="size-3 text-muted-foreground/60" />
    </span>
  </div>
  <Textarea
    id="objetivo"
    placeholder="ex.: foco em conversao para categoria de produto"
    maxLength={300}
    value={objetivoLinkagem}
    onChange={(e) => { setObjetivoLinkagem(e.target.value); }}
    disabled={enviando}
    rows={2}
  />
</div>
```

E adicionar `objetivo_linkagem` no payload:

```tsx
const body: DistribuirInlinksRequest = {
  // ...
  objetivo_linkagem: objetivoLinkagem.trim() || undefined,
};
```

Tipo em `frontend/src/types/ferramenta.ts`:

```typescript
export interface DistribuirInlinksRequest {
  // ...
  objetivo_linkagem?: string;
}
```

## 6. Verificacao ponta a ponta

### 6.1 Restart

```bash
pkill -f "uvicorn app.main"; pkill -f "arq app.worker"
cd backend && nohup python3 -u -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
cd backend && nohup python3 -u -m arq app.worker.WorkerSettings > /tmp/worker.log 2>&1 &
sleep 3
curl -sf -o /dev/null -w "Backend: %{http_code}\n" http://localhost:8000/health
```

### 6.2 Frontend

```bash
cd frontend && npm run build && cp -r out/* ../backend/static/
```

### 6.3 Execucao E2E real (mesma da Tathi)

URL alvo: `https://www.mundocristao.com.br/categoria-produto/livros/mulheres/`
Ancoras preferidas: `livros para mulheres cristas`, `livros cristaos para mulheres`, `literatura crista para mulheres`
Objetivo: "foco em conversao para categoria de produto de livros"
10 URLs candidatas (mesmo lote).

**Checks de aceitacao**:

1. **Bug A corrigido**: o artigo "Livros para mulheres cristas: obras que tocam a alma" (`/blog/livros-para-quem-atua-em-ministerios-de-mulheres`) deve sair de `sugestao_manual` para `aplicado`, com ancora preferida visivel.
2. **Label UX (B)**: Step 0 mostra "URL alvo a ser linkada nas paginas satelites".
3. **Endurecer prioridade (C)**: das ~5 candidatas que aplicarem inlink, **pelo menos 4** devem ter badge "Ancora preferida". Casos restantes so quando o conteudo realmente nao tem variante da ancora.
4. **Trecho ja-linkado (D)**: simular caso com candidata que tem `[mulheres](outra-url)` no markdown — deve virar sugestao manual com motivo claro.
5. **CTA fallback (E)**: em candidatas onde nenhuma ancora preferida cabe, validar que CTA `> Leia tambem: [ancora](alvo)` aparece no fim de paragrafo tematico. Apenas quando feature flag `permitir_cta_fallback` esta ativo.
6. **Objetivo linkagem (F)**: log do worker deve mostrar "OBJETIVO ESTRATEGICO DA LINKAGEM:" nos prompts, e justificativas geradas pelo LLM devem citar a intencao quando relevante.

### 6.4 Persistencia

```bash
sqlite3 ou psql:
SELECT
  json_extract(resultado_json, '$.candidatas[*].ancora_preferida_usada') AS ancoras_usadas,
  json_extract(resultado_json, '$.candidatas[*].status') AS statuses
FROM execucoes_ferramenta
WHERE id = '<execucao_id_de_teste>';
```

Esperado: maioria das aplicadas com `ancora_preferida_usada=true`.

### 6.5 Sanidade de imports e lint

```bash
cd backend && python3 -c "from app.agents.inlinks.inseridor import inserir_inlinks; print('OK')"
cd backend && python3 -c "from app.schemas.inlinks_reversos import DistribuirInlinksRequest; print('OK')"
cd frontend && npm run lint
```

## 7. Fora de escopo

- Resolver problema arquitetural de "inserir CTA via LLM gera resultados mais naturais" — mantemos template deterministico nesta versao (mais robusto, sem custo extra de chamada).
- Substituir Inseridor por modelo maior (gpt-4-turbo) — gpt-4.1 ja e suficiente quando o prompt e claro.
- Persistir log estruturado de quais ancoras foram usadas vs. rejeitadas para metricas agregadas — adicionar em v3.
- Permitir multiplas ancoras CTA por candidata — primeira ancora preferida e o suficiente para validacao inicial.

## 8. Riscos

- **C.4 (forcar anchor_text)** pode quebrar coesao gramatical se a ancora preferida nao casa com a estrutura do trecho. Mitigacao: aplicar apenas quando `_ancora_preferida_match` retorna match exato no paragrafo (nao bigrama frouxo), evitando substituicoes agressivas.
- **D (trecho ja-linkado)** pode aumentar `sugestao_manual` em sites com muita linkagem interna previa. Tradeoff aceito: cliente reclamou explicitamente desse comportamento.
- **E (CTA)** pode poluir markdown se o paragrafo top-1 estiver mal escolhido. Mitigacao: piso cosine >= 0.55 + verificacoes de paragrafo elegivel.
- **F (objetivo)** pode confundir o LLM se o texto for ambiguo. Mitigacao: campo opcional, default e null, hint da UI explica boas praticas.

## 9. Decisoes explicitas

- **Bypass de ancora preferida e dominante** sobre validacao de palavras-chave do destino. Razao: usuario sabe o que esta fazendo; nossa heuristica nao deve impedir sua intencao.
- **Boost de 0.60** (acima do range cosine) garante que paragrafos com ancora preferida sempre sejam top-1. Razao: outras heuristicas (cosine, keyword_boost) sao para o caso geral, nao devem competir com instrucao explicita do usuario.
- **CTA usa blockquote (`>`)** e nao paragrafo plano. Razao: visualmente distinto, deixa claro que e CTA, nao confunde com texto natural do autor.
- **Objetivo linkagem** entra no prompt como contexto antes das regras, nao como regra. Razao: regras LLM devem ser claras e poucas; objetivo e filtro de qualidade, nao restricao dura.

## 10. Estimativa de esforco

| Fase | Item | Esforco |
|---|---|---|
| 1 | A — Bug validador | 10 min |
| 1 | B — Label UX | 1 min |
| 2 | C.1 — Prompt regra zero | 10 min |
| 2 | C.2 — Boost 0.60 | 2 min |
| 2 | C.3 — Reorder top-N | 5 min |
| 2 | C.4 — Forcar anchor_text | 10 min |
| 2 | D — Trecho ja-linkado | 20 min |
| 3 | E — CTA fallback (backend + flag + frontend) | 30 min |
| 3 | F — Objetivo linkagem (schema + workflow + inseridor + UI) | 25 min |
| — | Restart + frontend build + E2E + verificacao | 30 min |
| | **Total** | **~2h25min** |
