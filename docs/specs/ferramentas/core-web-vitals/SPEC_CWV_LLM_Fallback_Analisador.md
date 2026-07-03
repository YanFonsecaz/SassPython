# SPEC — CWV LLM Fallback do Analisador

**Status:** ✅ implementado · **Escopo:** backend (exercitar e robustecer o caminho LLM) + frontend (observabilidade do uso de LLM)
**Dependências:** [[SPEC_Ferramenta_Core_Web_Vitals]] (§3.5.1), [[SPEC_CWV_Base_Conhecimento]] (§5 — observability)
**Esforço estimado:** ~1.5 dias

## 1. Problema

O `CWVAnalisadorAgent` (em `app/agents/cwv/analisador.py`) tem dois caminhos:

1. **Fast-path determinístico** (linha 28-39): para cada `audit` de Lighthouse cujo ID está em `mapeamento_audit_kb()` (atualmente 35 audits mapeados), associa direto ao `kb_codigo` correspondente.
2. **LLM fallback** (linha 41-49): para audits **não mapeados** (residuais), monta prompt + chama LLM com `invoke_structured` esperando schema `ListaProblemas`.

### Estado atual

- O e2e em web.dev gerou 7 problemas — **todos via fast-path**. O LLM nunca foi chamado.
- A KB tem 34 entradas com 35 audits mapeados, cobrindo a grande maioria dos audits "problemáticos" comuns.
- O LLM fallback é o "seguro" para audits raros / específicos de Lighthouse (que evoluem ao longo do tempo).

### Riscos do caminho não exercitado

1. **Schema `ListaProblemas` pode estar errado** — pydantic pode aceitar saídas inválidas do LLM
2. **Prompt pode produzir alucinação** — LLM pode inventar `kb_codigo` que não existe
3. **Custo descontrolado** — cada audit residual consome tokens; sem limite, um site com 50 audits raros consome muito
4. **Latência cumulativa** — `SEMAFORO_LLM = 3` mas se o LLM demora 8s por chamada, 50 audits ÷ 3 = 17 batches × 8s = 136s só no analisador
5. **Sem observabilidade** — usuário não sabe que o LLM foi usado em sua análise

## 2. Objetivos

1. **Validar** que o LLM fallback funciona corretamente quando audits residuais aparecem
2. **Validar** que `kb_codigo` retornado pelo LLM existe na KB (descartar alucinação)
3. **Limitar** o caminho LLM: max N audits residuais por análise, fail-soft se LLM falha
4. **Observabilidade**: contador de `kb_miss` (já mencionado no SPEC KB §observability) + indicador no frontend de "esta análise usou IA para X audits"

## 3. Backend

### 3.1 Robustecer `CWVAnalisadorAgent.analisar`

```python
# app/agents/cwv/analisador.py

import logging
from pydantic import BaseModel, Field, field_validator
from app.agents.base import BaseAgent
from app.services.cwv_kb import listar_kb_codigos, mapeamento_audit_kb

logger = logging.getLogger(__name__)

MAX_AUDITS_RESIDUAIS_LLM = 15  # corta cauda; resto vira kb_codigo='outros'


class ProblemaIdentificado(BaseModel):
    kb_codigo: str
    contexto_especifico: dict = Field(default_factory=dict)
    audits_origem: list[str] = Field(default_factory=list)


class ListaProblemas(BaseModel):
    problemas: list[ProblemaIdentificado] = Field(default_factory=list)


class CWVAnalisadorAgent(BaseAgent):
    async def analisar(
        self, *, audits_falhos: list[dict], plataforma: str, metricas: dict
    ) -> list[dict]:
        diretos = mapeamento_audit_kb()
        identificados: list[ProblemaIdentificado] = []

        # Fast-path
        for audit in audits_falhos:
            aid = audit.get("id", "")
            if aid in diretos:
                identificados.append(ProblemaIdentificado(
                    kb_codigo=diretos[aid],
                    contexto_especifico=_extrair_contexto(audit),
                    audits_origem=[aid],
                ))

        # LLM fallback: audits residuais
        audits_residuais = [a for a in audits_falhos if a.get("id", "") not in diretos]
        audits_para_llm = audits_residuais[:MAX_AUDITS_RESIDUAIS_LLM]
        audits_cortados = audits_residuais[MAX_AUDITS_RESIDUAIS_LLM:]

        if audits_para_llm:
            try:
                kb_codigos_validos = {c["codigo"] for c in listar_kb_codigos()}
                prompt = _montar_prompt_analise(audits_para_llm, list(kb_codigos_validos), plataforma, metricas)
                resp: ListaProblemas = await self.invoke_structured(prompt, ListaProblemas)
                
                # Validação anti-alucinação: descarta kb_codigo inventado
                validos = [p for p in resp.problemas if p.kb_codigo in kb_codigos_validos]
                descartados = len(resp.problemas) - len(validos)
                if descartados:
                    logger.warning(
                        "CWV analisador descartou %d problemas com kb_codigo inexistente",
                        descartados,
                    )
                identificados.extend(validos)

                # Audits residuais sem mapeamento LLM → kb_codigo='outros' como catch-all
                audits_residuais_sem_problema = [
                    a for a in audits_para_llm
                    if not any(a.get("id", "") in p.audits_origem for p in validos)
                ]
                for a in audits_residuais_sem_problema:
                    _emit_kb_miss(a)
                    identificados.append(ProblemaIdentificado(
                        kb_codigo="outros",
                        contexto_especifico={**_extrair_contexto(a), "audit_id": a.get("id")},
                        audits_origem=[a.get("id", "")],
                    ))
            except Exception as e:
                logger.warning("CWV analisador LLM fallback falhou: %s", e)
                # Fail-soft: registra audits residuais como 'outros'
                for a in audits_para_llm:
                    _emit_kb_miss(a)

        # Audits cortados pelo cap
        for a in audits_cortados:
            logger.info("CWV analisador audit %s descartado por cap MAX_AUDITS_RESIDUAIS_LLM", a.get("id"))

        return _dedup_e_consolidar(identificados)


def _emit_kb_miss(audit: dict):
    """Emite evento de KB miss para observabilidade."""
    logger.warning(
        "CWV kb_miss: audit_id=%s title=%s — sem mapeamento na KB",
        audit.get("id"),
        audit.get("title"),
        extra={"event_type": "cwv.kb_miss", "audit_id": audit.get("id")},
    )
```

### 3.2 Persistir uso de LLM por análise

Adicionar coluna em `cwv_analise`:

```sql
ALTER TABLE cwv_analise
ADD COLUMN llm_usado BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN llm_audits_processados INTEGER NOT NULL DEFAULT 0,
ADD COLUMN llm_audits_descartados INTEGER NOT NULL DEFAULT 0;
```

Migration nova (`0015_cwv_llm_observability.py`).

No workflow (após node `analisar_seo`), propagar pra persistência:

```python
# EstadoCWV adiciona
llm_stats: dict[str, dict]  # url -> {"usado": bool, "processados": int, "descartados": int}
```

Persistir junto:

```python
analise = CwvAnalise(
    ...,
    llm_usado=stats.get("usado", False),
    llm_audits_processados=stats.get("processados", 0),
    llm_audits_descartados=stats.get("descartados", 0),
)
```

### 3.3 Endpoint inclui novos campos

`AnaliseResposta` schema adiciona:

```python
class AnaliseResposta(BaseModel):
    ...
    llm_usado: bool = False
    llm_audits_processados: int = 0
    llm_audits_descartados: int = 0
```

### 3.4 Endpoint admin: top KB misses

```python
@router.get("/core-web-vitals/admin/kb-misses", dependencies=[Depends(somente_admin)])
async def kb_misses_top(db: AsyncSession = Depends(get_db), dias: int = 30):
    """
    Lista os audits mais frequentes que caíram em kb_codigo='outros' nos últimos N dias.
    Usado pra priorizar quais novas entradas adicionar à KB.
    """
    # Query: cwv_problema WHERE kb_codigo='outros'
    #        agrupar por contexto_especifico->'audit_id'
    #        order by count desc limit 20
    ...
```

V1: pode ser script standalone em `backend/scripts/cwv_kb_top_misses.py` se preferir não criar endpoint admin agora.

## 4. Frontend

### 4.1 Indicador no dashboard URL

Quando `analiseAtual.llm_usado === true`, exibir badge:

```tsx
{analiseAtual.llm_usado && (
  <Tooltip>
    <TooltipTrigger>
      <Badge variant="outline" className="gap-1.5">
        <SparklesIcon className="size-3 text-purple-500" />
        IA usada · {analiseAtual.llm_audits_processados} audit{analiseAtual.llm_audits_processados !== 1 ? "s" : ""}
      </Badge>
    </TooltipTrigger>
    <TooltipContent>
      <p className="text-xs">Esta análise teve {analiseAtual.llm_audits_processados} pontos sem catálogo direto, processados por IA.</p>
    </TooltipContent>
  </Tooltip>
)}
```

### 4.2 Indicador no card de problema "outros"

Quando `problema.kb_codigo === "outros"`, badge especial:

```tsx
{p.kb_codigo === "outros" && (
  <Badge variant="outline" className="text-[10px] gap-1">
    <InfoIcon className="size-2.5" /> mapeamento incerto
  </Badge>
)}
```

E na documentacao_md mostra texto da entrada `outros` da KB explicando que esse audit ainda não tem entrada específica.

## 5. KB — Entrada `outros` (já existe, validar conteúdo)

Confirmar que a entrada `outros` na KB tem mensagem útil tipo:

```yaml
- codigo: outros
  titulo: "Recomendação não catalogada"
  severidade: 2
  metricas_afetadas: [LCP, CLS, INP]
  audits_lighthouse: []
  descricao: |
    Este ponto foi sinalizado pelo Lighthouse mas ainda não temos
    uma recomendação específica catalogada. Consulte o link de referência
    para entender o problema técnico e como solucioná-lo.
  solucoes:
    geral: |
      Recomendações genéricas:
      1. Consulte a documentação oficial do Lighthouse (link abaixo)
      2. Se o problema persistir, avalie escalar para um especialista
      3. Use o Chrome DevTools → Performance para investigar
  links_referencia:
    - titulo: "Lighthouse — Performance audits"
      url: "https://developer.chrome.com/docs/lighthouse/performance/"
```

## 6. Testes

### 6.1 `test_analisador.py` (NOVO)

```python
@pytest.mark.asyncio
async def test_analisador_fast_path_so(monkeypatch):
    """Audits todos mapeados → não chama LLM"""
    audits = [{"id": "largest-contentful-paint-element", "title": "...", "score": 0.5, ...}]
    agent = CWVAnalisadorAgent("user-id")
    monkeypatch.setattr(agent, "invoke_structured", AsyncMock(side_effect=Exception("LLM não deveria ser chamado")))
    problemas = await agent.analisar(audits_falhos=audits, plataforma="vtex", metricas={})
    assert len(problemas) == 1
    assert problemas[0]["kb_codigo"] in mapeamento_audit_kb().values()

@pytest.mark.asyncio
async def test_analisador_llm_fallback_valida_kb_codigo(monkeypatch):
    """LLM retorna kb_codigo inexistente → descartado"""
    audits = [{"id": "audit-inexistente-no-mapa", "title": "X", "score": 0.5}]
    agent = CWVAnalisadorAgent("user-id")
    monkeypatch.setattr(agent, "invoke_structured", AsyncMock(return_value=ListaProblemas(problemas=[
        ProblemaIdentificado(kb_codigo="codigo-alucinado", contexto_especifico={}, audits_origem=["audit-inexistente-no-mapa"]),
    ])))
    problemas = await agent.analisar(audits_falhos=audits, plataforma="vtex", metricas={})
    # kb_codigo alucinado é descartado, audit cai em 'outros'
    assert any(p["kb_codigo"] == "outros" for p in problemas)

@pytest.mark.asyncio
async def test_analisador_cap_audits_residuais(monkeypatch):
    """N > MAX_AUDITS_RESIDUAIS_LLM → resto é cortado e logado"""
    audits = [{"id": f"audit-{i}", "title": f"T{i}", "score": 0.5} for i in range(50)]
    agent = CWVAnalisadorAgent("user-id")
    monkeypatch.setattr(agent, "invoke_structured", AsyncMock(return_value=ListaProblemas(problemas=[])))
    problemas = await agent.analisar(audits_falhos=audits, plataforma="vtex", metricas={})
    # No máximo MAX_AUDITS_RESIDUAIS_LLM viraram 'outros'
    outros = [p for p in problemas if p["kb_codigo"] == "outros"]
    assert len(outros) <= MAX_AUDITS_RESIDUAIS_LLM

@pytest.mark.asyncio
async def test_analisador_llm_excecao_fail_soft(monkeypatch):
    """LLM levanta exception → análise continua com fast-path + 'outros'"""
    audits = [
        {"id": "largest-contentful-paint-element", "title": "LCP", "score": 0.5},  # fast-path
        {"id": "audit-raro", "title": "X", "score": 0.5},  # residual
    ]
    agent = CWVAnalisadorAgent("user-id")
    monkeypatch.setattr(agent, "invoke_structured", AsyncMock(side_effect=Exception("LLM down")))
    problemas = await agent.analisar(audits_falhos=audits, plataforma="vtex", metricas={})
    assert len(problemas) >= 1  # pelo menos o fast-path
```

## 7. Plano de execução

| Fase | O que | Esforço |
|---|---|---|
| L1 | Backend: refatorar `CWVAnalisadorAgent.analisar` com cap + anti-alucinação + fail-soft | 0.25 dia |
| L2 | Backend: migration 0015 (3 colunas em cwv_analise) + persistência stats | 0.25 dia |
| L3 | Backend: testes unitários do analisador | 0.25 dia |
| L4 | KB: validar/criar entrada `outros` com texto útil | 0.1 dia |
| L5 | Backend: script `cwv_kb_top_misses.py` (ad-hoc, sem endpoint) | 0.15 dia |
| L6 | Frontend: badge "IA usada" + badge "mapeamento incerto" | 0.5 dia |
| **Total** | | **~1.5 dias** |

## 8. Critério de pronto

- [ ] Testes cobrem: fast-path, LLM ok, LLM alucina, LLM falha, cap de audits
- [ ] Migration 0015 aplicada, novas colunas presentes
- [ ] Persistencia atualiza `llm_usado`/`llm_audits_processados`/`llm_audits_descartados`
- [ ] Análise real com URL que tenha audits residuais (ex: site complexo): badge "IA usada" aparece no frontend
- [ ] Script `cwv_kb_top_misses.py` retorna top 20 audits sem mapeamento (vazio se tudo mapeado)
- [ ] Frontend: tooltip do badge explica o que significa
- [ ] Documentado em README das specs CWV como rodar o script de top misses

## 9. Não-objetivos V1

- Auto-aprendizagem da KB a partir dos misses (humano em loop continua sendo a fonte de verdade)
- Endpoint admin para editar KB (PR no git permanece o caminho — vide [[SPEC_CWV_Base_Conhecimento]] §manutenção)
- A/B de prompts diferentes para o analisador
- Tracing detalhado de tokens/custo por análise (V2)
