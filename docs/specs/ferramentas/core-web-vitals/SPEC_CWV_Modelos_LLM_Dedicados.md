# SPEC #15 — Modelos LLM dedicados para o CWV (analisador + pesquisador)

**Status:** ✅ implementado · **Escopo:** backend (`config.py`, `agents/cwv/analisador.py`, futuro `agents/cwv/pesquisador.py`)
**Dependências:** independente. **A parte do analisador pode ser feita agora**; a parte do pesquisador entra junto com [[SPEC_CWV_Analisador_Tools_Pesquisa]].
**Esforço estimado:** ~1 h para a parte do analisador; ~30 min adicionais quando a parte do pesquisador for ativada junto com a SPEC #13.
**Prioridade:** **alta** para a parte do analisador (ganho imediato de determinismo); média para a parte do pesquisador (só importa quando tools entrarem).

## 1. Contexto e problema

A ferramenta CWV usa hoje o LLM global definido em `backend/.env`:

```
llm_provider=openai
llm_model=gpt-4o-mini
llm_temperature=0.7   # default herdado de config.py:78
```

Esse default é compartilhado por todas as ferramentas que instanciam `BaseAgent` sem override. As ferramentas de **inlinks** já fugiram desse default e usam modelo dedicado (ver `backend/app/config.py:82-85`):

```python
inseridor_llm_model: str = "gpt-4.1"
reranker_llm_model: str = "gpt-4.1"
revisor_llm_model: str = "gpt-4.1"
enriquecedor_llm_model: str = "gpt-4.1"
```

O padrão de uso é instanciar `ChatOpenAI` no `__init__` do agente quando há modelo dedicado (ver `backend/app/agents/inlinks/revisor.py:121-131`).

O CWV ficou no default global porque o uso original era **classificação simples** (mapear audit → kb_codigo). Funciona, mas tem dois problemas mensuráveis:

### 1.1 Temperature alta em tarefa determinística

`llm_temperature=0.7` é razoável para geração criativa (artigos, slogans). Para **classificação de vocabulário fechado** (escolher entre 34-49 códigos exatos) é alto demais:

- Reproduzibilidade pior — mesmo input pode mapear para códigos diferentes entre runs.
- Mais propensão a "outros" quando a confiança é borderline.
- Testes baseados em outputs do LLM ficam flaky.

O padrão da indústria para classificação é `0.0-0.2`.

### 1.2 Mini fraco em tool-use (futuro)

Quando a [[SPEC_CWV_Analisador_Tools_Pesquisa]] entrar (loop ReAct com `buscar_web` + `fetch_url`) e a [[SPEC_CWV_Analisador_Context7]] adicionar `buscar_docs_lib`, o agente vai precisar:

- Decidir qual tool chamar baseado no audit.
- Iterar até 4 vezes sem ficar em loop.
- Sintetizar resultados em PT-BR com fidelidade técnica.

Essa carga é onde modelos `-mini` historicamente quebram. Para o **pesquisador residual** (roda 0-3× por análise, baixo volume), o custo de subir para um modelo maior é desprezível e a qualidade do output (que o usuário vê) sobe muito.

## 2. Solução

Adicionar **dois campos dedicados** em `backend/app/config.py`, espelhando o padrão das inlinks. Não tocar no `llm_model` global (evita regressão em outras ferramentas).

### 2.1 Novos campos em `config.py`

Em `backend/app/config.py`, após a linha 85 (depois dos `enriquecedor_llm_model`):

```python
# CWV — analisador (classificação determinística, alta frequência)
cwv_analisador_llm_model: str = "gpt-4o-mini"
cwv_analisador_llm_temperature: float = 0.1

# CWV — pesquisador (tool-use + síntese, baixa frequência, qualidade > custo)
cwv_pesquisador_llm_model: str = "gpt-4.1"
cwv_pesquisador_llm_temperature: float = 0.4
```

**Por quê esses defaults:**

- `cwv_analisador_llm_model = gpt-4o-mini` — mantém custo baixo. Subir para `gpt-4.1-mini` é opcional e fácil de testar via env (`cwv_analisador_llm_model=gpt-4.1-mini`).
- `cwv_analisador_llm_temperature = 0.1` — determinismo na classificação. Não zero porque queremos tolerância mínima quando há empate entre dois códigos similares.
- `cwv_pesquisador_llm_model = gpt-4.1` — comprovadamente bom em tool-use e síntese técnica. Já validado no projeto via inlinks.
- `cwv_pesquisador_llm_temperature = 0.4` — alguma variação na escrita da doc final é desejável (sair de templates rígidos), mas não a ponto de inventar.

### 2.2 Aplicar no `CWVAnalisadorAgent`

Em `backend/app/agents/cwv/analisador.py`, mudar `class CWVAnalisadorAgent(BaseAgent)` para sobrescrever o LLM no `__init__`, seguindo o padrão das inlinks:

```python
class CWVAnalisadorAgent(BaseAgent):
    def __init__(self, usuario_id: str):
        super().__init__(usuario_id)
        from app.config import settings
        if settings.llm_provider == "openai" and settings.cwv_analisador_llm_model:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=settings.cwv_analisador_llm_model,
                temperature=settings.cwv_analisador_llm_temperature,
                api_key=settings.openai_api_key,
            )

    async def analisar(self, ...):  # método existente, sem mudança
        ...
```

**Observações:**

- A condição `settings.llm_provider == "openai"` é a mesma usada pelos agentes de inlinks — mantém o fallback para Zhipu/outros providers caso alguém volte a usar.
- O método `analisar` existente não muda. A única diferença é qual LLM ele invoca por baixo.
- O cache de `_get_chat_model` em `agents/base.py:13-19` continua valendo para o `super().__init__()` que cria o LLM global — depois é substituído. Levemente wasteful (cria duas instâncias), mas é o padrão já adotado nas inlinks e mantém código simétrico.

### 2.3 Aplicar no `CWVPesquisadorAgent` (junto com SPEC #13)

Quando [[SPEC_CWV_Analisador_Tools_Pesquisa]] criar `backend/app/agents/cwv/pesquisador.py`, o `__init__` deve usar o `cwv_pesquisador_llm_model`:

```python
class CWVPesquisadorAgent(BaseAgent):
    def __init__(self, usuario_id: str, plataforma: str):
        # tools definidos como na SPEC #13
        tools = [buscar_web, fetch_url]
        if plataforma in FRAMEWORKS_SUPORTADOS_CTX7 and settings.api_context7_key:
            tools.append(buscar_docs_lib)
        super().__init__(usuario_id, tools=tools)
        self.plataforma = plataforma

        if settings.llm_provider == "openai" and settings.cwv_pesquisador_llm_model:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=settings.cwv_pesquisador_llm_model,
                temperature=settings.cwv_pesquisador_llm_temperature,
                api_key=settings.openai_api_key,
            )
            self.llm = llm.bind_tools(tools) if tools else llm
```

A reaplicação de `bind_tools` é necessária porque substituir `self.llm` perde o binding que `BaseAgent.__init__` fez.

### 2.4 Documentar no `.env.example`

Em `backend/.env.example` (ou criar se não existir), adicionar as quatro novas chaves comentadas para sinalizar configurabilidade:

```
# Modelos LLM dedicados para CWV (sobrescrevem llm_model global)
# Analisador roda 1x por análise (classificação) — mini é suficiente, temperature baixa
cwv_analisador_llm_model=gpt-4o-mini
cwv_analisador_llm_temperature=0.1
# Pesquisador roda 0-3x por análise (tool-use + síntese de doc) — modelo maior justificado
cwv_pesquisador_llm_model=gpt-4.1
cwv_pesquisador_llm_temperature=0.4
```

## 3. Critérios de aceitação

1. **Config carrega defaults:** sem nenhuma das 4 novas chaves no `.env`, app sobe e usa defaults da `config.py`.
2. **Override por env funciona:** com `cwv_analisador_llm_model=gpt-4.1-mini` no `.env`, o `CWVAnalisadorAgent.llm` é instância de `ChatOpenAI(model="gpt-4.1-mini")` (verificar via log de debug ou snapshot).
3. **Temperature aplicada:** `self.llm.temperature == 0.1` no analisador.
4. **Determinismo:** rodar a mesma análise CWV 3× em sequência sobre URL controlada (`https://example.com/`) — esperar **mesmos kb_codigos** identificados nas 3 vezes (sem variação por temperature).
5. **Sem regressão funcional:** suite existente (`pytest backend/tests/`) continua verde.
6. **Sem impacto em outras ferramentas:** inlinks, gerar-artigo e demais não regridem (não compartilham as novas chaves).
7. **Métrica de fallback:** taxa de `kb_codigo='outros'` em 10 análises pré e pós-mudança não aumenta (esperado: igual ou menor por causa de menos "indecisão" do LLM com temperature baixa).

## 4. Arquivos afetados

- `backend/app/config.py` — +4 campos.
- `backend/app/agents/cwv/analisador.py` — `__init__` sobrescrevendo `self.llm` (segue padrão de `inlinks/revisor.py:121-131`).
- `backend/app/agents/cwv/pesquisador.py` (a criar em [[SPEC_CWV_Analisador_Tools_Pesquisa]]) — `__init__` sobrescrevendo + reaplicando `bind_tools`.
- `backend/.env.example` — documentar as 4 chaves.
- `backend/tests/unit/test_cwv_analisador.py` — adicionar teste que valida o modelo e temperature instanciados.

## 5. Fora de escopo

- Trocar provider (OpenAI → Anthropic/Gemini). Não é o gargalo hoje.
- Adicionar campos por agente em outras ferramentas além do CWV.
- Ajustar `llm_max_tokens` por agente (default global 4096 cobre os casos atuais — revisitar quando documentações ficarem muito longas).
- Tunar temperature dinamicamente baseado em qual etapa do workflow está rodando.

## 6. Riscos

- **`gpt-4.1` mais caro que `gpt-4o-mini`** — sim, mas só roda para audits residuais (0-3 por análise). Diferença em USD por análise é da ordem de centavos, irrelevante perto dos 16 créditos cobrados.
- **`bind_tools` em cima do LLM substituído pode quebrar** se a ordem dos `__init__` for invertida. Mitigação: teste explícito em `tests/unit/test_cwv_pesquisador.py` verificando que `self.llm.kwargs.get('tools')` está populado pós-init.
- **Determinismo com temperature 0.1 não é absoluto** — OpenAI não garante 0 entre runs. Critério #4 admite mesma classificação, não bytes idênticos.

## 7. Plano de rollout

1. **Hoje:** aplicar parte do analisador (defaults + `__init__` override + temperature 0.1). Ganho imediato de determinismo e custo zero.
2. **Junto com SPEC #13:** aplicar parte do pesquisador. Custo extra justificado pela qualidade de tool-use.
3. **Pós-rollout:** monitorar por 1 semana taxa de `kb_codigo='outros'` e tempo médio de análise. Se métricas piorarem, reverter via env (`cwv_analisador_llm_temperature=0.7` etc.) sem deploy.

## 8. Custo aproximado por análise (estimativa)

Preços OpenAI (jan/2026, sujeitos a mudança):

| Configuração | Custo médio/análise |
|---|---|
| Hoje: `gpt-4o-mini` em tudo | ~$0.002 |
| Pós-SPEC: `gpt-4o-mini` analisador + (sem pesquisador) | ~$0.002 (igual) |
| Pós-SPEC + pesquisador `gpt-4.1` (com 2 audits residuais) | ~$0.020 |
| Alternativa "premium": `gpt-4.1` em tudo | ~$0.080 |

Recomendação fica no ponto de melhor relação qualidade-custo: barato no caminho frequente (classificação), generoso no caminho raro mas crítico (síntese de doc com tool-use).
