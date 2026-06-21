# SPEC — Determinismo do revisor (temperatura por agente)

**Status:** pendente
**Escopo:** backend (`BaseAgent` + `RevisorAgent` + config)
**Crédito:** não muda
**Esforço:** ~2h
**Depende de:** nada (pode ir em paralelo)

## 1. Resumo

O `RevisorAgent` é o **juiz de qualidade** do pipeline: ele decide o gate `score >= 70` que aprova/reprova o artigo e dispara (ou não) novas rodadas de redação. Hoje ele roda com `temperature=0.7` (o `settings.llm_temperature` global, herdado de `BaseAgent`). Um avaliador com temperatura alta dá **notas diferentes para o mesmo artigo** a cada execução → o gate vira loteria e o loop de revisão fica instável (pode reprovar um texto bom ou aprovar um ruim, e o custo/UX variam sem motivo).

A arquitetura atual **não permite** temperatura por agente: `_get_chat_model` é cacheado por `(provider, model, temperature)`, mas `BaseAgent.__init__` sempre passa o `settings.llm_temperature` global. O próprio time já sabe que avaliadores devem ter temperatura baixa — o analisador de CWV usa `temperature=0.1` (`config.py:88`).

Esta SPEC torna temperatura (e, opcionalmente, modelo) configuráveis por agente e fixa o revisor em modo quase-determinístico.

## 2. Estado atual e problemas

| # | Sintoma | Local | Causa |
|---|---|---|---|
| 1 | Revisor não-determinístico | `revisor.py` (sem override) + `base.py:25-29` | Herda `settings.llm_temperature=0.7` |
| 2 | Impossível ter temperatura por agente | `base.py:23-32` (`__init__` fixa a temperatura global) | Sem parâmetro de override |
| 3 | Inconsistência interna | CWV usa `cwv_analisador_llm_temperature=0.1` (`config.py:88`), artigo não | Padrão não propagado ao pipeline de artigo |

## 3. Decisão de arquitetura

1. `BaseAgent.__init__` passa a aceitar `temperature: float | None = None` e `model: str | None = None`, caindo nos defaults globais quando `None`. O `lru_cache` de `_get_chat_model` já chaveia por esses valores → instâncias distintas convivem sem conflito.
2. Novo setting `artigo_revisor_temperature: float = 0.1` (mantém algum jitter mínimo, alinhado ao CWV). `RevisorAgent` usa esse valor.
3. **Opcional** (recomendado): `artigo_revisor_model: str | None = None`. Se setado, o revisor usa um modelo mais forte que o redator (ex.: um modelo melhor para julgar). Default `None` = mesmo modelo do pipeline. **Não reusar** `revisor_llm_model` (`config.py:84`) — esse é do workflow de inlinks; criar setting próprio evita acoplamento acidental.

### Alternativa descartada
- **Fixar `temperature=0.0` direto no `RevisorAgent` sem setting**: funciona, mas hard-code não dá controle por ambiente. Setting é o padrão da casa (todos os outros agentes têm).

## 4. Mudanças

### 4.1 `backend/app/agents/base.py`

```python
def __init__(
    self,
    usuario_id: str,
    tools: list | None = None,
    *,
    temperature: float | None = None,
    model: str | None = None,
):
    self.usuario_id = usuario_id
    provider = settings.llm_provider
    self.llm = _get_chat_model(
        provider,
        model or settings.llm_model,
        settings.llm_temperature if temperature is None else temperature,
        settings.openai_api_key if provider == "openai" else settings.zhipuai_api_key,
    )
    self._tools = tools or []
    if self._tools:
        self.llm = self.llm.bind_tools(self._tools)
```

### 4.2 `backend/app/config.py`

Adicionar perto dos outros settings de LLM (`:76-90`):

```python
artigo_revisor_temperature: float = 0.1
artigo_revisor_model: str | None = None   # None = usa llm_model do pipeline
```

### 4.3 `backend/app/agents/revisor.py`

```python
class RevisorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        super().__init__(
            usuario_id,
            temperature=settings.artigo_revisor_temperature,
            model=settings.artigo_revisor_model,
        )
```

Import de `settings` no topo (se ainda não houver):

```python
from app.config import settings
```

## 5. Verificação

### 5.1 Unit — o revisor pede temperatura baixa

```python
def test_revisor_usa_temperatura_baixa(monkeypatch):
    capturado = {}
    def fake_get_chat_model(provider, model, temperature, api_key):
        capturado["temperature"] = temperature
        capturado["model"] = model
        return object()
    monkeypatch.setattr("app.agents.base._get_chat_model", fake_get_chat_model)
    RevisorAgent("user-1")
    assert capturado["temperature"] == settings.artigo_revisor_temperature  # 0.1
```

### 5.2 Unit — redator mantém o default

```python
def test_redator_mantem_temperatura_global(monkeypatch):
    # mesmo padrão: RedatorAgent("u") deve usar settings.llm_temperature
```

### 5.3 E2E/observação — estabilidade do score

`backend/tests/e2e/test_e2e_redator_revisor.py`: rodar o revisor 3× sobre o **mesmo** artigo mockado (com LLM real ou stub determinístico) e verificar que o `score_qualidade` não oscila a ponto de cruzar o gate de 70 (variância pequena). Com stub, garantir que a chamada usa a temperatura esperada.

## 6. Riscos

- **`lru_cache(maxsize=8)`**: agora há mais combinações `(provider, model, temperature)` (redator vs. revisor). 8 ainda cobre o pipeline de artigo (2 temperaturas × poucos modelos). Se outros agentes adotarem overrides, aumentar `maxsize`.
- **Temperatura 0.1 ainda tem leve jitter**: aceitável e intencional. Se quiser 100% determinístico, setar `0.0` via env.
- **Modelo diferente para o revisor** (se usar `artigo_revisor_model`): custo/latência por chamada podem subir. Medir antes de habilitar em produção.

## 7. Fora de escopo

- Temperatura por agente para redator/brief/pesquisador/imagem (esta SPEC só toca o revisor; a infra fica pronta para os demais).
- Trocar o método de avaliação (rubrica, self-consistency, LLM-as-judge com múltiplas amostras).

## 8. Arquivos alterados

- `backend/app/agents/base.py` — `__init__` aceita `temperature`/`model`.
- `backend/app/config.py` — `artigo_revisor_temperature`, `artigo_revisor_model`.
- `backend/app/agents/revisor.py` — passa overrides no `super().__init__`.
- `backend/tests/e2e/test_e2e_redator_revisor.py` (ou unit novo).
