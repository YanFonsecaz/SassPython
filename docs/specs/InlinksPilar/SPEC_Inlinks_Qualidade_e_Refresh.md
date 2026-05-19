# SPEC — Inlinks: qualidade de saída + fix do refresh do detalhe

**Status:** pendente · **Escopo:** backend + frontend · **Migration?** não · **Crédito:** não muda

## 1. Resumo

Cinco entregas independentes:

- **A.** Prompt do ancorador valoriza o destino (não só o pilar).
- **B.** Sugestão manual quando candidato é descartado por estar só em cabeçalho.
- **C.** Piso de `score_semantico` no filtro do reranker.
- **D.** Categorias honestas na UI dos inlinks.
- **E.** Refetch do `detalhe` em status final.

Total: 4 arquivos backend (1 prompt, 1 lógica, 1 dataclass, 1 workflow), 2 arquivos frontend, 0 migrations.

Origem: análise crítica da execução `33140f1e-ea7e-48a4-864c-805f417c3e43` validada via Playwright E2E. Bug E foi flagrado durante o próprio teste.

## 2. Entrega A — Prompt do ancorador valoriza o destino

### Sintoma observado

A execução produziu âncoras como "começar a aprender programação" → URL "qual a melhor linguagem para iniciantes". A âncora descreve o pilar mas não evoca o destino. Resultado: leitor clica esperando algo sobre "começar" e cai num artigo sobre "escolher linguagem". Baixo CTR e sinal fraco pro Google.

### Causa raiz

`backend/app/agents/inlinks/ancorador.py` linhas 28-49: o prompt enfatiza "trechos literais do pilar" e cita relação semântica com o destino apenas como uma de muitas regras, sem peso. O LLM converge para frases temáticas do pilar.

### Mudança

Reescrever o bloco de prompt (linhas 28-49) com nova estrutura: **destino como ponto de partida**, pilar como restrição.

```python
prompt = f"""Você é um especialista em SEO e linkagem interna.

Para cada URL candidata abaixo, escolha 5-7 frases do artigo pilar que sirvam de **âncora teaser** para o destino — ou seja, frases que, lidas isoladamente, façam o leitor querer clicar para saber mais sobre o **destino**.

ARTIGO PILAR:
{trecho_pilar}

CANDIDATAS:
{lista}

Responda APENAS com JSON:
{{"ancoras": [{{"indice": 1, "opcoes": ["trecho exato do pilar 1", "trecho exato do pilar 2"]}}, ...]}}

REGRAS DE QUALIDADE (em ordem de prioridade):
1. **Foco no destino:** a âncora deve evocar o tema do destino (use o título e o resumo da URL candidata como guia). Pergunte-se: "Se eu lesse só esta âncora, eu esperaria chegar nessa URL?"
2. **Literal do pilar:** as âncoras DEVEM ser trechos copiados EXATAMENTE do artigo pilar — preservando acentuação, capitalização e pontuação interna. Não invente, não parafraseie.
3. **Especificidade > generalidade:** prefira frases com substantivos concretos do tema do destino ("portfólio de projetos", "linguagem para iniciantes") em vez de termos abertos do pilar ("começar a aprender", "expandir conhecimento").
4. **Tamanho:** cada âncora deve ter 2-5 palavras.
5. **Cobertura do artigo:** procure âncoras ao longo de TODO o pilar (introdução, meio, conclusão), não apenas no início.
6. **Variedade:** dê 5-7 opções por candidato — combinações diferentes de termos para o injector escolher a melhor disponível.
7. **Não-cabeçalhos:** NÃO escolha trechos dentro de cabeçalhos (linhas iniciadas por `#`, `##`, etc.). Esses trechos serão descartados pelo injector.
8. **Sem genéricos:** evite "clique aqui", "saiba mais", "veja também".
9. **Vazio é aceitável:** se nenhuma frase do pilar evocar o destino com qualidade, retorne `"opcoes": []` para esse candidato — melhor descartar do que linkar mal."""
```

### Verificação

Rodar a mesma execução E2E (URLs do hashtagtreinamentos.com). Comparar âncoras antes/depois. Espera-se ver:

- Para `/curriculo-programacao`: âncora "portfólio" / "currículo" em vez de "começar a aprender".
- Para `/roadmap-programacao`: âncora "roadmap" / "planejamento de carreira" em vez de "foco no mercado".
- Para `/melhor-linguagem-de-programacao-iniciantes`: âncora "primeira linguagem" / "linguagem de programação" em vez de "começar a aprender".

## 3. Entrega B — Sugestão manual quando único match em cabeçalho

### Sintoma observado

Na execução, `/curriculo-programacao` desapareceu silenciosamente. A âncora "construir um portfólio" (a melhor opção semanticamente) só aparecia num H2; com a regra de skip de cabeçalho da iteração anterior, o injector descartou o candidato sem feedback.

### Solução

Em `backend/app/agents/inlinks/injector.py`, quando todas as opções de âncora de um candidato caem em cabeçalhos OU não têm match no pilar, em vez de `continue` silencioso, registrar como **sugestão manual** com explicação.

#### Mudanças em `injector.py`

1. Adicionar `motivo_sugestao` à dataclass `InlinkInjetado`:

```python
@dataclass
class InlinkInjetado:
    url_destino: str
    anchor_text: str
    paragrafo_idx: int
    offset_chars: int
    score_total: float
    score_semantico: float
    score_contexto: float
    status: str = "aplicado"
    motivo_rejeicao: str | None = None
    trecho_contexto: str | None = None
    titulo_destino: str | None = None
    motivo_contexto: str | None = None
    categoria_match: str | None = None
    motivo_sugestao: str | None = None  # NOVO — quando status="sugestao_manual"
```

2. Modificar o loop principal de `injetar_inlinks` para rastrear quando todas as opções foram bloqueadas por cabeçalho versus zero matches no texto.

```python
substituicoes_sugestao: list[dict] = []

for c in candidatos_ordenados:
    ancoras = c.get("ancoras_opcoes", [c.get("titulo", "")])
    url = c["url"]
    if not ancoras or not url:
        continue

    match_info = None
    teve_match_em_heading = False

    for anchor in ancoras:
        if not anchor:
            continue
        # _search_tolerant aceita start_from para próximas ocorrências
        start_from = 0
        while True:
            hit = _search_tolerant(pilar_markdown, anchor, start_from=start_from)
            if not hit:
                break
            start, end, matched_text = hit
            if _esta_em_cabecalho(pilar_markdown, start):
                teve_match_em_heading = True
                start_from = end  # tentar próxima ocorrência
                continue
            match_info = { ... mesmo bloco existente ... }
            break
        if match_info:
            break

    if not match_info:
        # Distinguir: tinha match em heading? então é sugestão manual.
        if teve_match_em_heading:
            substituicoes_sugestao.append({
                "url": url,
                "titulo_destino": c.get("titulo", ""),
                "ancoras_opcoes": [a for a in ancoras if a],
                "score_total": c.get("score_total", 0),
                "score_semantico": c.get("score_semantico", 0),
                "score_contexto": c.get("score_contexto", 0),
                "motivo_contexto": c.get("motivo_contexto", ""),
                "motivo_sugestao": "As âncoras propostas só aparecem em cabeçalhos. Reescreva um parágrafo do pilar para incluir o termo e linkar manualmente.",
            })
        continue
    # ... resto do fluxo igual (overlap, distância, substituicoes.append)
```

3. No final, somar as `substituicoes_sugestao` à lista de injetados:

```python
for s in substituicoes_sugestao:
    injetados.append(
        InlinkInjetado(
            url_destino=s["url"],
            anchor_text=s["ancoras_opcoes"][0] if s["ancoras_opcoes"] else "",
            paragrafo_idx=0,
            offset_chars=0,
            score_total=s["score_total"],
            score_semantico=s["score_semantico"],
            score_contexto=s["score_contexto"],
            status="sugestao_manual",
            titulo_destino=s.get("titulo_destino") or None,
            motivo_contexto=s.get("motivo_contexto") or None,
            motivo_sugestao=s.get("motivo_sugestao"),
            categoria_match=_categoria_match(
                s["score_semantico"], s["score_contexto"], s["score_total"]
            ),
        )
    )
```

#### Mudanças em `workflow_inlinks.py`

No `node_injetar` (linhas ~330-348), o dict gerado por inlink precisa incluir `motivo_sugestao`:

```python
inlinks_dicts = [
    {
        "url_destino": ij.url_destino,
        "anchor_text": ij.anchor_text,
        "paragrafo_idx": ij.paragrafo_idx,
        "offset_chars": ij.offset_chars,
        "score_total": ij.score_total,
        "score_semantico": ij.score_semantico,
        "score_contexto": ij.score_contexto,
        "status": ij.status,
        "trecho_contexto": ij.trecho_contexto,
        "titulo_destino": ij.titulo_destino,
        "motivo_contexto": ij.motivo_contexto,
        "categoria_match": ij.categoria_match,
        "motivo_sugestao": ij.motivo_sugestao,  # NOVO
    }
    for ij in injetados
]
```

Em `node_persistir`, ao montar `InlinkSugerido(...)`:

> **Não criar nova migration.**
>
> Para persistir `motivo_sugestao` em DB sem coluna nova: reusar `motivo_rejeicao` quando `status="sugestao_manual"`.
>
> ```python
> motivo_final = il.get("motivo_rejeicao") or (
>     il.get("motivo_sugestao") if il.get("status") == "sugestao_manual" else None
> )
> inlink = InlinkSugerido(
>     ...,
>     motivo_rejeicao=motivo_final,  # usado como motivo_sugestao quando status=sugestao_manual
>     ...
> )
> ```

A coluna `status` é `String(20)` — `"sugestao_manual"` (16 chars) cabe.

#### Mudanças no frontend

Em `frontend/src/types/ferramenta.ts`, adicionar ao `InlinkAplicado`:

```ts
motivo_sugestao?: string | null;
```

Em `frontend/src/components/ferramentas/inlinks-resultado.tsx`, adicionar ramo de renderização para `status === "sugestao_manual"`:

- Cor: amarelo/laranja (entre o verde "aplicado" e o vermelho "rejeitado").
- Badge: "Sugestão para revisão manual" (estilo `bg-warning/15`).
- Sem o bloco "Onde foi inserido" (não tem onde — é sugestão).
- Mostrar `motivo_rejeicao` (que carrega o motivo_sugestao via Opção 1) como explicação.
- Mostrar opções de âncora propostas (lista enxuta).

### Verificação

Submeter execução com URL pilar que tenha um cabeçalho com a âncora candidata única. Verificar:

- DB: linha em `inlinks_sugeridos` com `status='sugestao_manual'` e `motivo_rejeicao` preenchido.
- API: `resultado_json.inlinks` inclui o item com esse status.
- UI: badge laranja, sem "Onde foi inserido", com explicação clara.

## 4. Entrega C — Piso de score_semantico no reranker

### Sintoma observado

Execução real: âncora "foco no mercado" → URL `/roadmap-programacao` foi aplicada. Score_total = 0.71, com score_contexto = 0.85 (LLM aprovou) e score_semantico = 0.75. Mas a âncora não tem relação semântica forte com o destino.

A combinação `0.6 * sem + 0.3 * ctx` permite que score_contexto alto compense score_semantico medíocre.

### Mudança

Em `backend/app/agents/workflow_inlinks.py`, função `node_match_rerank` (~linha 283), endurecer o filtro:

```python
_MIN_SEMANTIC_SCORE = 0.55  # piso absoluto de similaridade de embedding

# ... dentro de node_match_rerank:
filtered = [
    c for c in reranked
    if c.get("score_total", 0) >= threshold
    and c.get("score_semantico", 0) >= _MIN_SEMANTIC_SCORE
]
```

Adicionar a constante no topo do arquivo (junto a outras constantes/configs).

### Por que 0.55?

Empiricamente: embeddings cosine entre textos do mesmo tema costumam ficar acima de 0.6; entre temas vagamente relacionados, 0.4-0.55. Cortar em 0.55 elimina os "vagamente relacionados" que o LLM aprovava por contexto.

### Verificação

Comparar a execução de teste antes e depois. URLs com score_semantico < 0.55 devem ser descartadas no `match_rerank`. Logar via `publish_event` quantas caíram pelo piso (mensagem tipo `f"{n_descartadas_piso} candidatas abaixo do piso semântico de {_MIN_SEMANTIC_SCORE}"`).

## 5. Entrega D — Categorias honestas na UI

### Sintoma

Hoje `frontend/src/components/ferramentas/inlinks-resultado.tsx` (linhas 12-32) mapeia `categoria_match` para labels otimistas. "Complemento contextual" soa positivo, mas significa "score_contexto inflado, score_semantico fraco — revise antes de aprovar".

### Mudança

Reescrever os labels e descrições em `CATEGORIA_INFO` para serem honestos:

```ts
const CATEGORIA_INFO: Record<
  string,
  { label: string; descricao: string; classe: string }
> = {
  alta_similaridade: {
    label: "Conexão forte",
    descricao: "Tema do destino bate fortemente com o trecho do pilar — link confiável",
    classe: "bg-success/10 text-success border-success/30",
  },
  boa_similaridade: {
    label: "Conexão sólida",
    descricao: "Conexão temática consistente entre trecho e destino",
    classe: "bg-brand/15 text-brand-dark border-brand/30",
  },
  complemento_contextual: {
    label: "Conexão indireta · revise",
    descricao: "Destino se conecta por contexto, não por tema direto. Confirme se o leitor vai querer clicar.",
    classe: "bg-warning/15 text-warning border-warning/40",
  },
  similaridade_media: {
    label: "Conexão fraca · revise",
    descricao: "Relação tênue entre trecho e destino. Considere remover ou trocar a âncora.",
    classe: "bg-muted text-muted-foreground border-border",
  },
};
```

Mudanças-chave:
- "Complemento contextual" → **"Conexão indireta · revise"** (sinaliza ação).
- "Similaridade média" → **"Conexão fraca · revise"** (não vende otimismo).
- "Boa similaridade" → "Conexão sólida".
- "Alta similaridade" → "Conexão forte".

A descrição agora orienta a decisão do usuário, não só descreve.

### Verificação

Rodar uma execução e abrir `/ferramentas/historico/<id>`. Inlinks com `categoria_match="complemento_contextual"` devem mostrar "Conexão indireta · revise". Tooltip (hover no badge — atributo `title`) traz a descrição completa.

## 6. Entrega E — Bug: refresh do detalhe quando status muda

### Sintoma

Em `frontend/src/components/ferramentas/execucao-detalhe-conteudo.tsx` (linhas 119-129), o useEffect que carrega `detalhe` depende só de `[id]`. Cenário real:

1. Usuário submete formulário → redirect pra `/ferramentas/historico/<id>` durante "executando".
2. Componente monta, `loadDetalhe()` busca a execução com `resultado_json` vazio.
3. `setDetalhe(dados)` salva o estado vazio.
4. SSE atualiza `execucao.status` pra "concluida", mas `detalhe` continua vazio.
5. Usuário vê:
   - Coluna "Original" do comparador vazia (`pilar_original` ausente).
   - Painel "Inlinks aplicados" não renderiza (`resultado.inlinks` ausente).
6. F5 conserta tudo — porque agora carrega já como "concluida".

### Causa raiz

```tsx
useEffect(() => {
  async function loadDetalhe() {
    try {
      const dados = await api.get<ExecucaoDetalhe>(`/ferramentas/historico/${id}`);
      setDetalhe(dados);
    } catch { /* silent */ }
  }
  loadDetalhe();
}, [id]);
```

Deps `[id]` — só dispara no mount.

### Correção

Adicionar `execucao?.status` às deps. Cada transição de status refeita `detalhe`:

```tsx
useEffect(() => {
  async function loadDetalhe() {
    try {
      const dados = await api.get<ExecucaoDetalhe>(`/ferramentas/historico/${id}`);
      setDetalhe(dados);
    } catch { /* silent */ }
  }
  loadDetalhe();
}, [id, execucao?.status]);
```

Custo: 1 request HTTP a cada transição de status (4-6 transições durante a execução de inlinks). Aceitável — o endpoint é leitura simples.

### Verificação

1. Submeter execução nova via `/ferramentas/inlinks`.
2. Ficar parado na tela de detalhe (sem F5) durante "executando".
3. Esperar status flipar pra "concluida".
4. Confirmar:
   - Coluna "Original" do comparador agora renderiza com conteúdo.
   - Painel "Inlinks aplicados" aparece.
5. Sem F5 → tudo funciona.

## 7. Verificação ponta a ponta (todas as entregas)

1. Backend: rebuild não necessário (Python). Reiniciar `uvicorn` + `arq` worker.
2. Frontend: `cd frontend && npm run build && cp -r out/* ../backend/static/` para servir build atualizado.
3. Submeter execução nova com as URLs do hashtagtreinamentos.com (mesmas do teste anterior).
4. Sem F5, observar:
   - **(E)** Comparador renderiza original e modificado completos quando o status flipa.
   - **(A)** Âncoras escolhidas têm relação clara com os destinos (ver títulos das URLs no badge).
   - **(B)** Se houver candidato cuja única âncora estava em heading, aparece com badge laranja "Sugestão para revisão manual".
   - **(C)** No log do worker (`tail /tmp/arq.log`), `match_rerank` pode descartar mais candidatos.
   - **(D)** Categorias relabel — qualquer "Conexão indireta · revise" ou "Conexão fraca · revise" presente.
5. Comparar com a execução anterior (`33140f1e-…`) lado a lado. Esperar ver melhoria qualitativa visível.

## 8. Fora de escopo

- Mostrar score numérico mais proeminente na UI (cosmético).
- Mutação de texto pra inserir inlinks (continua aguardando dados).
- Configurar `_MIN_SEMANTIC_SCORE` como parâmetro no formulário (constante por enquanto).
- Re-executar sugestões manuais automaticamente — o usuário decide o que fazer.

## 9. Riscos

- **(A) Prompt do ancorador:** o LLM pode interpretar "destino" frouxamente e parafrasear. A regra #2 ("literal do pilar") continua dura. Se quebrar a literal-match, o injector vai descartar a âncora — falha-segura.
- **(B) Status "sugestao_manual":** qualquer código que filtra por `status === "aplicado"` precisa estar consistente. Verificar:
  - `inlinks-resultado.tsx`: já filtra com `i.status === "aplicado"` para a contagem (`qtdInlinksAplicados`). OK.
  - Backend `_finalizar_sucesso_inlinks`: o crédito é cobrado por `n_candidatas_validas`, não por aplicados — não muda.
- **(C) Piso de 0.55:** pode reduzir bastante o número de inlinks em pilares pequenos/genéricos. Aceitável (qualidade > volume).
- **(D) Relabel:** pura UI, baixo risco.
- **(E) Refresh:** request extra por mudança de status. Negligível.
