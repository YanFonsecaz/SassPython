# SPEC — Inlinks: arquitetura totalmente IA (v1, sem treino)

**Status:** pendente · **Escopo:** backend + frontend + 1 migration · **Crédito:** não muda

## 1. Resumo

Cinco entregas:

- **A.** Cleaner agent — refina markdown da Trafilatura via LLM.
- **B.** Enriquecedor de metadados — gera `{tipo, categoria, intenção, palavras_chave, entidades, resumo}` por URL e persiste em `conteudos_vetores`.
- **C.** Persistência + reuso de embeddings em `pgvector` — `node_enriquecer` consulta antes de recomputar.
- **D.** Agente inseridor semântico — substitui `injector.py` regex. Decide onde inserir, escolhe âncora, adiciona conector opcional (1-3 palavras), respeita restrições mecânicas.
- **E.** Botões humanos de aprovar/rejeitar — UI + endpoint + persistência (sem treinar).

Total: 1 migration (campos em `inlinks_sugeridos`), 6 arquivos backend novos/alterados, 3 arquivos frontend.

**Fora de escopo (v2):** `histórico_performance` e `penalização_por_rejeição` aplicados ao score. Esta v1 só **coleta** o sinal humano; o reranker continua usando apenas `score_semantico + score_contexto`.

## 2. Entrega A — Cleaner agent

**Arquivo novo:** `backend/app/agents/inlinks/cleaner.py`

Estende `BaseAgent` (`backend/app/agents/base.py`). Recebe markdown da Trafilatura, retorna markdown refinado.

### Estrutura

```python
import json
import logging

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


async def limpar_conteudo(markdown: str, usuario_id: str) -> str:
    """Refina markdown da Trafilatura. Em caso de erro, retorna o original."""
    if not markdown or not markdown.strip():
        return markdown

    agente = _CleanerAgent(usuario_id)
    prompt = _build_prompt(markdown)
    try:
        resposta = await agente._invoke_llm(prompt)
        limpo = _parse(resposta)
        return limpo or markdown
    except Exception as e:
        logger.warning("Cleaner falhou, usando markdown original: %s", e)
        return markdown


class _CleanerAgent(BaseAgent):
    async def _invoke_llm(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.content
```

### Prompt

```
Você é um editor de conteúdo focado em SEO. Recebe um markdown extraído
de uma página web e devolve uma versão refinada.

REGRAS (sem reescrever o conteúdo):
1. Remova blocos finais do tipo "Leia também", "Veja também",
   "Posts relacionados", "Compartilhe", "Sobre o autor".
2. Remova listas de links que não fazem parte do corpo principal
   (geralmente no fim do artigo).
3. Normalize headings: sem H1 duplicado; remova linhas com apenas
   `#`, `##`, `###` sem texto.
4. NÃO invente texto. NÃO reescreva parágrafos. NÃO mude a ordem.
5. NÃO remova H2/H3 do corpo principal; só remova ruído explícito.
6. Mantenha listas, blocos de código e citações intactos.

Saída APENAS em JSON:
{"markdown_limpo": "..."}

Markdown original:
<<<
{markdown}
>>>
```

### Integração

Novo nó `node_limpar_conteudo` antes de `enriquecer` em `workflow_inlinks.py`. Para o pilar e cada candidata com sucesso, passa `conteudo_md` pelo cleaner e atualiza no estado.

Quando uma URL já tem registro em `conteudos_vetores` com `html_hash` igual (ver Entrega C), pulamos o cleaner (resultado já está no DB).

### Fallback

Sem JSON válido na resposta, retorna o markdown original. Não bloqueia o fluxo.

## 3. Entrega B — Enriquecedor de metadados

**Arquivo novo:** `backend/app/agents/inlinks/enriquecedor_metadados.py`

### Estrutura

```python
import json
import logging
from dataclasses import dataclass

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class MetadadosConteudo:
    tipo: str          # "blog" | "produto" | "categoria" | "landing" | "tutorial"
    categoria: str
    intencao: str      # "informacional" | "comercial" | "transacional" | "navegacional"
    palavras_chave: list[str]
    entidades: list[str]
    resumo: str


async def enriquecer_metadados(
    markdown: str, titulo: str, usuario_id: str
) -> MetadadosConteudo:
    """Gera metadados estruturados de uma URL. Fallback retorna metadados vazios."""
    agente = _EnriquecedorAgent(usuario_id)
    prompt = _build_prompt(markdown, titulo)
    try:
        resposta = await agente._invoke_llm(prompt)
        data = _parse(resposta)
        return MetadadosConteudo(
            tipo=data.get("tipo", "blog"),
            categoria=data.get("categoria", ""),
            intencao=data.get("intencao", "informacional"),
            palavras_chave=data.get("palavras_chave", []) or [],
            entidades=data.get("entidades", []) or [],
            resumo=data.get("resumo", ""),
        )
    except Exception as e:
        logger.warning("Enriquecedor falhou: %s", e)
        return MetadadosConteudo(
            tipo="blog", categoria="", intencao="informacional",
            palavras_chave=[], entidades=[], resumo="",
        )
```

### Prompt

```
Você é um analista de conteúdo SEO. Recebe título e markdown de uma
página e produz metadados estruturados.

REGRAS:
- tipo: um de [blog, produto, categoria, landing, tutorial].
- intencao: um de [informacional, comercial, transacional, navegacional].
- categoria: tema principal em 1-3 palavras (ex.: "Programação iniciante").
- palavras_chave: 5-10 termos centrais do texto (substantivos, não verbos).
- entidades: nomes próprios, ferramentas, tecnologias, frameworks
  mencionados (até 10).
- resumo: 2-3 frases sobre o que a página oferece ao leitor.

Saída APENAS em JSON:
{
  "tipo": "blog",
  "categoria": "...",
  "intencao": "informacional",
  "palavras_chave": ["..."],
  "entidades": ["..."],
  "resumo": "..."
}

Título: {titulo}

Markdown:
<<<
{markdown_truncado_8000}
>>>
```

### Mapeamento para `conteudos_vetores`

Colunas em `backend/app/models/conteudo_vetor.py` (linhas 25-28): `tipo`, `intencao`, `palavras_chave`, `atividades`.

- `tipo` → `tipo` (direto).
- `intencao` → `intencao` (direto).
- `palavras_chave` → `palavras_chave` (JSONB).
- `entidades` → **mapear para `atividades`** (reusa a coluna JSONB existente; não cria migration).
- `categoria` e `resumo` — sem coluna dedicada. Mantém no dict em memória passado pelo workflow para o reranker e o inseridor.

## 4. Entrega C — Persistência + reuso em pgvector

**Arquivo alterado:** `backend/app/agents/workflow_inlinks.py`, `node_enriquecer` (linhas 160-216).

### Fluxo novo

Para o pilar e cada candidata extraída com sucesso:

1. Calcular `html_hash` (já existe nos resultados do scraper).

2. Consultar:
   ```python
   from sqlalchemy import select
   from app.models.conteudo_vetor import ConteudoVetor

   stmt = (
       select(ConteudoVetor)
       .where(
           ConteudoVetor.usuario_id == usuario_id,
           ConteudoVetor.url_canonica == url_canonica,
           ConteudoVetor.html_hash == html_hash,
           ConteudoVetor.ativo == True,
       )
       .order_by(ConteudoVetor.chunk_index)
   )
   ```

   Se retornar linhas: **reusa**.
   - `embedding` por chunk vem do DB.
   - Metadados (`tipo`, `intencao`, `palavras_chave`, `atividades`) vêm do DB.
   - Pula cleaner + enriquecedor + embedding (economia grande em runs warm).

3. Se vazio (cold):
   - Roda `limpar_conteudo` (Entrega A) → `markdown_limpo`.
   - `chunks = chunk_texto(markdown_limpo)` (reusa `app.core.chunker`).
   - Roda `enriquecer_metadados` (Entrega B) **uma vez por URL** com o markdown completo.
   - `embeddings = await gerar_embeddings_batch([c.texto for c in chunks], usuario_id)`.
   - Persiste cada chunk em `conteudos_vetores`:
     ```python
     for chunk, emb in zip(chunks, embeddings):
         if emb is None:
             continue
         session.add(ConteudoVetor(
             usuario_id=usuario_id,
             cliente_id=cliente_id,  # se houver
             execucao_id=execucao_id,
             titulo=titulo,
             conteudo=chunk.texto,
             tipo=meta.tipo,
             intencao=meta.intencao,
             palavras_chave=meta.palavras_chave,
             atividades=meta.entidades,
             embedding=emb,
             url_canonica=url_canonica,
             chunk_index=chunk.ordem,
             tipo_recurso="pilar" if is_pilar else "candidata",
             html_hash=html_hash,
             tokens=chunk.tokens,
             score_base=0.0,
             ativo=True,
         ))
     await session.commit()
     ```

4. Estado retornado no fim de `node_enriquecer`:
   - `pilar_embedding`: embedding do primeiro chunk do pilar (ou média dos chunks — manter como hoje, primeiro chunk).
   - `candidatas_embeddings`: lista de dicts mantendo a forma atual `{url, url_canonica, titulo, ordem, embedding}` **acrescida de** `tipo`, `intencao`, `palavras_chave`, `entidades`, `resumo`, `categoria` (para uso pelo reranker e inseridor).
   - `pilar_metadados`: dict com metadados do pilar (passado para o inseridor para contexto).

5. Eventos via `publish_event`:
   - Cold: `"Gerando embeddings + metadados (cold) para N URLs"`.
   - Warm parcial: `"Reuso de N URLs do banco vetorial, M URLs novas"`.
   - Warm total: `"Reuso completo: N URLs do banco vetorial"`.

### Considerações de concorrência

O `INSERT` é dentro do mesmo `async with async_session_factory()` do nó. Se duas execuções simultâneas tentarem inserir o mesmo `(usuario_id, url_canonica, chunk_index)`, o índice único existente (migration 0005 linha 27) bloqueia a segunda — capture `IntegrityError` e relê do DB.

## 5. Entrega D — Agente inseridor semântico

**Arquivo novo:** `backend/app/agents/inlinks/inseridor.py`

**Arquivo deprecated mas mantido como helper utilitário:** `backend/app/agents/inlinks/injector.py` — `_strip_accents`, `_esta_em_cabecalho` e `remover_links_rejeitados` continuam usados; `injetar_inlinks` deixa de ser chamado pelo workflow mas pode permanecer no arquivo até v2.

### Função principal

```python
import json
import logging
import re
from dataclasses import dataclass

from app.agents.base import BaseAgent
from app.agents.inlinks.injector import _esta_em_cabecalho, _strip_accents

logger = logging.getLogger(__name__)

_MIN_DISTANCE_WORDS = 100
_MAX_CONECTOR_WORDS = 3
_MAX_PILAR_CHARS = 30000


@dataclass
class InlinkInserido:
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
    motivo_sugestao: str | None = None
    trecho_original: str | None = None
    conector_antes: str | None = None
    conector_depois: str | None = None


async def inserir_inlinks(
    pilar_markdown: str,
    candidatos: list[dict],
    usuario_id: str,
    max_inlinks: int = 8,
) -> tuple[str, list[InlinkInserido]]:
    if not pilar_markdown.strip() or not candidatos:
        return pilar_markdown, []

    paragrafos = pilar_markdown.split("\n\n")
    pilar_numerado = _numerar_paragrafos(paragrafos)
    candidatos_top = sorted(
        candidatos, key=lambda c: c.get("score_total", 0), reverse=True
    )[:max_inlinks]

    agente = _InseridorAgent(usuario_id)
    prompt = _build_prompt(pilar_numerado[:_MAX_PILAR_CHARS], candidatos_top, max_inlinks)

    try:
        resposta = await agente._invoke_llm(prompt)
        insercoes_raw = _parse(resposta)
    except Exception as e:
        logger.warning("Inseridor LLM falhou: %s", e)
        insercoes_raw = []

    return _aplicar_insercoes(pilar_markdown, paragrafos, candidatos_top, insercoes_raw)
```

### Prompt

```
Você é um especialista em SEO e linkagem interna. Recebe um artigo
pilar (com parágrafos numerados [P0], [P1], ...) e uma lista de URLs
candidatas. Decide onde inserir cada link.

ARTIGO PILAR:
{pilar_numerado}

CANDIDATAS:
{lista de candidatas com índice, URL, título, resumo}

REGRAS DE INSERÇÃO (em ordem de prioridade):
1. Escolha o parágrafo cujo TEMA bate com o destino. Não escolha um
   parágrafo só porque a palavra aparece — escolha onde o leitor
   estaria interessado em aprofundar sobre o destino.
2. `trecho_original`: 2-5 palavras CONTÍNUAS, COPIADAS LITERALMENTE
   do parágrafo escolhido. Preserve acentos, capitalização, pontuação
   interna.
3. `anchor_text`: por padrão, igual ao `trecho_original`. Se uma
   reformulação MÍNIMA tornar a âncora mais natural (ex.: trocar
   "linguagens iniciantes" por "linguagem para iniciantes"), pode usar.
4. Conectores opcionais para fluidez (`conector_antes`,
   `conector_depois`): até 3 palavras cada, fora da âncora. Exemplo:
   âncora "currículo de programador" + conector_depois ", que mostre
   habilidades reais". Use só quando o trecho original ficar travado
   sem o conector.
5. PROIBIDO inserir em: cabeçalhos (linhas iniciadas por #), itens de
   lista (linhas começando com -, *, 1.), blocos de código.
6. Distância mínima de 100 palavras entre dois inlinks.
7. Distribua ao longo do pilar — não concentre tudo no início.
8. Vazio é aceitável: se nenhum parágrafo serve para um destino,
   omita o candidato.

Saída APENAS em JSON:
{
  "insercoes": [
    {
      "url_destino": "https://...",
      "paragrafo_idx": 5,
      "trecho_original": "linguagem para iniciantes",
      "anchor_text": "linguagem para iniciantes",
      "conector_antes": "",
      "conector_depois": ", como exploramos a seguir",
      "justificativa": "..."
    }
  ]
}
```

### Pós-processamento (código)

Para cada inserção retornada pelo LLM:

1. **Validar `paragrafo_idx`** está dentro do array de parágrafos.
2. **Validar não é cabeçalho/lista/código:** `_esta_em_cabecalho(pilar, offset_inicio_paragrafo)` ou regex para listas e fenced code.
3. **Validar `trecho_original` existe no parágrafo:** busca tolerante a acentos via `_strip_accents` (já em `injector.py:56`). Se não encontra → `sugestao_manual` com motivo `"Trecho indicado não foi encontrado no parágrafo."`.
4. **Validar conectores ≤ 3 palavras:** `len(conector.split()) <= 3`. Acima disso, trunca para 3 palavras.
5. **Validar distância:** offset_chars da inserção, calcular distância em palavras vs inserções já aceitas. Se < 100 palavras → `sugestao_manual` com motivo `"Muito próximo de outro inlink."`.

### Aplicação no markdown

Para inserções válidas, ordenadas por `offset_chars` decrescente:

```python
texto_novo = f"{conector_antes}[{anchor_text}]({url}){conector_depois}"
pilar = pilar[:offset] + texto_novo + pilar[offset + len(trecho_original):]
```

Decrescente para não invalidar offsets das outras inserções.

### Helpers a expor

`injector.py` deve exportar publicamente:
- `_strip_accents` → `strip_accents`
- `_esta_em_cabecalho` → `esta_em_cabecalho`
- Manter os nomes antigos como aliases por compatibilidade.

### Substituição no workflow

Em `workflow_inlinks.py`:

```python
# REMOVER: node_gerar_ancoras e node_injetar
# ADICIONAR:
async def node_inserir(estado: EstadoInlinks) -> dict:
    from app.agents.inlinks.inseridor import inserir_inlinks
    from app.core.workflow_events import publish_event

    eid = estado["execucao_id"]
    await publish_event(eid, "node_start", "inserir", "Inserindo inlinks no texto...")

    pilar_md = estado.get("pilar_resultado", {}).get("conteudo_md", "")
    candidatos = estado.get("candidatos_reranked", [])
    max_inlinks = estado.get("max_inlinks", 8)

    pilar_modificado, inseridos = await inserir_inlinks(
        pilar_md, candidatos, estado["usuario_id"], max_inlinks=max_inlinks
    )

    inlinks_dicts = [_inserido_to_dict(ij) for ij in inseridos]
    await publish_event(eid, "node_complete", "inserir", f"{len(inseridos)} inlinks inseridos")
    return {
        "pilar_modificado": pilar_modificado,
        "inlinks_aplicados": inlinks_dicts,
    }
```

E nas edges:
```python
workflow.add_edge("match_rerank", "inserir")  # antes: match_rerank → gerar_ancoras
workflow.add_edge("inserir", "revisar")        # antes: injetar → revisar
```

`node_persistir` precisa ler também `trecho_original`, `conector_antes`, `conector_depois` do dict e gravar nas colunas novas (Entrega E).

## 6. Entrega E — Botões humanos de aprovar/rejeitar

### Migration `0008_inlinks_feedback_humano.py`

```python
"""inlinks feedback humano + conectores

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inlinks_sugeridos", sa.Column("status_humano", sa.String(20), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("motivo_humano", sa.Text(), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("revisado_humano_em", sa.DateTime(), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("trecho_original", sa.Text(), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("conector_antes", sa.String(80), nullable=True))
    op.add_column("inlinks_sugeridos", sa.Column("conector_depois", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("inlinks_sugeridos", "conector_depois")
    op.drop_column("inlinks_sugeridos", "conector_antes")
    op.drop_column("inlinks_sugeridos", "trecho_original")
    op.drop_column("inlinks_sugeridos", "revisado_humano_em")
    op.drop_column("inlinks_sugeridos", "motivo_humano")
    op.drop_column("inlinks_sugeridos", "status_humano")
```

### Modelo

Em `backend/app/models/inlink_sugerido.py`, adicionar:

```python
status_humano: Mapped[str | None] = mapped_column(String(20), nullable=True)
motivo_humano: Mapped[str | None] = mapped_column(Text, nullable=True)
revisado_humano_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
trecho_original: Mapped[str | None] = mapped_column(Text, nullable=True)
conector_antes: Mapped[str | None] = mapped_column(String(80), nullable=True)
conector_depois: Mapped[str | None] = mapped_column(String(80), nullable=True)
```

### Endpoint

`POST /ferramentas/historico/{execucao_id}/inlinks/{inlink_id}/feedback`

Body:
```json
{ "decisao": "aprovado" | "rejeitado", "motivo": "opcional" }
```

Arquivo: `backend/app/api/routes/ferramentas.py`.

```python
@router.post("/historico/{execucao_id}/inlinks/{inlink_id}/feedback")
async def feedback_inlink(
    execucao_id: UUID,
    inlink_id: UUID,
    body: InlinkFeedbackRequest,
    usuario: UsuarioAutenticado,
    db: AsyncSession,
):
    from datetime import datetime
    from app.models.inlink_sugerido import InlinkSugerido
    from app.models.execucao_ferramenta import ExecucaoFerramenta
    from app.services import inlink_performance_service

    stmt = (
        select(InlinkSugerido)
        .join(ExecucaoFerramenta, ExecucaoFerramenta.id == InlinkSugerido.execucao_id)
        .where(
            InlinkSugerido.id == inlink_id,
            InlinkSugerido.execucao_id == execucao_id,
            ExecucaoFerramenta.usuario_id == usuario.id,
        )
    )
    inlink = (await db.execute(stmt)).scalar_one_or_none()
    if not inlink:
        raise HTTPException(404, "Inlink não encontrado")

    novo_status = "aprovado_humano" if body.decisao == "aprovado" else "rejeitado_humano"
    inlink.status_humano = novo_status
    inlink.motivo_humano = body.motivo
    inlink.revisado_humano_em = datetime.utcnow()

    await inlink_performance_service.registrar_evento(
        db,
        usuario_id=str(usuario.id),
        url_destino=inlink.url_destino,
        evento=novo_status,
        motivo=body.motivo,
        execucao_id=str(execucao_id),
        metadata={"anchor_text": inlink.anchor_text, "score_total": inlink.score_total},
    )

    await db.commit()
    return {"status_humano": novo_status, "revisado_em": inlink.revisado_humano_em.isoformat()}
```

**Importante:** o markdown publicado NÃO é alterado. O feedback é só registro.

### Schemas

`backend/app/schemas/inlinks.py`:

```python
from typing import Literal

class InlinkFeedbackRequest(BaseModel):
    decisao: Literal["aprovado", "rejeitado"]
    motivo: str | None = None


# Estender InlinkSugeridoResponse:
class InlinkSugeridoResponse(BaseModel):
    id: UUID  # NOVO — para o frontend identificar no botão de feedback
    # ... campos existentes ...
    status_humano: str | None = None
    motivo_humano: str | None = None
    revisado_humano_em: datetime | None = None
    trecho_original: str | None = None
    conector_antes: str | None = None
    conector_depois: str | None = None
```

E em `node_persistir`, garantir que o `inlinks` em `resultado_final` inclua o `id` recém-criado:

```python
session.add(inlink)
await session.flush()  # garante .id
inlinks_para_resultado.append({
    "id": str(inlink.id),
    # ... resto ...
})
```

### Frontend — tipos

`frontend/src/types/ferramenta.ts`:

```ts
export interface InlinkAplicado {
  id: string;  // NOVO
  // ... existentes ...
  status_humano?: "aprovado_humano" | "rejeitado_humano" | null;
  motivo_humano?: string | null;
  revisado_humano_em?: string | null;
  trecho_original?: string | null;
  conector_antes?: string | null;
  conector_depois?: string | null;
}
```

### Frontend — API

`frontend/src/lib/api.ts` (junto aos outros métodos `api.get`/`api.post`):

```ts
export async function enviarFeedbackInlink(
  execucaoId: string,
  inlinkId: string,
  decisao: "aprovado" | "rejeitado",
  motivo?: string
): Promise<{ status_humano: string; revisado_em: string }> {
  return api.post(
    `/ferramentas/historico/${execucaoId}/inlinks/${inlinkId}/feedback`,
    { decisao, motivo }
  );
}
```

### Frontend — UI

`frontend/src/components/ferramentas/inlinks-resultado.tsx`:

- Adicionar prop `execucaoId: string` ao componente.
- Para cada `<li>` cujo `il.status === "aplicado"` (não rejeitado_revisor, não sugestao_manual), adicionar rodapé:

```tsx
{il.status === "aplicado" && (
  <div className="flex items-center justify-end gap-2 border-t pt-3 mt-3">
    <span className="text-xs text-muted-foreground mr-auto">
      Esse inlink ajuda no seu artigo?
    </span>
    <Button
      size="sm"
      variant={il.status_humano === "aprovado_humano" ? "default" : "outline"}
      onClick={() => handleAprovar(il.id)}
      disabled={il.status_humano === "aprovado_humano"}
    >
      👍 Aprovar
    </Button>
    <Button
      size="sm"
      variant={il.status_humano === "rejeitado_humano" ? "destructive" : "outline"}
      onClick={() => handleRejeitar(il.id)}
    >
      👎 Rejeitar
    </Button>
  </div>
)}
```

`handleRejeitar` abre prompt nativo `window.prompt("Por que está rejeitando?")` ou um dialog do shadcn; passa motivo opcional. POST otimista, rollback com toast em erro.

Estado visual:
- `status_humano === "aprovado_humano"`: borda do card em `border-success/30`.
- `status_humano === "rejeitado_humano"`: card com `opacity-60` e a âncora `line-through`.

Em `execucao-detalhe-conteudo.tsx`, passar `execucaoId={id}` ao `<InlinksResultado />`.

## 7. Verificação ponta a ponta

1. **Migration:**
   ```bash
   cd backend && alembic upgrade head
   ```
   Verificar: `\d inlinks_sugeridos` no psql mostra 6 colunas novas.

2. **Restart serviços:**
   ```bash
   # mata uvicorn + arq worker antigos
   # sobe novos
   ```

3. **Build frontend:**
   ```bash
   cd frontend && npm run build && cp -r out/* ../backend/static/
   ```

4. **Execução 1 (cold)** — submeter inlinks_automaticos com URLs do hashtagtreinamentos.com:
   - DB: `SELECT count(*), tipo, intencao FROM conteudos_vetores WHERE execucao_id = '<eid>' GROUP BY tipo, intencao;` → linhas por URL × chunks, metadados populados.
   - Logs do worker mostram cleaner + enriquecedor sendo chamados por URL.
   - Inserções com `conector_antes`/`conector_depois` aparecem nos logs do inseridor.
   - UI: âncoras evocam o destino (ex.: "currículo de programador" para `/curriculo-programacao`, não "começar a aprender").

5. **Execução 2 (warm) com as MESMAS URLs:**
   - Logs do worker: `"Reuso completo: N URLs do banco vetorial"`.
   - Tempo da etapa enriquecer cai drasticamente (medir antes/depois).
   - Sem novos INSERTs em `conteudos_vetores` para essas URLs.

6. **Botões humanos:**
   - Clicar Aprovar em 1 inlink. F5. Card aparece com borda verde.
   - `SELECT status_humano, motivo_humano FROM inlinks_sugeridos WHERE id='<inlink_id>';` → `aprovado_humano`.
   - Clicar Rejeitar com motivo "Âncora confusa". `motivo_humano` persistido.
   - `SELECT evento, motivo FROM inlinks_historico_performance WHERE url_destino='...' ORDER BY criado_em DESC LIMIT 2;` → dois eventos: `aprovado_humano`, `rejeitado_humano`.

7. **Fallback do inseridor:**
   - Criar pilar onde a única ocorrência da palavra-âncora candidata está num H2.
   - Resultado esperado: inserção vira `sugestao_manual` (badge laranja), workflow não quebra.

8. **Fallback dos agentes:**
   - Simular falha do cleaner (forçar exceção): markdown original deve fluir adiante.
   - Simular falha do enriquecedor: metadados padrão (`tipo="blog"`, listas vazias) salvos.
   - Simular falha do inseridor: lista de inserções vazia, pilar permanece sem links — workflow conclui sem erro.

## 8. Fora de escopo (v2)

- `histórico_performance` aplicado ao score do rerank.
- `penalização_por_rejeição` baixando score de URLs muito rejeitadas pelo humano ou pelo revisor IA.
- Reescrita de parágrafo (esta v1 só permite conectores ≤ 3 palavras).
- Cleaner agressivo (modo "remover seções inteiras").
- Telemetria de CTR real (UTM/pixel).
- Regenerar inlink quando humano rejeita (botão "Refazer este inlink").
- `categoria` e `resumo` persistidos em coluna dedicada de `conteudos_vetores`.
- Limpeza de `conteudos_vetores` órfãos (TTL por `ativo=false` ou `updated_at` antigo).

## 9. Riscos e mitigações

- **Cleaner remove conteúdo legítimo.** Mitigação: prompt conservador (regra 4-5); fallback retorna original em qualquer erro.
- **Inseridor alucina posição.** Mitigação: validação pós-LLM com `strip_accents`; se trecho não existe no parágrafo indicado, vira `sugestao_manual`.
- **Reuso via html_hash:** se Trafilatura mudar versão e gerar hashes diferentes para o mesmo HTML, perde reuso. Aceitável (cold run uma vez).
- **Conectores artificiais.** Mitigação: opcionais no prompt; LLM pode omitir quando o trecho original já flui bem. Pós-processamento trunca em 3 palavras.
- **Custo LLM aumenta** (cleaner + enriquecedor + inseridor = 3 chamadas extras cold). Aceitável: warm pula tudo. Sem mudança de crédito cobrado do cliente (custo absorvido).
- **Botão de rejeição sem efeito visível no SEO:** o markdown publicado não muda. Mitigação: copy clara na UI ("Esse inlink ajuda no seu artigo?") deixando claro que é feedback, não desfazer.
- **Concorrência em `conteudos_vetores`:** duas execuções simultâneas para a mesma URL podem colidir no índice único. Mitigação: capturar `IntegrityError` e relê do DB no nó.
