# SPEC — IA de Visão Multimodal (analisador + documentador)

**Status:** a aplicar · **Data:** 2026-05-30
**Escopo:** backend — `app/agents/parecer/{analisador,documentador,workflow}.py` + schemas estruturados + prompts + seleção de modelo
**Reusos:** `BaseAgent` / `invoke_structured` (`app/agents/base.py`), `_get_chat_model`, `chamada_llm_com_retry`, `ferramenta_service`, `credito_service`
**Specs irmãs:** [[SPEC_Parecer_Ferramenta]] (quem chama o workflow) · [[SPEC_Parecer_Geracao_Docx]] (consome a `estrutura`)
**Referência:** padrão de modelos dedicados em [[SPEC_CWV_Modelos_LLM_Dedicados]]

## 1. Objetivo

Transformar **prints + descrições curtas** (canvas livre) em um **parecer técnico estruturado** no
formato do documento de referência. Duas etapas:

1. **Analisador (visão):** para cada imagem, com o texto adjacente como contexto, descreve **o que a
   imagem mostra** e identifica o **problema técnico**, o **impacto** (LCP/CLS/SEO/…) e **onde ocorre**.
2. **Documentador (síntese):** agrega os achados + as notas do usuário e redige o parecer completo no
   padrão do `[Imecap] Parecer Tecnico Performance (1).docx`: **cabeçalho de 3 linhas** (título,
   subtítulo, linha de escopo), **seções por página/URL** (`N.`) → **subseções** (`N.M.`) com
   `Problema / Evidência(s) / Solução`, e **recomendações globais** por último. _Sem_ tabela de
   metadados e _sem_ sumário executivo.

> Primeiro uso de **visão** no projeto. Nenhum agente atual envia imagem ao LLM.

## 2. Seleção de modelo — **2 modelos OpenAI dedicados**

`BaseAgent.__init__` instancia `settings.llm_model` (pode ser ZhipuAI/sem visão). Aqui instanciamos
**explicitamente** modelos OpenAI, reaproveitando o factory cacheado `_get_chat_model`. Melhor
resultado = separar **visão** (barato/rápido por imagem) de **redação** (prosa melhor), como o CWV
faz em [[SPEC_CWV_Modelos_LLM_Dedicados]]:

```python
# app/agents/parecer/modelos.py
from app.agents.base import _get_chat_model
from app.config import settings

def get_modelo_visao():       # analisador: 1 chamada por imagem
    return _get_chat_model("openai", settings.parecer_analisador_model, settings.llm_temperature, settings.openai_api_key)

def get_modelo_redacao():     # documentador: síntese do parecer
    return _get_chat_model("openai", settings.parecer_documentador_model, 0.4, settings.openai_api_key)
```

- Defaults: `parecer_analisador_model = "gpt-4o"` (visão), `parecer_documentador_model = "gpt-4.1"`
  (redação). Ambos OpenAI; provider **fixo** "openai" (não usar `settings.llm_provider`).
- Pré-condição: `settings.openai_api_key` presente; senão a execução falha com `ErroPermanente`
  ("OPENAI_API_KEY ausente — visão indisponível") e **libera os créditos** reservados.

## 3. Schemas estruturados (`app/schemas/parecer.py`, continua)

Saída tipada via `invoke_structured(prompt, schema)` (function calling). Espelha as seções do
documento de referência.

```python
from typing import Literal
from pydantic import BaseModel, Field

Impacto = Literal["LCP", "CLS", "INP", "FCP", "TTFB", "SEO", "Indexacao", "Acessibilidade", "Outro"]

class AchadoImagem(BaseModel):
    """Saída do analisador para UMA imagem."""
    indice_global: int                 # índice da imagem no conjunto (ordem do canvas)
    o_que_mostra: str                  # legenda objetiva do print (vira "Evidência")
    problema: str                      # problema técnico identificado
    impacto: list[Impacto]
    onde_ocorre: str                   # ex.: "Página de produto (Mobile)"
    confianca: float = Field(ge=0, le=1)

# Estrutura espelha o documento de referencia [Imecap] Parecer Tecnico Performance (1).docx:
# cabecalho de 3 linhas -> secoes por pagina (N.) -> subsecoes (N.M.) com
# Problema/Evidencia(s)/Solucao -> "Recomendacoes globais" por ultimo.
# SEM tabela de metadados e SEM sumario executivo.
class EvidenciaItem(BaseModel):
    legenda: str                       # texto após "Evidência:"
    imagens_indices: list[int] = Field(default_factory=list)  # quais imagens embutir

class ProblemaSecao(BaseModel):
    descricao: str                     # parágrafo "Problema"
    evidencias: list[EvidenciaItem] = Field(default_factory=list)  # 1+ "Evidência:"
    solucao: str                       # parágrafo "Solução"
    solucao_escopo: str | None = None  # ex.: "Desktop e Mobile" → "Solução (Desktop e Mobile)"

class SubSecao(BaseModel):
    titulo: str                        # ex.: "LCP atrasado por CSS bloqueante" ou "Versão Desktop"
    problemas: list[ProblemaSecao]     # renderer numera "Problema 1/2" se houver >1

class SecaoParecer(BaseModel):
    titulo: str                        # ex.: "Página de categoria — /cabelos"
    url: str | None = None
    observacao: str | None = None      # ex.: "Observação: ocorre em Desktop e Mobile."
    subsecoes: list[SubSecao]

class PrioridadeGlobal(BaseModel):
    titulo: str                        # ex.: "Prioridade 1 — Eliminar render-blocking"
    itens: list[str]

class ParecerEstruturado(BaseModel):
    titulo: str = "PARECER TÉCNICO — SEO / PERFORMANCE"
    subtitulo: str                     # ex.: "Otimização de Core Web Vitals"
    escopo_linha: str                  # ex.: "LCP e CLS — dominio.com.br (Cliente)"
    secoes: list[SecaoParecer]
    recomendacoes_globais: list[PrioridadeGlobal]
```

> O cabeçalho não tem data nem tabela de metadados (segue o doc de referência refinado). O nome do
> cliente entra na `escopo_linha` (vem do backend, não inventado). Persistência: `site` da listagem
> recebe a `escopo_linha`; não há mais coluna `plataforma` preenchida pela IA.

## 4. Agente Analisador (`app/agents/parecer/analisador.py`, novo)

Uma chamada de visão **por imagem** (paralelizável com `asyncio.gather`, respeitando o
`chamada_llm_com_retry`/guard existente). Mensagem multimodal LangChain:

```python
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.parecer.modelos import get_modelo_visao
from app.schemas.parecer import AchadoImagem

SYSTEM_ANALISE = (
    "Você é um especialista em SEO técnico e Core Web Vitals. Recebe UM print (screenshot) de "
    "ferramentas como Chrome DevTools / PageSpeed / DOM, com uma nota curta do analista. "
    "Descreva objetivamente o que o print mostra e identifique o problema técnico, seu impacto e "
    "onde ocorre. Não invente dados que não estejam visíveis. Responda em português."
)

async def analisar_imagem(usuario_id: str, indice: int, data_uri: str, nota: str) -> AchadoImagem:
    llm = get_modelo_visao().with_structured_output(AchadoImagem, method="function_calling")
    msgs = [
        SystemMessage(content=SYSTEM_ANALISE),
        HumanMessage(content=[
            {"type": "text", "text": f"Índice da imagem: {indice}. Nota do analista: {nota or '(sem nota)'}"},
            {"type": "image_url", "image_url": {"url": data_uri}},
        ]),
    ]
    from app.core.llm_guard import chamada_llm_com_retry
    achado = await chamada_llm_com_retry(llm, msgs, usuario_id)
    achado.indice_global = indice
    return achado
```

**GIF animado:** OpenAI usa o 1º frame; manter o `data_uri` original (o documentador também recebe a
imagem). Se o `data:image/gif` falhar, converter para PNG (1º frame, Pillow) e reenviar.

**Blocos sem imagem:** se um bloco só tem texto (descrição de um problema sem print), ele entra
direto na etapa de síntese como contexto textual (não passa pelo analisador).

## 5. Agente Documentador (`app/agents/parecer/documentador.py`, novo)

Recebe: nome do cliente, blocos (texto na ordem), e a lista de `AchadoImagem`. Produz
`ParecerEstruturado` numa chamada estruturada usando o **modelo de redação**
(`get_modelo_redacao()` → `parecer_documentador_model`, default `gpt-4.1`) com
`.with_structured_output(ParecerEstruturado, method="function_calling")`.

```python
SYSTEM_DOC = (
    "Você redige PARECERES TÉCNICOS de SEO/Performance no padrão de uma agência...\n"
    "ESTRUTURA OBRIGATÓRIA (espelha o doc de referência):\n"
    "- Cabeçalho: 'subtitulo' curto + 'escopo_linha' = '<foco> — <domínio> (<Cliente>)'.\n"
    "- 'secoes' (uma por página/URL): titulo, url?, observacao?, e 'subsecoes'.\n"
    "- cada 'subsecao': titulo + 1+ 'problemas' (descricao, 'evidencias' [legenda + imagens_indices], "
    "solucao, solucao_escopo?).\n"
    "- 'recomendacoes_globais': 'Prioridade 1..N' com itens.\n"
    "NÃO inclua tabela de metadados nem sumário executivo. NÃO invente URLs/dados não suportados."
)
# texto completo em backend/app/agents/parecer/documentador.py
```

- O **nome do cliente** = `entrada["cliente_nome"]` (vem da rota; não inventar) — entra na
  `escopo_linha`. Não há data nem tabela de metadados no formato.
- O documentador **deve** referenciar os índices de imagem corretos em `evidencias[].imagens_indices`,
  para o renderer embutir a Evidência certa (ver [[SPEC_Parecer_Geracao_Docx]]).

## 6. Workflow (`app/agents/parecer/workflow.py`, novo)

Função chamada pelo worker. Mantém simples (sem LangGraph — não há ramificação/estado complexo):

```python
import logging
from datetime import UTC, datetime
from app.db.session import async_session_factory
from app.services import ferramenta_service, credito_service
from app.schemas.parecer import GerarParecerRequest
from app.agents.parecer.analisador import analisar_imagem
from app.agents.parecer.documentador import gerar_parecer_estruturado
from app.services.parecer_service import estrutura_para_html
from app.core.excecoes import ErroPermanente

logger = logging.getLogger(__name__)

async def executar_workflow_parecer(execucao_id: str, ctx=None):
    async with async_session_factory() as session:
        ex = await ferramenta_service.buscar_execucao(session, execucao_id)
        if not ex:
            return
        # capturar escalares enquanto a sessão está aberta (evita DetachedInstance após commit)
        entrada = dict(ex.entrada_json)
        usuario_id = str(ex.usuario_id)
        cliente_id = str(ex.cliente_id)
        custo = ex.creditos_cobrados
        await ferramenta_service.atualizar_execucao(session, execucao_id, status="processando", etapa_atual="analisando_imagens")
        await session.commit()

    if not _tem_openai_key():
        await _falhar(execucao_id, usuario_id, custo, "OPENAI_API_KEY ausente — visão indisponível")
        raise ErroPermanente("OPENAI_API_KEY ausente")

    # 1) Visão por imagem (numera as imagens na ordem global do canvas)
    achados, indice = [], 0
    pares_img = []  # (indice, data_uri) para o renderer
    for bloco in entrada["blocos"]:
        nota = bloco.get("texto", "")
        for data_uri in bloco.get("imagens", []):
            pares_img.append((indice, data_uri))
            indice += 1
    import asyncio
    achados = await asyncio.gather(*[analisar_imagem(usuario_id, i, uri, _nota_do_indice(entrada, i)) for i, uri in pares_img])

    # 2) Síntese
    await _set_etapa(execucao_id, "redigindo_parecer")
    estrutura = await gerar_parecer_estruturado(
        usuario_id, cliente_nome=entrada["cliente_nome"], blocos=entrada["blocos"], achados=list(achados),
    )
    # (sem data/metadados no formato refinado)

    # 3) Renderiza HTML (com as imagens embutidas por índice)
    parecer_html = estrutura_para_html(estrutura, imagens_por_indice=dict(pares_img))

    # 4) Persistência (tabela `parecer`) + ponteiro na execução + cobrança
    from app.services import parecer_persistencia
    async with async_session_factory() as session:
        parecer = await parecer_persistencia.criar_parecer(
            session, execucao_id=execucao_id, cliente_id=cliente_id, usuario_id=usuario_id,
            cliente_nome=entrada["cliente_nome"], estrutura=estrutura.model_dump(),
            parecer_html=parecer_html, n_imagens=len(pares_img),
            modelo=settings.parecer_documentador_model,
        )
        await ferramenta_service.atualizar_execucao(
            session, execucao_id, status="concluida", etapa_atual="concluido",
            concluida_em=datetime.now(UTC), resultado_json={"parecer_id": str(parecer.id)},
        )
        await credito_service.confirmar_debito(session, usuario_id, custo)
        await session.commit()
```

Ver [[SPEC_Parecer_Dados_e_Persistencia]] §4.1 (mesma sequência).

Tratamento de erro segue o padrão do `_executar_job` (worker): `ErroTransitorio` → retry com defer,
`ErroPermanente`/inesperado → `_marcar_falhou`. **No caminho de falha, liberar a reserva de créditos**
(`credito_service.liberar_reserva`) — encapsular num helper `_falhar(...)`.

## 7. Custo de tokens / latência

- 1 chamada de visão por imagem + 1 de síntese. Para ~6 imagens: ~7 chamadas → cabe no
  `parecer_workflow_timeout=600s` com folga.
- Paralelizar a visão (`asyncio.gather`) reduz latência total; o `chamada_llm_com_retry`/guard já
  trata rate limit/retry.
- Custo em créditos: `10 + 3×n_imagens` (cap 90) — ver [[SPEC_Parecer_Ferramenta]] §3.2.

## 8. Critérios de aceite

- [ ] `analisar_imagem` retorna `AchadoImagem` coerente para um print real (ex.: usar `cwv-*.png` do repo)
- [ ] `gerar_parecer_estruturado` devolve `ParecerEstruturado` válido com seções por página e `imagens_indices` corretos
- [ ] Provider forçado em OpenAI; falha clara se faltar `OPENAI_API_KEY`
- [ ] `escopo_linha` usa o `cliente_nome` vindo do backend (não inventado); sem tabela de metadados/sumário
- [ ] Workflow grava `resultado_json` e confirma/libera créditos conforme o caso
