# SPEC — Ferramenta "Parecer Técnico" (principal / orquestração)

**Status:** ✅ implementado · **Data:** 2026-05-30
**Escopo:** backend — schemas + rota (`/api/ferramentas/parecer`) + job ARQ + service de custo/persistência + cobrança · reusa `ExecucaoFerramenta` (sem tabela nova)
**Reusos:** `ExecucaoFerramenta` + ARQ + `BaseAgent` + `ferramenta_service` + `credito_service` (mesmo padrão de [[SPEC_Ferramenta_Core_Web_Vitals]])
**Specs irmãs:** [[SPEC_Parecer_IA_Visao_Multimodal]] (o que o worker chama) · [[SPEC_Parecer_Geracao_Docx]] (o que o `exportar` chama) · [[SPEC_Parecer_Editor_Frontend]] (quem consome a rota)

## 1. Visão geral

### 1.1 Problema

Gestores de SEO da agência precisam entregar a clientes/parceiros **documentos de correção** no
padrão "Parecer Técnico". Hoje é manual: juntar prints, descrever o problema, escrever solução e
formatar no Word. Queremos que o usuário **cole os prints + uma descrição curta** e a IA **redija o
parecer pronto** no padrão da casa, com **preview editável** e **export `.docx`**.

### 1.2 Fluxo do usuário

1. Acessa `/ferramentas/parecer`, seleciona o **cliente**.
2. No **editor (canvas livre)** cola prints/gifs e escreve descrições curtas na ordem que quiser.
3. Clica **Gerar** → confirma custo (créditos) → análise dispara.
4. Aguarda (~10–60s) com estado de loading; o front faz **polling** do status.
5. O parecer gerado **carrega no editor** (preview editável); o usuário ajusta.
6. Clica **Baixar `.docx`** e envia o arquivo à agência.

### 1.3 Diferença para o CWV

A ferramenta CWV é **automática** (coleta PSI, classifica audits). Esta é **humano-no-loop**: o
usuário traz a evidência (prints) e a nota; a IA **redige** o documento. São complementares — esta
serve para **qualquer** problema de SEO, não só performance.

## 2. Modelo de dados — `ExecucaoFerramenta` (lifecycle) + tabela `parecer` (documento)

> **Decisão de melhor resultado:** dividir responsabilidades como o CWV faz. Detalhes completos da
> tabela/model/migration/persistência em **[[SPEC_Parecer_Dados_e_Persistencia]]**.

- **`execucoes_ferramentas`** (existente) — ciclo de vida + créditos + Histórico genérico:
  - `ferramenta = "parecer_tecnico"`
  - `entrada_json` = payload normalizado (ver §3.1): blocos com texto + imagens base64 já
    **comprimidas no cliente** (precisamos delas no worker). Ver nota de tamanho em §6.
  - `resultado_json` = `{ "parecer_id": "<uuid>" }` (ponteiro para o documento)
  - `status`: `pendente → enfileirado → processando → concluida | falhou`
  - `creditos_cobrados`, `thread_id`, `timeout_em`, `erro_msg`, `concluida_em` — como nas demais.
- **`parecer`** (nova) — o documento: `titulo/subtitulo/site/plataforma/cliente_nome`,
  `meta_json`, `estrutura_json`, `parecer_html` (fonte do re-download), `n_imagens`, `modelo`.
  Habilita "Meus Pareceres" ([[SPEC_Parecer_Historico_UI]]).

> As imagens (evidências) ficam **base64 inline** em `estrutura_json`/`parecer_html` (documento
> autocontido). Caminho de escala: Supabase Storage (V2).

## 3. Backend

### 3.1 Schemas Pydantic (`app/schemas/parecer.py`, novo)

```python
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

# Um "bloco" do canvas livre: texto e/ou imagens, na ordem em que aparecem.
# imagens = data URIs base64 (já comprimidas no cliente, ver SPEC_Parecer_Editor_Frontend).
class BlocoEntrada(BaseModel):
    texto: str = Field(default="", max_length=8000)
    imagens: list[str] = Field(default_factory=list, max_length=10)  # data:image/...;base64,...


class GerarParecerRequest(BaseModel):
    cliente_id: UUID
    titulo_sugerido: str | None = Field(default=None, max_length=200)  # opcional
    blocos: list[BlocoEntrada] = Field(min_length=1, max_length=40)

    @property
    def total_imagens(self) -> int:
        return sum(len(b.imagens) for b in self.blocos)


class CustoParecerResponse(BaseModel):
    custo: int
    custo_base: int
    custo_por_imagem: int
    n_imagens: int


class ParecerExecucaoResposta(BaseModel):
    id: str
    ferramenta: str
    status: str
    etapa_atual: str | None = None
    creditos_cobrados: int | None = None
    # presentes quando status == "concluida":
    parecer_html: str | None = None
    estrutura: dict | None = None
    erro_msg: str | None = None
    criado_em: str
    concluida_em: str | None = None


class ExportarParecerRequest(BaseModel):
    # HTML final editado no Tiptap (vocabulário controlado — ver SPEC_Parecer_Geracao_Docx §2)
    html: str = Field(min_length=1)
    nome_arquivo: str | None = Field(default=None, max_length=120)
```

### 3.2 Custo (`app/services/ferramenta_service.py`, editar)

Seguindo o padrão dos demais (`CUSTO_BASE`, `calcular_custo_*`):

```python
CUSTO_BASE_PARECER = 10          # síntese + montagem do documento
CUSTO_POR_IMAGEM_PARECER = 3     # 1 chamada de visão por imagem
CUSTO_MAX_PARECER = 90

def calcular_custo_parecer(n_imagens: int) -> int:
    return min(CUSTO_BASE_PARECER + n_imagens * CUSTO_POR_IMAGEM_PARECER, CUSTO_MAX_PARECER)
```

Adicionar a entrada correspondente em `CUSTOS_TABELA` (para a tela de transparência de custos).
Os valores são **configuráveis** — podem iniciar baixos (ou 0) durante a validação.

### 3.3 Rota (`app/routers/parecer.py`, novo)

Espelha `ferramentas_cwv.py` (validar cliente → reservar créditos → criar execução → enfileirar →
202). Registrar em `app/main.py` com prefixo `/api/ferramentas` (como os demais).

> **Refinado por [[SPEC_Parecer_Dados_e_Persistencia]] §4.2:** com a tabela `parecer`, o
> `GET /parecer/execucao/{id}` serve **só de poll de status** (passa a devolver `parecer_id` quando
> `concluida`); o **documento** vem de `GET /parecer/{parecer_id}` e o **`exportar` passa a ser
> chaveado por `parecer_id`**. Os blocos de código abaixo mostram a forma base (resultado inline);
> use a forma refinada da #2 quando implementar.

```python
import logging, uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, rate_limit_autenticado
from app.models.cliente import Cliente
from app.models.usuario import Usuario
from app.models.execucao_ferramenta import ExecucaoFerramenta
from app.schemas.parecer import (
    GerarParecerRequest, CustoParecerResponse, ParecerExecucaoResposta, ExportarParecerRequest,
)
from app.services import ferramenta_service, credito_service

logger = logging.getLogger(__name__)
router = APIRouter()


async def _validar_cliente(db, usuario_id: str, cliente_id: str) -> Cliente:
    res = await db.execute(select(Cliente).where(Cliente.id == cliente_id, Cliente.usuario_id == usuario_id))
    cliente = res.scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return cliente


@router.post("/parecer/custo", response_model=CustoParecerResponse)
async def custo_parecer(
    body: GerarParecerRequest,
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    n = body.total_imagens
    return {
        "custo": ferramenta_service.calcular_custo_parecer(n),
        "custo_base": ferramenta_service.CUSTO_BASE_PARECER,
        "custo_por_imagem": ferramenta_service.CUSTO_POR_IMAGEM_PARECER,
        "n_imagens": n,
    }


@router.post("/parecer/gerar", status_code=202)
async def gerar_parecer(
    body: GerarParecerRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("parecer_gerar", max_requests=5, window_seconds=300)),
) -> dict[str, Any]:
    cliente = await _validar_cliente(db, str(usuario.id), str(body.cliente_id))
    custo = ferramenta_service.calcular_custo_parecer(body.total_imagens)

    try:
        await credito_service.reservar_creditos(db, str(usuario.id), custo)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail="Creditos insuficientes") from exc

    entrada = body.model_dump(mode="json")
    entrada["cliente_nome"] = cliente.nome  # para a IA preencher o cabeçalho sem inventar
    execucao = ExecucaoFerramenta(
        usuario_id=str(usuario.id),
        cliente_id=str(body.cliente_id),
        ferramenta="parecer_tecnico",
        status="pendente",
        entrada_json=entrada,
        creditos_cobrados=custo,
        thread_id=str(uuid.uuid4()),
        timeout_em=datetime.now(UTC) + timedelta(seconds=settings.parecer_workflow_timeout),
    )
    db.add(execucao)
    await db.flush()

    try:
        from app.core.redis_pool import get_redis_pool
        redis = await get_redis_pool()
        job = await redis.enqueue_job("executar_workflow_parecer", str(execucao.id))
        execucao.job_id = job.job_id
        execucao.status = "enfileirado"
        await db.flush()
    except Exception as e:
        logger.error("Falha ao enfileirar parecer: %s", e)
        await credito_service.liberar_reserva(db, str(usuario.id), custo)
        execucao.status = "falhou"
        execucao.erro_msg = "Falha ao enfileirar workflow"
        await db.flush()

    return {"id": str(execucao.id), "status": execucao.status, "custo_estimado": custo}


@router.get("/parecer/execucao/{execucao_id}", response_model=ParecerExecucaoResposta)
async def buscar_execucao_parecer(
    execucao_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    res = await db.execute(
        select(ExecucaoFerramenta).where(
            ExecucaoFerramenta.id == execucao_id,
            ExecucaoFerramenta.usuario_id == usuario.id,
        )
    )
    ex = res.scalar_one_or_none()
    if not ex:
        raise HTTPException(status_code=404, detail="Execucao nao encontrada")
    resultado = ex.resultado_json or {}
    return {
        "id": str(ex.id), "ferramenta": ex.ferramenta, "status": ex.status,
        "etapa_atual": ex.etapa_atual, "creditos_cobrados": ex.creditos_cobrados,
        "parecer_html": resultado.get("parecer_html"),
        "estrutura": resultado.get("estrutura"),
        "erro_msg": ex.erro_msg,
        "criado_em": str(ex.criado_em),
        "concluida_em": str(ex.concluida_em) if ex.concluida_em else None,
    }


@router.post("/parecer/{execucao_id}/exportar")
async def exportar_parecer(
    execucao_id: str,
    body: ExportarParecerRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("parecer_exportar", max_requests=20, window_seconds=300)),
) -> StreamingResponse:
    res = await db.execute(
        select(ExecucaoFerramenta).where(
            ExecucaoFerramenta.id == execucao_id,
            ExecucaoFerramenta.usuario_id == usuario.id,
        )
    )
    ex = res.scalar_one_or_none()
    if not ex:
        raise HTTPException(status_code=404, detail="Execucao nao encontrada")

    # Persistir o HTML editado de volta (para re-download / histórico)
    resultado = dict(ex.resultado_json or {})
    resultado["parecer_html"] = body.html
    await ferramenta_service.atualizar_execucao(db, execucao_id, resultado_json=resultado)
    await db.commit()

    from app.services.parecer_service import html_para_docx_bytes
    docx_bytes = html_para_docx_bytes(body.html)  # ver SPEC_Parecer_Geracao_Docx

    nome = (body.nome_arquivo or "parecer-tecnico").rsplit(".", 1)[0]
    import io
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nome}.docx"'},
    )
```

### 3.4 Job no worker (`app/worker.py`, editar)

```python
async def executar_workflow_parecer(ctx, execucao_id: str):
    await _executar_job(ctx, "app.agents.parecer.workflow", "executar_workflow_parecer", execucao_id)

class WorkerSettings:
    functions = [..., executar_workflow_cwv, executar_workflow_parecer]  # adicionar
```

O handler `app.agents.parecer.workflow.executar_workflow_parecer(execucao_id, ctx=...)` está
especificado em [[SPEC_Parecer_IA_Visao_Multimodal]]. Ele:
1. carrega a execução (`ferramenta_service.buscar_execucao`), seta `status="processando"`;
2. roda visão por imagem + síntese → `estrutura`; renderiza `parecer_html` (chama o renderer da
   [[SPEC_Parecer_Geracao_Docx]] §1, `estrutura_para_html`);
3. grava `resultado_json={estrutura, parecer_html, n_imagens, modelo}`, `status="concluida"`,
   `concluida_em=now`;
4. **confirma o débito** dos créditos reservados (`credito_service.confirmar_debito`).
   Em falha permanente, o worker já faz `_marcar_falhou` + o refund deve ser liberado
   (`credito_service.liberar_reserva`) no caminho de erro do handler.

### 3.5 Config (`app/config.py`, editar)

```python
parecer_analisador_model: str = "gpt-4o"    # VISÃO: 1 chamada por imagem
parecer_documentador_model: str = "gpt-4.1" # REDAÇÃO: síntese do parecer (prosa melhor)
parecer_workflow_timeout: int = 600          # 10 min
custo_base_parecer: int = 10                 # custo configurável por env (pode iniciar baixo/0)
```

`OPENAI_API_KEY` já é configurada no `render.yaml`. A ferramenta **exige** provider OpenAI para a
parte de visão (independente do `LLM_PROVIDER` default do projeto). Modelos dedicados seguem o padrão
de [[SPEC_CWV_Modelos_LLM_Dedicados]].

## 4. Cobrança (resumo do ciclo)

| Momento | Ação | Função |
|---|---|---|
| `gerar` | reserva `custo` | `credito_service.reservar_creditos` |
| falha ao enfileirar | libera reserva | `credito_service.liberar_reserva` |
| worker concluiu | confirma débito | `credito_service.confirmar_debito` |
| worker falhou | libera reserva + `_marcar_falhou` | `credito_service.liberar_reserva` |

## 5. Segurança / multi-tenant

- Toda leitura filtra por `usuario_id == usuario.id` (idem CWV).
- `_validar_cliente` garante que o cliente pertence ao usuário.
- `rate_limit_autenticado` em `gerar` (5/5min) e `exportar` (20/5min).
- Validar tamanho do payload (ver §6) e os tipos de imagem aceitos (`data:image/(png|jpeg|gif|webp)`).

## 6. Limites de payload (importante)

Como as imagens vão **base64 inline**, o payload de `gerar` pode ser grande. Mitigações:
- **Compressão no cliente** (downscale ~1600px, qualidade ~80) — ver [[SPEC_Parecer_Editor_Frontend]] §4.
- `max_length` em `blocos` (40) e `imagens` por bloco (10).
- Validação server-side: rejeitar requisição se soma dos base64 exceder, p.ex., **12 MB**
  (`HTTP 413`), com mensagem amigável orientando reduzir/!comprimir imagens.
- Garantir que o limite de body do servidor (uvicorn/starlette) acomoda o teto definido.

## 7. Critérios de aceite

- [ ] `POST /parecer/custo` retorna custo coerente com nº de imagens
- [ ] `POST /parecer/gerar` cria `ExecucaoFerramenta(ferramenta="parecer_tecnico")`, reserva créditos e enfileira (202)
- [ ] `GET /parecer/execucao/{id}` reflete `pendente→processando→concluida` e devolve `parecer_html`
- [ ] `POST /parecer/{id}/exportar` devolve `.docx` válido e persiste o HTML editado
- [ ] Refund de créditos em falha; confirmação em sucesso
- [ ] Item aparece no Histórico; isolamento por usuário garantido
