# SPEC — Dados e Persistência (tabela `parecer` dedicada)

**Status:** a aplicar · **Data:** 2026-05-30
**Escopo:** backend — tabela `parecer` + model SQLAlchemy + migration Alembic + `parecer_persistencia.py` + ajuste dos endpoints
**Reusos:** `app/models/base.py` (`Base`, `UUIDPrimaryKeyMixin`, `TimestampMixin`), padrão de `cwv_persistencia.py`
**Specs irmãs:** [[SPEC_Parecer_Ferramenta]] (lifecycle/rota) · [[SPEC_Parecer_IA_Visao_Multimodal]] (grava o resultado) · [[SPEC_Parecer_Historico_UI]] (consome a listagem)

> **Decisão de melhor resultado (refina [[SPEC_Parecer_Ferramenta]] §2):** em vez de guardar o
> documento só em `ExecucaoFerramenta.resultado_json`, adicionamos uma **tabela `parecer` dedicada**
> — mesmo padrão do CWV (`cwv_analise`). Divisão de responsabilidades:
> - **`execucoes_ferramentas`**: ciclo de vida (status/etapa/timeout), **créditos**, worker, e o
>   **Histórico genérico**. `resultado_json` guarda apenas `{ "parecer_id": "<uuid>" }`.
> - **`parecer`**: o **documento** (estrutura + HTML + metadados) e a base de "Meus Pareceres"
>   (listar, reabrir, re-baixar, versionar no futuro).

## 1. Tabela `parecer` (migration Alembic)

Arquivo novo em `backend/migrations/versions/` (próximo número sequencial), padrão dos demais.

```sql
parecer:
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
  execucao_id     UUID NOT NULL REFERENCES execucoes_ferramentas(id) ON DELETE CASCADE
  cliente_id      UUID NOT NULL REFERENCES clientes(id)
  usuario_id      UUID NOT NULL REFERENCES usuarios(id)

  titulo          TEXT NOT NULL                 -- ex.: "PARECER TÉCNICO — SEO / PERFORMANCE"
  subtitulo       TEXT
  site            TEXT
  plataforma      TEXT                          -- inferida pela IA (pode ser longa); denormalizada p/ listagem
  cliente_nome    TEXT NOT NULL                 -- snapshot do nome do cliente (cabeçalho fiel)

  meta_json       JSONB NOT NULL                -- {subtitulo, escopo_linha} (cabeçalho do parecer)
  estrutura_json  JSONB NOT NULL                -- ParecerEstruturado completo (fonte de verdade)
  parecer_html    TEXT NOT NULL                 -- HTML atual (editado) → fonte do re-download
  n_imagens       INTEGER NOT NULL DEFAULT 0
  modelo          VARCHAR(40)                    -- modelo de redação usado
  status          VARCHAR(20) NOT NULL DEFAULT 'concluido'  -- concluido | falhou
  criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
  atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT now()

INDEX ix_parecer_usuario_cliente_data ON parecer (usuario_id, cliente_id, criado_em DESC);
INDEX ix_parecer_execucao ON parecer (execucao_id);
```

`downgrade()` faz `drop_index` + `drop_table`.

> **Imagens:** as evidências continuam **base64 inline** dentro de `parecer_html`/`estrutura_json`
> (decisão de melhor resultado p/ V1: documento autocontido, sem links quebrados, sem dependência de
> storage). Cada linha fica "pesada" mas o volume é baixo. Caminho de escala (V2): mover imagens p/
> **Supabase Storage** e guardar URLs — ver backlog no README.

## 2. Model (`app/models/parecer.py`, novo)

```python
import uuid
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin

class Parecer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "parecer"

    execucao_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("execucoes_ferramentas.id", ondelete="CASCADE"), nullable=False)
    cliente_id:  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False)
    usuario_id:  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True)

    titulo:        Mapped[str] = mapped_column(Text, nullable=False)
    subtitulo:     Mapped[str | None] = mapped_column(Text)
    site:          Mapped[str | None] = mapped_column(Text)
    plataforma:    Mapped[str | None] = mapped_column(Text)  # IA pode inferir descricao longa
    cliente_nome:  Mapped[str] = mapped_column(Text, nullable=False)

    meta_json:      Mapped[dict] = mapped_column(JSONB, nullable=False)
    estrutura_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    parecer_html:   Mapped[str] = mapped_column(Text, nullable=False)
    n_imagens:      Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    modelo:         Mapped[str | None] = mapped_column(String(40))
    status:         Mapped[str] = mapped_column(String(20), nullable=False, default="concluido")

    __table_args__ = (
        Index("ix_parecer_usuario_cliente_data", "usuario_id", "cliente_id", "criado_em"),
        Index("ix_parecer_execucao", "execucao_id"),
    )
```

Registrar em `app/models/__init__.py` (como os demais models).

## 3. Persistência (`app/services/parecer_persistencia.py`, novo)

```python
from sqlalchemy import select
from app.models.parecer import Parecer

async def criar_parecer(session, *, execucao_id, cliente_id, usuario_id, cliente_nome,
                        estrutura: dict, parecer_html: str, n_imagens: int, modelo: str) -> Parecer:
    meta = estrutura["meta"]
    p = Parecer(
        execucao_id=execucao_id, cliente_id=cliente_id, usuario_id=usuario_id,
        cliente_nome=cliente_nome,
        titulo=estrutura["titulo"], subtitulo=estrutura.get("subtitulo"),
        site=estrutura.get("site"), plataforma=meta.get("plataforma"),
        meta_json=meta, estrutura_json=estrutura, parecer_html=parecer_html,
        n_imagens=n_imagens, modelo=modelo, status="concluido",
    )
    session.add(p); await session.flush()
    return p

async def atualizar_html(session, parecer_id, usuario_id, html: str) -> Parecer | None:
    res = await session.execute(select(Parecer).where(Parecer.id == parecer_id, Parecer.usuario_id == usuario_id))
    p = res.scalar_one_or_none()
    if p: p.parecer_html = html
    return p

async def buscar_parecer(session, parecer_id, usuario_id) -> Parecer | None:
    res = await session.execute(select(Parecer).where(Parecer.id == parecer_id, Parecer.usuario_id == usuario_id))
    return res.scalar_one_or_none()

async def listar_pareceres(session, usuario_id, cliente_id: str | None = None, limite=50, offset=0):
    q = select(Parecer).where(Parecer.usuario_id == usuario_id)
    if cliente_id:
        q = q.where(Parecer.cliente_id == cliente_id)
    q = q.order_by(Parecer.criado_em.desc()).limit(limite).offset(offset)
    res = await session.execute(q)
    return res.scalars().all()
```

## 4. Integração com o fluxo

### 4.1 Worker (ver [[SPEC_Parecer_IA_Visao_Multimodal]] §6) — ao concluir

```python
parecer = await parecer_persistencia.criar_parecer(
    session, execucao_id=execucao_id, cliente_id=ex.cliente_id, usuario_id=ex.usuario_id,
    cliente_nome=entrada["cliente_nome"], estrutura=estrutura.model_dump(),
    parecer_html=parecer_html, n_imagens=len(pares_img), modelo=settings.parecer_documentador_model,
)
await ferramenta_service.atualizar_execucao(
    session, execucao_id, status="concluida", etapa_atual="concluido",
    concluida_em=datetime.now(UTC), resultado_json={"parecer_id": str(parecer.id)},
)
await credito_service.confirmar_debito(session, usuario_id, ex.creditos_cobrados)
```

### 4.2 Endpoints (refina [[SPEC_Parecer_Ferramenta]] §3)

| Endpoint | Muda? | Retorno |
|---|---|---|
| `POST /parecer/gerar` | igual | `{id (execucao), status}` |
| `GET /parecer/execucao/{id}` | **poll de status** | inclui `parecer_id` quando `concluida` |
| `GET /parecer/{parecer_id}` | **novo** | documento: `titulo, parecer_html, estrutura, meta, cliente_nome, criado_em` (filtra por `usuario_id`) |
| `GET /parecer/historico` | **novo** | lista (ver [[SPEC_Parecer_Historico_UI]]) |
| `POST /parecer/{parecer_id}/exportar` | **passa a usar `parecer_id`** | `.docx`; persiste `parecer_html` editado via `atualizar_html` |

Fluxo no front: gera → faz poll por `execucao_id` → ao concluir recebe `parecer_id` → daí em diante
opera por `parecer_id` (abrir/editar/exportar/reabrir do histórico).

## 5. Critérios de aceite

- [ ] Migration cria `parecer` com índices; `downgrade` reverte limpo
- [ ] Worker cria 1 linha `parecer` por execução concluída e guarda `parecer_id` na execução
- [ ] `GET /parecer/{id}` e `GET /parecer/historico` filtram por `usuario_id` (multi-tenant)
- [ ] `exportar` atualiza `parecer_html` e re-download reflete a edição
- [ ] `ON DELETE CASCADE`: remover a execução remove o parecer
