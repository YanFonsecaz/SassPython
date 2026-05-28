# SPEC — CWV Bugs Postmortem (E2E 2026-05-26)

**Status:** documentação · fixes já aplicados no código · não exige nova execução
**Escopo:** registrar os 9 bugs encontrados durante o e2e da ferramenta, causa raiz, fix e como prevenir recorrência
**Audiência:** code review, postmortem, lições aprendidas para próximas ferramentas

## 1. Contexto

Após implementação completa das 3 specs originais ([[SPEC_Ferramenta_Core_Web_Vitals]], [[SPEC_CWV_Base_Conhecimento]], [[SPEC_CWV_Dashboard_Historico]]), o teste e2e em 26/05/2026 expôs 9 bugs reais que **não foram detectados** durante o desenvolvimento porque:

- **Zero testes automatizados** para o código novo
- Componentes nunca foram exercitados ponta-a-ponta antes do e2e
- Specs foram aplicadas mecanicamente sem rodar a ferramenta com dados reais

Este documento existe para que o time tenha referência das pegadinhas e para guiar a [[SPEC_CWV_Testes_Automatizados]].

## 2. Lista dos bugs

| # | Severidade | Camada | Sintoma observado | Onde |
|---|---|---|---|---|
| 1 | Alta | Backend / persistência | Histórico mostra `0 problemas` mesmo com URLs que têm 7+ | `cwv_persistencia.py:_analise_resumo` |
| 2 | Média | Backend / router | `/historico-url` retorna `plataforma_detectada=""` sempre | `ferramentas_cwv.py:historico_url_cwv` |
| 3 | Alta | Backend / router | `POST /analisar` retorna HTTP 500 — "Object of type HttpUrl is not JSON serializable" | `ferramentas_cwv.py:analisar_cwv` |
| 4 | Crítica | Backend / config | `psi_api_key` nunca é lida — env var existe mas tem nome diferente | `config.py:Settings` |
| 5 | Alta | Backend / resiliência | Sem fallback quando key principal estoura quota diária (HTTP 429) | `cwv_psi_client.py:fetch_psi` |
| 6 | Crítica | Backend / workflow | `analise_ids=[]` e `n_sucesso=0` no resultado_json mesmo com 7 problemas persistidos | `workflow.py:_run_workflow_cwv` (linha do `astream`) |
| 7 | Crítica | Backend / workflow | Execução fica em `status='executando'` para sempre — não atualiza para `concluida` | `workflow.py:_run_workflow_cwv` (`flush` em vez de `commit`) |
| 8 | Alta | Backend / SPA fallback | Rotas dinâmicas `/url/<id>`, `/historico/<id>`, `/execucao/<id>` retornam HTML errado | `main.py:_DYNAMIC_SEGMENTS` |
| 9 | Alta | Frontend / Next.js | `useParams()` retorna `"placeholder"` em vez do ID real → API chama `/analise/placeholder` → 500 | `cwv-url-client.tsx`, `cwv-historico-client.tsx`, `cwv-execucao-client.tsx` |

## 3. Detalhamento

### 3.1 Bug #1 — Contagem de problemas hardcoded como 0

**Sintoma:** API `/historico` retorna `n_problemas: 0` e `n_problemas_alta_severidade: 0` para toda análise, mesmo quando `cwv_problema` tem 7 linhas para essa `analise_id`.

**Causa raiz:** `_analise_resumo` em `cwv_persistencia.py` retornava esses campos hardcoded:

```python
"n_problemas": 0,
"n_problemas_alta_severidade": 0,
```

Provavelmente colocados como "TODO" e esquecidos.

**Fix aplicado:** `buscar_historico_url` agora faz LEFT JOIN com subquery agregando contagens:

```python
contagens = (
    select(
        CwvProblema.analise_id.label("analise_id"),
        func.count(CwvProblema.id).label("n_total"),
        func.coalesce(
            func.sum(case((CwvProblema.severidade >= 4, 1), else_=0)),
            0,
        ).label("n_alta"),
    )
    .group_by(CwvProblema.analise_id)
    .subquery()
)
```

E `_analise_resumo` aceita `n_problemas` e `n_alta` como kwargs.

**Prevenção:** teste de integração que insere N problemas + 1 análise + chama `buscar_historico_url` e verifica que `n_problemas == N` e `n_problemas_alta_severidade == filter(severidade>=4)`.

### 3.2 Bug #2 — `plataforma_detectada` vazia no /historico-url

**Sintoma:** Endpoint `/historico-url?cliente_id=X&url=Y` retornava `"plataforma_detectada": ""` independente do que está no banco.

**Causa raiz:** literal string vazia no router:

```python
return {
    "url_canonica": url,
    "template_tipo": analises[0]["template_tipo"] if analises else "",
    "plataforma_detectada": "",   # ← bug
    "analises": analises,
}
```

**Fix aplicado:** novo helper `buscar_ultima_analise_url` retorna o `CwvAnalise` mais recente; o router extrai `plataforma_detectada` e `template_tipo` desse objeto. Também adiciona `_validar_cliente` (segurança — endpoint não verificava ownership).

**Prevenção:** teste integração que cria 2 análises (mesma URL, plataformas diferentes em momentos diferentes) e valida que `/historico-url` retorna a plataforma da análise mais recente.

### 3.3 Bug #3 — HttpUrl não-serializável em JSONB

**Sintoma:** Submit do form retorna HTTP 500. Stack trace:

```
TypeError: Object of type HttpUrl is not JSON serializable
[SQL: INSERT INTO execucoes_ferramentas (... entrada_json ...) VALUES ($7::JSONB, ...)]
```

**Causa raiz:** `body.model_dump()` retorna `urls_por_template` com objetos `pydantic.HttpUrl` em vez de strings. Quando SQLAlchemy serializa para JSONB, `json.dumps` não sabe lidar com `HttpUrl`.

**Fix aplicado:** trocado para `body.model_dump(mode="json")` em duas chamadas (`analisar_cwv` e `reanalisar_cwv`).

**Prevenção:** teste de integração que faz POST `/analisar` com body válido e verifica HTTP 202. Esse teste sozinho teria pego o bug.

### 3.4 Bug #4 — Env var ignorada

**Sintoma:** Mesmo com `API_PSI_KEY=...` no `.env`, `settings.psi_api_key` retorna `""`. Resultado: PSI sempre roda em modo anônimo (cota IP-based mais baixa).

**Causa raiz:** `pydantic-settings` com `case_sensitive=False` mapeia env var `API_PSI_KEY` → field `api_psi_key` (não `psi_api_key`). Como a SPEC usava `psi_api_key`, a key nunca foi lida.

**Fix aplicado:** renomeado para `api_psi_key` + adicionado `api_psi_key2` (fallback).

**Prevenção:** validar na inicialização que se `api_psi_key` está vazia em `ambiente=producao`, emite warning. Ou criar fixture de teste que monkeypatcha `os.environ` e verifica que `settings.api_psi_key` reflete o valor.

### 3.5 Bug #5 — Sem fallback de PSI key

**Sintoma:** Key principal estourou cota diária (HTTP 429 — "Quota exceeded"). Workflow falhou em 100% das URLs do dia, mesmo havendo outra key disponível como secundária.

**Causa raiz:** `fetch_psi` usava só `settings.psi_api_key` e não tentava recuperação.

**Fix aplicado:** loop com `_psi_keys()` que retorna ambas keys configuradas; em HTTP 429 ou 403, tenta a próxima:

```python
async def fetch_psi(url: str, estrategia: str = "mobile") -> dict:
    keys = _psi_keys() or [None]
    for i, key in enumerate(keys):
        try:
            data = await _fetch_psi_once(url, estrategia, key)
            ...
            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 403) and i + 1 < len(keys):
                continue
            raise PSIError(...) from e
```

**Prevenção:** teste com `httpx_mock` simulando key1 → 429 e key2 → 200, verificando que `fetch_psi` retorna o payload de key2.

### 3.6 Bug #6 — astream(version="v2") não acumula estado

**Sintoma:** Workflow rodava com sucesso (persistia análises e problemas), MAS `resultado_json.analise_ids=[]` e `n_urls_analisadas=0`. Frontend então não conseguia navegar para o dashboard.

**Causa raiz:** `workflow.astream(estado_inicial, config=config, version="v2")` retorna **eventos** do LangGraph (`{"event": "on_chain_end", "name": "node_name", "data": {...}, "run_id": "..."}`), não atualizações de state. O código fazia `estado_final.update(event)`, que adicionava chaves `event/name/data/run_id` mas nunca os campos da `EstadoCWV` (`psi_resultados`, `analises_persistidas`, etc).

**Fix aplicado:** trocado para `workflow.ainvoke()` que retorna o state final completo:

```python
estado_final = await workflow.ainvoke(estado_inicial, config=config)
```

**Prevenção:** teste de integração end-to-end do workflow com PSI mockado: dado 1 URL ok + 1 falhou, verificar que `estado_final["analises_persistidas"]` tem 2 IDs e `estado_final["psi_resultados"]` tem 2 entries.

### 3.7 Bug #7 — flush sem commit

**Sintoma:** Mesmo após `_run_workflow_cwv` completar, `execucao.status` continuava `"executando"` no banco, `creditos_cobrados=0`, `resultado_json=null`. Frontend ficava em loop de polling perpétuo.

**Causa raiz:** o bloco `async with async_session_factory() as session:` chamava `await session.flush()` no final, mas não `commit()`. Ao sair do `async with` sem commit, SQLAlchemy faz ROLLBACK das mudanças. O DEBUG do crédito foi confirmado (commit interno em `confirmar_debito`), mas as alterações em `execucao` eram revertidas.

**Fix aplicado:** trocado para `await session.commit()` em ambas saídas (sucesso e saldo insuficiente).

**Prevenção:** ESLint-like rule para Python? Difícil. Melhor: teste e2e que valida `execucao.status == 'concluida'` após workflow run, lendo o registro em uma sessão nova.

### 3.8 Bug #8 — Rotas dinâmicas CWV não cobertas em main.py

**Sintoma:** Navegar diretamente para `/ferramentas/core-web-vitals/url/<uuid>` (sem ter clicado em link interno antes) caía no fallback genérico `index.html` (login). Click-through funcionava por sorte/cache.

**Causa raiz:** `main.py:_DYNAMIC_SEGMENTS` listava só `ferramentas/historico/<id>` e `clientes/<id>` — esquecendo as 3 novas rotas adicionadas pela ferramenta CWV.

**Fix aplicado:** adicionados 3 padrões:

```python
(re.compile(r"^ferramentas/core-web-vitals/execucao/[\w-]+$"), "ferramentas/core-web-vitals/execucao/placeholder.html"),
(re.compile(r"^ferramentas/core-web-vitals/historico/[\w-]+$"), "ferramentas/core-web-vitals/historico/placeholder.html"),
(re.compile(r"^ferramentas/core-web-vitals/url/[\w-]+$"), "ferramentas/core-web-vitals/url/placeholder.html"),
```

**Prevenção:** centralizar `_DYNAMIC_SEGMENTS` numa lista única e adicionar teste que, para cada rota dinâmica do frontend (descoberta via leitura de `frontend/src/app/**/[*]/page.tsx`), valida que o serve_spa retorna HTML válido com status 200.

### 3.9 Bug #9 — useParams retorna "placeholder" em static export

**Sintoma:** API era chamada com `analiseId=placeholder` em vez do UUID real, retornando HTTP 500 (UUID inválido). Página caía em `notFound()` → redirect.

**Causa raiz:** Next.js com `output: "export"` + `generateStaticParams` que retorna `[{ analiseId: "placeholder" }]` faz com que `useParams()` retorne `{ analiseId: "placeholder" }` no primeiro render (build-time). Apenas após hydration o valor mudaria — mas como a página chama API no `useEffect` inicial, ela usa o valor errado.

**Fix aplicado:** trocado para `usePathname()` + split, igual ao padrão estabelecido em `execucao-detalhe-conteudo.tsx`:

```tsx
const pathname = usePathname();
const analiseId = pathname.split("/").filter(Boolean).pop() || "";
```

Aplicado em 3 components: `cwv-url-client.tsx`, `cwv-historico-client.tsx`, `cwv-execucao-client.tsx`.

**Prevenção:** documentar no `frontend/AGENTS.md` ou no CLAUDE.md regional que **dynamic routes em static export devem usar `usePathname()`, nunca `useParams()`**. Considerar criar um helper `useDynamicParam(name: string)` que abstrai isso.

## 4. Análise de causa-raiz transversal

Todos os 9 bugs caem em uma das três categorias:

### 4.1 Specs aplicadas mecanicamente (bugs #1, #2)
SPEC declarava `n_problemas` no schema, mas o código de implementação retornou hardcoded `0`. SPEC dizia `plataforma_detectada` deve vir do banco, mas o código retornou `""`. Quem aplicou a SPEC traduziu campos sem verificar correção semântica.

**Lição:** Cada campo no schema de resposta merece um teste de integração com pelo menos 2 valores diferentes para verificar que está vindo do banco e não de um placeholder.

### 4.2 Conhecimento tácito de framework não documentado (bugs #4, #6, #9)
- Pydantic Settings env mapping (#4)
- LangGraph `astream` vs `ainvoke` (#6)
- Next.js `useParams` em static export (#9)

São pegadinhas que só se descobre na primeira vez. Não há culpa do implementador, é falta de tribal knowledge documentado.

**Lição:** Após cada e2e de uma nova ferramenta, atualizar um documento "Frontend tribal knowledge" e "Backend tribal knowledge" com pegadinhas descobertas. Os fixes #4, #6 e #9 deveriam virar entradas em `AGENTS.md` regional ou `CLAUDE.md`.

### 4.3 Branches nunca exercitadas (bugs #3, #5, #7, #8)
- Submit do form (#3)
- Quota exhausted (#5)
- Commit do workflow (#7)
- Navegação direta para URL dinâmica (#8)

Todos foram código que **funciona em isolamento** mas nunca foi exercido em um cenário real.

**Lição:** A definição de "pronto" da SPEC §9 (Critério de pronto) deveria incluir **e2e manual com checklist explícito**:
- [ ] Submit do form com 1 URL real
- [ ] Polling até concluída
- [ ] Click no "Ver dashboard" navega
- [ ] Refresh duro na URL do dashboard mantém o usuário lá

Adicionalmente, as Phase reviews da SPEC deveriam exigir que cada Phase termine com smoke test executado pelo implementador.

## 5. Critério de pronto

- [x] Os 9 bugs estão documentados aqui com sintoma, causa, fix e prevenção
- [x] Todos os fixes já estão aplicados no código (verificado via e2e em 2026-05-26)
- [ ] [[SPEC_CWV_Testes_Automatizados]] cobre cada bug com pelo menos 1 teste
- [ ] `frontend/AGENTS.md` ou equivalente menciona a pegadinha do `useParams` em static export
- [ ] `backend/CLAUDE.md` ou equivalente menciona `ainvoke` vs `astream` em LangGraph
- [ ] Próximas ferramentas: checklist de e2e manual obrigatório na Phase final
