# SPEC — Robustez e limpeza do CWV

**Status:** ✅ aplicado (commit e50a3e6)
**Escopo:** backend (`agents/cwv/*` + `routers/ferramentas_cwv.py`)
**Crédito:** não muda
**Esforço:** ~3h
**Depende de:** nada. As 5 partes são independentes (podem virar PRs separados).

## 1. Resumo

Cinco itens de robustez/consistência de menor severidade.

## 2. Estado atual, problemas e mudanças

### 2.1 `compile()` sem checkpointer + `thread_id` morto (#6)

`construir_workflow` (`workflow.py:310`) faz `g.compile()` sem checkpointer, mas `_run_workflow_cwv` passa `config={"configurable": {"thread_id": f"cwv_{execucao_id}"}}` (`:382`). Sem checkpointer, a doc do LangGraph confirma que não há persistência/tolerância a falha — o `thread_id` é inerte e enganoso.

**✅ Decidido (produto):** opção mínima — **remover** o `config`/`thread_id` morto (deixar `ainvoke(estado_inicial)` puro). Não adicionar checkpointer agora. Implementar como abaixo, sem reabrir.

```python
# opção mínima:
estado_final = await workflow.ainvoke(estado_inicial)   # sem config
```

### 2.2 Agentes recriam `ChatOpenAI` sem cache (#7)

`CWVAnalisadorAgent` (`analisador.py:23-32`) e `CWVPesquisadorAgent` (`pesquisador.py:52-59`) chamam `super().__init__` (cria o modelo base) e depois **sobrescrevem** `self.llm` com um `ChatOpenAI` novo (sem `lru_cache`). O `BaseAgent` já aceita `model`/`temperature` (adicionado no fix do revisor) e cacheia via `_get_chat_model`.

**Mudança (analisador):**
```python
class CWVAnalisadorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        from app.config import settings
        model = settings.cwv_analisador_llm_model if settings.llm_provider == "openai" else None
        super().__init__(usuario_id, model=model, temperature=settings.cwv_analisador_llm_temperature)
```

**Pesquisador** usa tools (`bind_tools`). Hoje faz `super().__init__(usuario_id, tools=tools)` e depois recria. Refatorar para passar `model`/`temperature` ao `super().__init__` e deixar o `BaseAgent` fazer o `bind_tools` (ele já faz quando recebe `tools`):
```python
super().__init__(usuario_id, tools=tools, model=model, temperature=settings.cwv_pesquisador_llm_temperature)
```
(remover o bloco que recria `ChatOpenAI` + `bind_tools`).

> Determinismo já está ok (analisador 0.1, pesquisador 0.4) — esta mudança é só reuso/cache e consistência.

### 2.3 `except CancelledError` usa `execucao` possivelmente indefinida (#8)

`executar_workflow_cwv` (`:389-392`): o handler usa a variável `execucao` da `try`. Se o cancelamento ocorrer antes de `execucao` ser atribuída (`:325`), dá `UnboundLocalError` → mascara o cancelamento e não libera a reserva.

**Mudança:** re-buscar a execução dentro do handler (como em gerar_artigo):
```python
except asyncio.CancelledError:
    async with async_session_factory() as session:
        execucao = await ferramenta_service.buscar_execucao(session, execucao_id)
        if execucao and execucao.status in ("executando", "enfileirado", "pendente"):
            reserva = ferramenta_service._obter_reserva_estimada("core_web_vitals", execucao)
            if reserva > 0:
                await credito_service.liberar_reserva(session, str(execucao.usuario_id), reserva)
            await ferramenta_service.atualizar_execucao(session, execucao_id, status="cancelada", creditos_cobrados=0)
            ...
        await session.commit()
    raise
```

> Combinar com SPEC-A (reserva real). Inicializar `execucao = None` antes do `try` também resolve o NameError, mas re-buscar é mais robusto (objeto da sessão fechada).

### 2.4 `override_plataforma` não regenera docs pesquisados (#9)

`ferramentas_cwv.py:399-406`: só regenera problemas com `kb_codigo` (entrada_kb existe). Problemas documentados via pesquisador (sem KB) mantêm a doc da plataforma antiga após o override.

**✅ Decidido (produto):** opção mínima — **não** regenerar docs vindos de pesquisa (só os de KB). Não re-disparar o pesquisador aqui. Retornar `n_sem_kb` para a UI sinalizar quantos não foram regenerados. Implementar como abaixo, sem reabrir.
```python
for p in problemas:
    entrada_kb = buscar_entrada(p.kb_codigo) if p.kb_codigo else None
    if entrada_kb is None:
        continue  # doc veio de pesquisa; documentar limitação na UI (sem regenerar aqui)
    p.documentacao_md = agente._gerar_doc(entrada_kb, nova_plataforma, p.contexto_especifico or {})
    atualizados += 1
```
(documentar no retorno quantos ficaram sem regenerar: `n_sem_kb`).

### 2.5 Export .docx síncrono bloqueia o event loop (#10)

`exportar_problema_docx`/`exportar_relatorio_docx` (`:465, :502`) chamam `html_para_docx_bytes` (python-docx, CPU-bound) direto no handler async.

**Mudança:** despachar para thread:
```python
import asyncio
docx = await asyncio.to_thread(html_para_docx_bytes, relatorio_para_html(analise_dict, prob_dicts))
```
(idem no de problema). Rate limit (30/300s) já limita o impacto, mas `to_thread` evita travar a loop durante a geração.

## 3. Verificação

- **#6**: workflow compila/roda sem `config` (ou com checkpointer, se escolhida a opção maior); e2e segue verde.
- **#7**: unit — analisador/pesquisador pedem a temperatura/modelo esperados via `_get_chat_model` mockado; pesquisador ainda tem tools bound.
- **#8**: simular `CancelledError` antes da atribuição de `execucao` → sem `UnboundLocalError`; reserva liberada.
- **#9**: override em análise com problema sem `kb_codigo` → não quebra; retorna `n_sem_kb`.
- **#10**: export .docx retorna bytes válidos; chamada usa `to_thread` (não bloqueia — teste de fumaça).

## 4. Riscos

- **#6 opção checkpointer**: muda topologia/persistência — coordenar deploy (sem execuções CWV em andamento). A opção mínima (remover config) não tem esse risco.
- **#7**: `lru_cache(maxsize=16)` já ampliado (fix inlinks) — cobre os modelos CWV.
- **#9 re-pesquisa**: se optarem por re-disparar o pesquisador no override, vira chamada LLM síncrona no request → preferir job assíncrono (fora do escopo mínimo).

## 5. Fora de escopo

- Adicionar checkpointer ao CWV (decisão à parte, item #6 opção maior).
- Re-pesquisa automática no override (item #9 versão completa).

## 6. Arquivos alterados

- `backend/app/agents/cwv/workflow.py` — `ainvoke` sem config (ou checkpointer); handler `CancelledError`.
- `backend/app/agents/cwv/analisador.py`, `pesquisador.py` — `BaseAgent` com `model`/`temperature`.
- `backend/app/routers/ferramentas_cwv.py` — override (problemas sem KB), export `.docx` via `to_thread`.
- `backend/tests/unit/` — conforme §3.
