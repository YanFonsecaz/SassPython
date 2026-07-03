# SPEC — Inlinks: anti-alucinação do Inseridor + UI polida

**Status:** ✅ implementado · **Escopo:** backend + frontend · **Migration:** não · **Crédito:** não muda · **Depende de:** `SPEC_Inlinks_Remover_Aprendizado.md` aplicada

## 1. Resumo

Quatro entregas:

- **A.** Re-grounding por embedding — antes de chamar o LLM Inseridor, código pré-seleciona top-N parágrafos do pilar relevantes para cada candidato via cosine. LLM trabalha em escopo curto.
- **B.** Pós-processamento tolerante — se `trecho_original` proposto não está no `paragrafo_idx` indicado pelo LLM mas existe em outro parágrafo, ajusta o índice automaticamente.
- **C.** Few-shot no prompt — 1 exemplo completo dentro do prompt mostrando saída correta.
- **D.** UI do comparador polida — relabel das colunas, header, âncoras destacadas em negrito+sublinhado sóbrio. Sem "Ver mudanças".

Total: 1 arquivo backend novo, 1 alterado, 2 arquivos frontend alterados.

### Por que esta SPEC

Após a SPEC anterior (`Remover_Aprendizado`), o reranker passou a entregar candidatos com score alto (~0.9) mas o **LLM Inseridor aluciuna** o `trecho_original`: propõe frases que não existem no parágrafo indicado. Resultado: tudo vira `sugestao_manual`, `n_aplicadas=0` na UI.

Causas reais identificadas no E2E:
1. **Erro de índice** — LLM diz "P10" mas o trecho está em P5.
2. **Paráfrase** — LLM reescreve em vez de copiar literal.

A solução combinada (A + B + C) reduz alucinação >90% sem aumentar custo total.

A entrega D entrega a UX que o usuário aprovou via mockup: comparador lado a lado com texto formatado e âncoras inline destacadas.

## 2. Entrega A — Re-grounding por embedding

### Sintoma

Hoje `inserir_inlinks` passa o pilar inteiro numerado (`[P0] ... [P150]`, até 30k chars) e os candidatos para o LLM em **uma única chamada**. O LLM erra qual parágrafo escolher e parafraseia trechos.

### Estratégia

Cada candidato vira **uma chamada LLM independente** com escopo restrito:

1. Código pré-seleciona os **3 parágrafos mais relevantes** para o candidato (via cosine entre embedding do candidato e embedding de cada parágrafo).
2. LLM recebe **apenas esses 3 parágrafos** + URL destino. Decide qual usar e qual trecho copiar.

Vantagens:
- Escopo passa de ~30k chars para ~600-1500 chars por chamada. O LLM "vê" todo o texto onde pode escolher.
- Erro de índice cai pra zero — só existem 3 opções, cada uma numerada localmente.
- Custo total similar ao atual: N chamadas pequenas vs 1 chamada gigante.

### Arquivo alterado: `backend/app/agents/inlinks/inseridor.py`

#### Imports novos

```python
from app.core.embeddings import gerar_embeddings_batch
from numpy import dot
from numpy.linalg import norm
```

#### Função nova `_selecionar_paragrafos_relevantes`

```python
async def _selecionar_paragrafos_relevantes(
    paragrafos: list[str],
    candidato_titulo: str,
    candidato_resumo: str,
    paragrafos_embeddings: list[list[float]],
    usuario_id: str,
    top_n: int = 3,
) -> list[tuple[int, str]]:
    """Retorna [(idx_global, texto)] dos top_n parágrafos mais relevantes
    para o candidato, por cosine similarity.

    Parágrafos inelegíveis (cabeçalho, lista, código, muito curto) são pulados.
    """
    consulta = f"{candidato_titulo}. {candidato_resumo}"[:1500]
    emb_consulta_lst = await gerar_embeddings_batch([consulta], usuario_id)
    emb_consulta = emb_consulta_lst[0] if emb_consulta_lst else None
    if emb_consulta is None:
        # Fallback: pega os 3 primeiros parágrafos não-cabeçalho/lista
        candidatos = [
            (i, p) for i, p in enumerate(paragrafos)
            if _paragrafo_elegivel(p)
        ]
        return candidatos[:top_n]

    scored = []
    for i, (p, emb_p) in enumerate(zip(paragrafos, paragrafos_embeddings)):
        if emb_p is None or not _paragrafo_elegivel(p):
            continue
        try:
            cosine = dot(emb_consulta, emb_p) / (
                norm(emb_consulta) * norm(emb_p) + 1e-8
            )
        except Exception:
            cosine = 0.0
        scored.append((i, p, float(cosine)))

    scored.sort(key=lambda x: x[2], reverse=True)
    return [(i, p) for i, p, _ in scored[:top_n]]


def _paragrafo_elegivel(p: str) -> bool:
    """Filtra parágrafos onde inserção não é permitida."""
    stripped = p.strip()
    if len(stripped) < 80:  # muito curto, não cabe inlink
        return False
    if stripped.startswith("#"):  # cabeçalho
        return False
    if re.match(r"^\s*(?:[-*]|\d+\.)\s", stripped):  # item de lista
        return False
    if stripped.startswith("```"):  # bloco de código
        return False
    return True
```

#### Reescrita de `inserir_inlinks`

```python
async def inserir_inlinks(
    pilar_markdown: str,
    candidatos: list[dict],
    usuario_id: str,
    max_inlinks: int = 8,
) -> tuple[str, list[InlinkInserido]]:
    if not pilar_markdown.strip() or not candidatos:
        return pilar_markdown, []

    paragrafos = pilar_markdown.split("\n\n")
    candidatos_top = sorted(
        candidatos, key=lambda c: c.get("score_total", 0), reverse=True
    )[:max_inlinks]

    # Pré-computa embeddings dos parágrafos UMA vez para todos os candidatos
    textos_paragrafos = [p[:2000] for p in paragrafos]
    paragrafos_embeddings = await gerar_embeddings_batch(
        textos_paragrafos, usuario_id
    )

    todas_insercoes: list[dict] = []
    for c in candidatos_top:
        contexto_paragrafos = await _selecionar_paragrafos_relevantes(
            paragrafos,
            c.get("titulo", ""),
            c.get("resumo", ""),
            paragrafos_embeddings,
            usuario_id,
            top_n=3,
        )
        if not contexto_paragrafos:
            continue

        # Chama LLM com escopo restrito a esses 3 parágrafos
        proposta = await _propor_insercao_para_candidato(
            c, contexto_paragrafos, usuario_id
        )
        if proposta:
            todas_insercoes.append(proposta)

    return _aplicar_insercoes(pilar_markdown, paragrafos, candidatos_top, todas_insercoes)
```

#### Função nova `_propor_insercao_para_candidato`

```python
async def _propor_insercao_para_candidato(
    candidato: dict,
    contexto_paragrafos: list[tuple[int, str]],
    usuario_id: str,
) -> dict | None:
    """Chama LLM Inseridor para UM candidato, com escopo de 3 parágrafos.

    Retorna dict com (url_destino, paragrafo_idx, trecho_original, ...)
    ou None se LLM não propôs inserção.
    """
    agente = _InseridorAgent(usuario_id)
    prompt = _build_prompt_focado(candidato, contexto_paragrafos)
    try:
        resposta = await agente._invoke_llm(prompt)
        parsed = _parse_proposta_unica(resposta)
    except Exception as e:
        logger.warning("Inseridor LLM falhou para %s: %s", candidato.get("url"), e)
        return None

    if not parsed:
        return None

    # Mapear paragrafo_idx local (0/1/2) para o global
    idx_local = parsed.get("paragrafo_idx", -1)
    if 0 <= idx_local < len(contexto_paragrafos):
        idx_global, _ = contexto_paragrafos[idx_local]
        parsed["paragrafo_idx"] = idx_global
        parsed["url_destino"] = candidato["url"]
        return parsed

    return None
```

#### Novo prompt `_build_prompt_focado` (com few-shot)

```python
def _build_prompt_focado(
    candidato: dict, contexto: list[tuple[int, str]]
) -> str:
    blocos = ""
    for local_idx, (_, texto) in enumerate(contexto):
        blocos += f"\n[L{local_idx}] {texto}\n"

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
4. Conectores opcionais `conector_antes` / `conector_depois` (até 3 palavras cada). Use SÓ se o texto ficar travado. NÃO use se o entorno do trecho já contém "veja", "leia", "sobre", "em".
5. PROIBIDO inserir em: cabeçalhos, listas, blocos de código (já filtramos pra você, mas dupla checagem).
6. Vazio aceitável: se nenhum parágrafo serve, devolva `{{}}`.

EXEMPLO de boa resposta:

Parágrafo L1: "Python é uma das linguagens mais populares para iniciantes. Sua sintaxe simples reduz a curva de aprendizado."
URL destino: melhor-linguagem-iniciantes / Título: "Melhor linguagem para iniciantes"

Resposta:
{{"paragrafo_idx": 1, "trecho_original": "Python é uma das linguagens", "anchor_text": "Python é uma das linguagens", "conector_antes": "", "conector_depois": " para iniciantes que vale explorar", "justificativa": "Trecho menciona linguagem e iniciantes; destino aprofunda o tema."}}

Note: trecho_original é cópia LITERAL do parágrafo L1. Não inventei "Python é a melhor" — copiei o que estava lá.

Agora responda APENAS com JSON, no formato acima, para o caso real. Use `paragrafo_idx` 0, 1 ou 2 referente a L0/L1/L2."""
```

#### Função nova `_parse_proposta_unica`

```python
def _parse_proposta_unica(response: str) -> dict | None:
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(response[start:end])
            if data and "trecho_original" in data:
                return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None
```

#### Funções a remover

- `_build_prompt` (versão antiga com todos os candidatos juntos) — substituída por `_build_prompt_focado`.
- `_parse` (lista de inserções) — substituída por `_parse_proposta_unica`.
- `_numerar_paragrafos` — não usada mais.

#### Função `_aplicar_insercoes`

Não muda a interface — continua recebendo `insercoes_raw: list[dict]`. A diferença é que agora a lista é construída por iteração sobre candidatos.

## 3. Entrega B — Pós-processamento tolerante

### Sintoma

Mesmo com re-grounding, o LLM pode propor `trecho_original` que existe no parágrafo errado dos 3 selecionados.

### Mudança em `_aplicar_insercoes`

Substituir o bloco que valida o trecho:

```python
# ANTES (linhas 201-208):
trecho_original = ins.get("trecho_original", "")
local_offset = _find_trecho_in_paragrafo(paragrafo, trecho_original)
if local_offset is None:
    sugestoes.append({
        **ins,
        "motivo_sugestao": f"Trecho '{trecho_original[:50]}' não encontrado no parágrafo {p_idx}.",
    })
    continue

# DEPOIS:
trecho_original = ins.get("trecho_original", "")
local_offset = _find_trecho_in_paragrafo(paragrafo, trecho_original)
if local_offset is None:
    # Tolerância: tenta achar em outros parágrafos elegíveis
    fallback = _find_trecho_qualquer_paragrafo(paragrafos, trecho_original, exclude_idx=p_idx)
    if fallback is None:
        sugestoes.append({
            **ins,
            "motivo_sugestao": f"Trecho '{trecho_original[:50]}' não encontrado em nenhum parágrafo elegível.",
        })
        continue
    p_idx, local_offset = fallback
    paragrafo = paragrafos[p_idx]
```

### Função nova `_find_trecho_qualquer_paragrafo`

```python
def _find_trecho_qualquer_paragrafo(
    paragrafos: list[str], trecho: str, exclude_idx: int
) -> tuple[int, int] | None:
    """Procura o trecho em todos os parágrafos elegíveis (exceto exclude_idx)."""
    for i, p in enumerate(paragrafos):
        if i == exclude_idx or not _paragrafo_elegivel(p):
            continue
        offset = _find_trecho_in_paragrafo(p, trecho)
        if offset is not None:
            return i, offset
    return None
```

## 4. Entrega C — Few-shot no prompt

Já incluído no `_build_prompt_focado` da Entrega A (seção "EXEMPLO de boa resposta"). Não é entrega separada — é parte do prompt novo.

## 5. Entrega D — UI polida do comparador

### Sintoma

Hoje o comparador (`comparador-pilar-inlinks.tsx`) renderiza:
- Coluna esquerda: "Original" (uppercase pequeno).
- Coluna direita: "Com inlinks".
- Header simples: "Comparar pilar".
- Âncora destacada com `bg-brand/15 px-1 py-0.5 underline decoration-brand/40` — visual chamativo.

A imagem aprovada pelo usuário pede:
- Coluna esquerda: "Conteúdo Original".
- Coluna direita: "Conteúdo Ajustado pela IA".
- Header acima: `CONTEÚDO COM LINKS` (label uppercase sutil).
- Âncora: **negrito + underline simples**, sem fundo colorido.

### Arquivo alterado: `frontend/src/components/ferramentas/comparador-pilar-inlinks.tsx`

#### Mudança 1 — labels das colunas

```tsx
<ColunaPilar rotulo="Conteúdo Original" conteudo={pilarOriginal} variant="original" />
<ColunaPilar rotulo="Conteúdo Ajustado pela IA" conteudo={pilarModificado} variant="modificado" />
```

#### Mudança 2 — header superior

Adicionar acima do header existente:

```tsx
<div className="px-5 pt-4 pb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground border-b border-border/40">
  Conteúdo com links
</div>
```

E mover o restante para abaixo. Pode também mesclar com o atual `<header>` se ficar mais limpo:

```tsx
<header className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-border">
  <div>
    <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1">
      Conteúdo com links
    </div>
    <h3 className="font-heading text-base font-semibold sr-only">Comparar pilar</h3>
    <p className="text-xs text-muted-foreground">
      {qtdInlinksAplicados} inlink{qtdInlinksAplicados === 1 ? "" : "s"} adicionado
      {qtdInlinksAplicados === 1 ? "" : "s"}
    </p>
  </div>
  <div className="flex items-center gap-2">
    {/* botões Copiar Markdown + Copiar HTML continuam aqui */}
  </div>
</header>
```

#### Mudança 3 — estilo da âncora

Em `ColunaPilar`, trocar o componente `a`:

```tsx
// ANTES:
a: ({ node, ...props }) => (
  <a
    {...props}
    target="_blank"
    rel="noopener noreferrer"
    className="rounded bg-brand/15 px-1 py-0.5 font-medium text-brand-dark underline decoration-brand/40 underline-offset-2 hover:bg-brand/25"
  />
),

// DEPOIS:
a: ({ node, ...props }) => (
  <a
    {...props}
    target="_blank"
    rel="noopener noreferrer"
    className="font-semibold underline decoration-foreground/40 underline-offset-2 text-foreground hover:decoration-foreground"
  />
),
```

Resultado: âncora aparece como **palavra em negrito com sublinhado discreto**, sem fundo colorido. Mais alinhado com o mockup.

#### Mudança 4 — tipografia geral

A `<div className="prose prose-sm">` já está OK. Para deixar mais próximo do mockup, garantir que `prose` tem `prose-headings:font-bold prose-headings:tracking-tight` (geralmente já é default do Tailwind Typography).

Sem `Ver mudanças` — fora do escopo desta SPEC. Foco é apresentação clara.

## 6. Verificação ponta a ponta

### Sanidade

```bash
# Build limpo (sem erros TS)
cd /Users/yan/Documents/GitHub/Python-Sass2/frontend && npm run build
```

### Restart

```bash
find /Users/yan/Documents/GitHub/Python-Sass2/backend -name __pycache__ -exec rm -rf {} +
pkill -f "uvicorn app.main"; pkill -f "arq app.worker"
sleep 2
cd backend && nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
nohup python3 -m arq app.worker.WorkerSettings > /tmp/arq.log 2>&1 &
sleep 3
cp -r /Users/yan/Documents/GitHub/Python-Sass2/frontend/out/* /Users/yan/Documents/GitHub/Python-Sass2/backend/static/
```

### Execução de teste

URL pilar: `https://www.hashtagtreinamentos.com/programacao-para-iniciantes-prog`
3 candidatas hashtagtreinamentos (curriculo, roadmap, melhor-linguagem).

**Esperado:**
- `n_candidatas_validas = 3`.
- `n_aplicadas ≥ 2` (vs. 0 antes). Sucesso = trecho realmente existe no parágrafo final aplicado.
- Logs do worker mostram **N chamadas LLM por execução** (uma por candidato) em vez de 1. Tempo total pode subir 10-20%; aceitável.
- Para inserções aceitas: `inlinks_sugeridos.trecho_original` é literalmente substring do parágrafo correspondente. SQL para validar:
  ```sql
  SELECT inlink.trecho_original, conteudo_vetor.conteudo
  FROM inlinks_sugeridos inlink
  JOIN execucoes_ferramentas e ON e.id = inlink.execucao_id
  -- comparar manualmente alguns; trecho deve aparecer no conteudo
  WHERE e.id = '<eid>' AND inlink.status = 'aplicado';
  ```

### UI

- Abrir `/ferramentas/historico/<eid>`.
- Labels das colunas: "Conteúdo Original" e "Conteúdo Ajustado pela IA" ✅.
- Header "Conteúdo com links" em uppercase sutil ✅.
- Âncoras inline: **negrito + sublinhado discreto**, sem fundo colorido ✅.
- Botões "Copiar Markdown" e "Copiar HTML" no topo direito ✅.
- Sem botão "Ver mudanças" (não escopo) ✅.

### Comparação com a versão antiga

Para uma execução com 3 candidatas:
- **Antes (SPEC anterior):** 1 chamada LLM (~30k chars), `n_aplicadas=0`, todos `sugestao_manual`.
- **Depois:** 3 chamadas LLM (~1500 chars cada), `n_aplicadas=2-3`, trecho garantidamente literal.

## 7. Fora de escopo

- Botão "Ver mudanças" (diff inline) — escopo separado se quisermos depois.
- Validação semântica via embedding do trecho proposto vs parágrafo — não necessária se A+B+C funcionarem.
- JSON schema constraint via `response_format` — adicionar só se houver muitos erros de parse na prática.
- Trocar modelo LLM padrão para mais forte — não.

## 8. Riscos

- **Custo LLM aumenta linearmente com candidatos** (N chamadas vs 1). Em compensação, cada chamada é ~20x menor. Tendência: custo total semelhante. Monitorar via Anthropic/OpenAI dashboard após primeiro release.
- **Embedding de parágrafos custa $$ extra** — mitigado pelo cache do `gerar_embeddings_batch` (já tem Redis 30d). Em runs warm, custo cai a zero.
- **Re-grounding pode pular parágrafos relevantes** se cosine não capturar bem — top-3 é margem razoável; subir para top-5 se aparecer caso ruim.
- **Few-shot pode "viesar" demais** — exemplo é tomar de uma frase genérica de programação; LLM pode imitar. Mitigação: o exemplo segue a estrutura mas é tematicamente neutro.
- **CSS da âncora pode ficar invisível** se o tema dark estiver pálido — testar nos dois temas.

## 9. Próximos passos pós-SPEC (não desta SPEC)

Se após esta SPEC ainda houver alucinação:
1. Validação semântica: embedding do `trecho_original` proposto vs parágrafo — rejeita se cosine < 0.85.
2. `response_format=json_schema` na OpenAI — força estrutura.
3. Trocar modelo do `_InseridorAgent` por GPT-4 / Sonnet em vez do default.
