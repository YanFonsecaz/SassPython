# SPEC — Distribuir Inlinks: Visibilidade, Proteção do Alvo e Cobrança Justa

**Status:** ✅ implementado · **Escopo:** `workflow_inlinks_reversos.py` + `ferramenta_service.py` · **Crédito:** ajusta política
**Depende de:** [[SPEC_Ferramenta_Distribuir_Inlinks]] aplicada
**Contexto:** E2E real com URL alvo `mundocristao.com.br/categoria-produto/livros/mulheres/` + 10 satélites blog post. Execução `eca473b6` completou em **230ms**, retornou `candidatas: []`, mas **cobrou 10 créditos**. Conteúdo do alvo no cache vinha de E2E anterior — Trafilatura extraiu apenas boilerplate de cookies de página de categoria WooCommerce, não texto redacional. Resultado: embedding ruim, cosine baixo com todas as candidatas, filtro `>= threshold` zerou tudo, candidatas reais sumiram do resultado.

## 1. Causas-raiz

### 1.1 Candidatas filtradas somem do resultado

`node_filtrar_similaridade` produz `candidatas_viaveis` somente com aquelas que passaram do threshold. As que não passaram nunca chegam a `candidatas_processadas` em `node_inserir_em_cada` e por isso não aparecem em `resultado_final.candidatas`.

Hoje o usuário vê `n_aplicadas=0, n_sugestoes=0, n_sem_match=0, n_falhas=0` com lista vazia — sem entender por quê. A mensagem genérica de `erro_msg` ("Nenhum inlink pôde ser aplicado…") não diz qual candidata foi avaliada nem qual cosine cada uma teve.

### 1.2 Alvo extraído inválido passa silenciosamente

Trafilatura é otimizado para artigos. Em páginas de categoria (WooCommerce, listagens, paginadas), retorna boilerplate (cookies, "Showing 1–9 of 18 results"). O conteúdo é grande o suficiente para passar do guard `len(conteudo.strip()) < 50` no scraper, mas semanticamente é inútil — gera embedding lixo que reprova qualquer candidata real no filtro do passo 5.

A ferramenta processou mesmo assim, gerou embedding do lixo, comparou com candidatas, todas falharam, cobrou 10 créditos.

### 1.3 Cobrança quando nada foi feito

`finalizar_sucesso_distribuir_inlinks` hoje tem 2 ramos:

- `n_processadas == 0` (todas falharam na extração) → 0 créditos.
- `n_aplicadas + n_sugestoes == 0` → cobra `n_processadas * CUSTO_POR_CANDIDATA`.

No caso da execução `eca473b6`: `n_processadas=10` (extraídas), mas `n_aplicadas+n_sugestoes+n_sem_match+n_falhas = 0` porque todas sumiram no filtro. Cobrou 10 créditos por valor zero.

## 2. Mudanças

### 2.1 Fix 1 — Visibilidade das candidatas filtradas

Em `node_filtrar_similaridade` (linhas ~394-440), produzir DUAS listas:

```python
viaveis = [c for c in best_by_url.values() if c["score_semantico"] >= threshold]
descartadas = [c for c in best_by_url.values() if c["score_semantico"] < threshold]

viaveis.sort(key=lambda x: x["score_semantico"], reverse=True)

await publish_event(
    eid, "node_complete", "filtrar_similaridade",
    f"{len(viaveis)} candidatas viaveis, {len(descartadas)} sem similaridade suficiente",
)
return _sanitize({
    "candidatas_viaveis": viaveis,
    "candidatas_descartadas": descartadas,
})
```

Adicionar `candidatas_descartadas: list[dict]` em `EstadoDistribuir`.

Em `node_inserir_em_cada` (linha ~443), incluir as descartadas como `sem_match` no início:

```python
async def node_inserir_em_cada(estado: EstadoDistribuir) -> dict:
    ...
    candidatas_viaveis = estado.get("candidatas_viaveis", [])
    candidatas_descartadas = estado.get("candidatas_descartadas", [])
    max_inlinks = ...

    threshold = estado.get("threshold_score", 0.6)

    resultados: list[dict] = []

    # Inicia com descartadas (sem_match com motivo claro)
    for c in candidatas_descartadas:
        resultados.append({
            "url": c["url"],
            "url_canonica": c.get("url_canonica", c["url"]),
            "titulo": c.get("titulo", ""),
            "status": "sem_match",
            "score_semantico": c.get("score_semantico"),
            "motivo": (
                f"Similaridade {c['score_semantico']:.2f} abaixo do threshold {threshold:.2f}. "
                f"O conteudo da candidata nao tem tema suficientemente proximo da URL alvo."
            ),
        })

    if not candidatas_viaveis:
        await publish_event(eid, "node_complete", "inserir_em_cada", "Nenhuma candidata viavel para inserir")
        return _sanitize({"candidatas_processadas": resultados})

    # ... resto do código de inserção paralela
```

Também adicionar as candidatas que **falharam na extração** (existem em `candidatas_resultados` mas não chegam ao filtro):

Em `node_filtrar_similaridade`, no início, incluir falhas:

```python
candidatas_resultados = estado.get("candidatas_resultados", [])
falhas_extracao: list[dict] = []
for c in candidatas_resultados:
    if c.get("falhou"):
        falhas_extracao.append({
            "url": c.get("url", ""),
            "url_canonica": c.get("url_canonica", c.get("url", "")),
            "titulo": c.get("titulo", ""),
            "status": "falhou_extracao",
            "motivo": c.get("erro") or "Falha ao extrair conteudo da URL",
        })
```

E adicionar `falhas_extracao` ao retorno do nó. Em `node_inserir_em_cada`, prefixar `resultados` com elas.

### 2.2 Fix 2 — Proteção contra alvo ruim

Adicionar guard em `node_extrair_alvo` (após o `await extrair_pilar`):

```python
_MIN_ALVO_CHARS = 500
_MIN_ALVO_PALAVRAS = 80

if not resultado.falhou:
    conteudo = resultado.conteudo_md or ""
    n_chars = len(conteudo.strip())
    n_palavras = len(conteudo.split())
    if n_chars < _MIN_ALVO_CHARS or n_palavras < _MIN_ALVO_PALAVRAS:
        resultado.falhou = True
        resultado.erro = (
            f"URL alvo extraida com conteudo insuficiente ({n_palavras} palavras, "
            f"{n_chars} caracteres). Isto costuma acontecer com paginas de categoria, "
            f"listagens ou paginas dinamicas. Use URL de artigo ou landing page com texto."
        )
```

E em `executar_workflow_distribuir_inlinks` (linha ~687), curto-circuito: se `estado_inicial[alvo].falhou` após `node_extrair_alvo`, abortar workflow imediatamente e marcar execução como `concluida` com `erro_msg` claro e `n_processadas=0` para que cobrança caia em 0.

Solução simples: usar conditional edge no LangGraph:

```python
def _rota_apos_extrair_alvo(estado: EstadoDistribuir) -> str:
    if estado.get("alvo_resultado", {}).get("falhou"):
        return "persistir_falha_alvo"
    return "extrair_candidatas"


async def node_persistir_falha_alvo(estado: EstadoDistribuir) -> dict:
    """Persiste resultado vazio com motivo quando alvo falha — sem cobrar."""
    eid = estado["execucao_id"]
    alvo = estado.get("alvo_resultado", {})
    resultado_final = {
        "url_alvo": alvo.get("url_canonica", alvo.get("url", "")),
        "titulo_alvo": alvo.get("titulo", ""),
        "n_candidatas_validas": 0,
        "n_aplicadas": 0,
        "n_sugestoes": 0,
        "n_sem_match": 0,
        "n_falhas": 0,
        "candidatas": [],
        "alvo_invalido": True,
        "motivo_alvo": alvo.get("erro", "URL alvo nao processavel"),
    }
    return _sanitize({"resultado_final": resultado_final})
```

E no grafo (`criar_workflow_distribuir`):

```python
workflow.add_node("persistir_falha_alvo", node_persistir_falha_alvo)
workflow.add_conditional_edges("extrair_alvo", _rota_apos_extrair_alvo, {
    "extrair_candidatas": "extrair_candidatas",
    "persistir_falha_alvo": "persistir_falha_alvo",
})
workflow.add_edge("persistir_falha_alvo", END)
```

### 2.3 Fix 3 — Cobrança justa

Em `finalizar_sucesso_distribuir_inlinks` (ferramenta_service.py, linhas 256-315), ajustar:

```python
async def finalizar_sucesso_distribuir_inlinks(db, execucao_id: str, resultado_json: dict) -> ExecucaoFerramenta:
    from app.services import credito_service

    execucao = await buscar_execucao(db, execucao_id)
    if not execucao:
        raise ValueError(f"Execucao {execucao_id} nao encontrada")

    # 1. Alvo inválido → cobrança zero, mensagem clara
    if resultado_json.get("alvo_invalido"):
        execucao.status = "concluida"
        execucao.creditos_cobrados = 0
        execucao.erro_msg = resultado_json.get("motivo_alvo") or (
            "URL alvo nao tem conteudo redacional suficiente. "
            "Use URL de artigo ou landing page, nao pagina de categoria/listagem."
        )
        execucao.resultado_json = resultado_json
        execucao.concluida_em = datetime.utcnow()
        await db.flush()
        logger.info("%s distribuir_inlinks status=concluida sem creditos (alvo invalido)", execucao_id[:8])
        return execucao

    n_processadas = resultado_json.get("n_candidatas_validas", 0)

    # 2. Nenhuma candidata extraida → zero
    if n_processadas == 0:
        execucao.status = "concluida"
        execucao.creditos_cobrados = 0
        execucao.erro_msg = (
            "Nenhuma candidata pode ser processada. "
            "Verifique se as URLs estao acessiveis."
        )
        execucao.resultado_json = resultado_json
        execucao.concluida_em = datetime.utcnow()
        await db.flush()
        logger.info("%s distribuir_inlinks status=concluida sem creditos (0 candidatas validas)", execucao_id[:8])
        return execucao

    n_aplicadas = resultado_json.get("n_aplicadas", 0)
    n_sugestoes = resultado_json.get("n_sugestoes", 0)
    n_sem_match = resultado_json.get("n_sem_match", 0)

    # 3. Nada com valor (nenhum link aplicado ou sugerido) → cobrança zero
    # Mesmo que tenham sido extraidas, se a ferramenta nao conseguiu apontar nada util,
    # nao cobramos. Pelo menos uma sem_match ja conta como entrega informativa? Nao —
    # sem_match é "rejeita por falta de fit", nao agrega valor. Mantemos a regra:
    # cobranca exige >= 1 candidata com inlink (aplicado ou sugerido).
    if n_aplicadas + n_sugestoes == 0:
        execucao.status = "concluida"
        execucao.creditos_cobrados = 0
        execucao.erro_msg = (
            f"Avaliamos {n_processadas} candidata(s), mas nenhuma tem similaridade "
            f"suficiente com a URL alvo para inserir um link. "
            f"Tente URLs candidatas mais relacionadas ao tema."
        )
        execucao.resultado_json = resultado_json
        execucao.concluida_em = datetime.utcnow()
        await db.flush()
        logger.info(
            "%s distribuir_inlinks status=concluida sem creditos (0 aplicadas+sugestoes de %d)",
            execucao_id[:8], n_processadas,
        )
        return execucao

    # 4. Cobrança normal
    custo = calcular_custo_distribuir_inlinks(n_processadas)

    saldo_ok = await credito_service.verificar_saldo_suficiente(db, str(execucao.usuario_id), custo)
    if not saldo_ok:
        execucao.status = "falhou"
        execucao.erro_msg = "Saldo insuficiente"
        execucao.concluida_em = datetime.utcnow()
        await db.flush()
        return execucao

    await credito_service.debitar_creditos(
        db,
        str(execucao.usuario_id),
        custo,
        descricao=f"Distribuir inlinks: {custo} creditos (candidatas={n_processadas})",
        ferramenta="distribuir_inlinks",
        execucao_id=execucao_id,
    )

    execucao.status = "concluida"
    execucao.creditos_cobrados = custo
    execucao.resultado_json = resultado_json
    execucao.concluida_em = datetime.utcnow()
    await db.flush()
    logger.info("%s distribuir_inlinks status=concluida creditos=%d", execucao_id[:8], custo)
    return execucao
```

**Mudança-chave:** quando `n_aplicadas + n_sugestoes == 0`, agora cobra **zero** em vez de cobrar `n_processadas × custo_por_candidata`. O modelo de negócio passa a ser: paga só quando recebeu valor (≥1 link sugerido ou aplicado).

## 3. Verificação

### 3.1 E2E #1 — alvo inválido (Mundo Cristão)

Mesmo input que falhou:

```json
{
  "url_alvo": "https://www.mundocristao.com.br/categoria-produto/livros/mulheres/",
  "candidatas_urls": [10 blog posts]
}
```

Esperado:
- Status `concluida` em < 30s (não processa candidatas se alvo falhou — só extrai alvo e curto-circuita).
- `creditos_cobrados = 0`.
- `resultado_json.alvo_invalido = true`.
- `erro_msg`: "URL alvo extraida com conteudo insuficiente (N palavras, M caracteres)…"
- `candidatas = []` no resultado, mas com `alvo_invalido=true` o frontend pode renderizar a tela de erro específica.

### 3.2 E2E #2 — alvo válido, candidatas sem fit

Usar pilar `o-que-montar-para-ganhar-dinheiro` como alvo (tem conteúdo) + 4 URLs já testadas (agência-viagens, restaurante, imobiliária, loja-virtual). Sabemos que 3 não têm fit com o pilar.

Esperado:
- `n_aplicadas + n_sugestoes`: 1-2 (restaurante deve aplicar com fix B+C herdado do Inseridor).
- `n_sem_match`: o que sobrar (com cosine real visível em cada candidata).
- Todas as 4 candidatas aparecem em `resultado.candidatas`.
- Se `n_aplicadas + n_sugestoes == 0`: cobrar zero (entrega informativa não cobra).
- Se ≥ 1 aplicada/sugerida: cobrar `15 + 4 × 1 = 19` normal.

### 3.3 E2E #3 — alvo válido, candidatas com fit

URLs Hashtag (4 candidatas) com alvo python-mais-facil. Sabido que aplica 2-3.

Esperado:
- `n_aplicadas + n_sugestoes` ≥ 2 (mantém comportamento atual).
- Todas as 4 em `resultado.candidatas` (mantém visibilidade).
- Cobrança 19 (15 + 4).

## 4. Riscos

| Risco | Mitigação |
|---|---|
| Guard de alvo (500 chars / 80 palavras) ser muito restritivo e bloquear landing pages válidas curtas | Thresholds escolhidos com base no E2E real falho (1206 chars de boilerplate, ~190 palavras). Landing page real costuma ter ≥ 200 palavras. Se aparecer falso positivo, ajustar para 300 chars / 50 palavras. |
| Visibilidade adiciona payload grande em `resultado_json` (10 candidatas + cosines + motivos) | Já carregamos `markdown_modificado` por aplicada — bem maior que metadata de sem_match. Aceitável. |
| Cobrança zero quando nada útil estraga modelo de negócio | É o efeito desejado: usuário só paga quando recebe ≥ 1 link. Já fizemos isso no Inlinks Automáticos com a regra "0 aplicadas = só URLs". Aqui radicalizamos para "0 aplicadas+sugestoes = 0 créditos". Margem ainda OK porque o caso comum é apresentar ≥ 1 link válido. |
| Curto-circuito pula `extrair_candidatas` quando alvo falha | Correto: se alvo é inválido, candidatas não importam. Não desperdiça extrações de URLs externas. |

## 5. Não-objetivos

- Mudar o scraper Trafilatura para extrair categoria WooCommerce (v2 — talvez `favor_recall=True` ou fallback BeautifulSoup).
- Adicionar tela de erro específica no frontend para `alvo_invalido` (v2 — hoje a `erro_msg` já é exibida).
- Permitir o usuário passar `markdown_alvo` direto (bypass do scraper) — v2.

## 6. Plano de execução

1. Editar `workflow_inlinks_reversos.py`:
   - Adicionar guard `_MIN_ALVO_CHARS / _MIN_ALVO_PALAVRAS` em `node_extrair_alvo`.
   - Reescrever `node_filtrar_similaridade` para produzir `candidatas_descartadas` e `falhas_extracao`.
   - Atualizar `node_inserir_em_cada` para prefixar `resultados` com descartadas e falhas.
   - Adicionar `node_persistir_falha_alvo` + conditional edge após `extrair_alvo`.
   - Atualizar `EstadoDistribuir` TypedDict com `candidatas_descartadas`.

2. Editar `ferramenta_service.py`:
   - Reescrever `finalizar_sucesso_distribuir_inlinks` com 4 ramos (alvo_invalido, sem candidatas, sem valor, normal).

3. Restart worker.

4. Rodar E2E #1, #2, #3.

5. Validar:
   - E2E #1: zero crédito, `alvo_invalido=true`, mensagem clara.
   - E2E #2: candidatas todas visíveis, cosines reais, cobrança alinhada com valor entregue.
   - E2E #3: comportamento anterior preservado.

## 7. Critério de pronto

- Cobrança zero quando `alvo_invalido` ou `n_aplicadas + n_sugestoes == 0`.
- Todas as candidatas (inclusive sem_match e falhou_extracao) aparecem em `resultado_json.candidatas`.
- E2E #1 (alvo categoria WooCommerce) concluído em < 30s com 0 créditos e mensagem específica.
- E2E #2 e #3 com comportamento esperado das execuções anteriores, sem regressão.
