# SPEC — Inlinks: remover aprendizado/penalização + corrigir bugs do reranker e revisor

**Status:** pendente · **Escopo:** backend + frontend + 1 migration · **Crédito:** não muda · **Depende de:** `SPEC_Inlinks_Arquitetura_IA.md` + `SPEC_Inlinks_Refinamentos_UX.md` aplicadas

## 1. Resumo

Quatro entregas:

- **A.** Remover totalmente o subsistema de aprendizado/penalização (tabela, modelo, service, rotas, schemas, tipos, UI).
- **B.** Reduzir threshold default no formulário de 0.78 para 0.65.
- **C.** Revisor ignora `sugestao_manual` (não envia ao LLM, não sobrescreve status).
- **D.** Migration 0009 limpa o DB (drop tabela + drop colunas humanas).

Total: 1 migration nova, 5 arquivos backend alterados, 2 arquivos backend deletados, 4 arquivos frontend alterados.

### Por que esta SPEC

O E2E da SPEC anterior expôs três problemas:

1. **Reranker filtra demais.** O cálculo `score_total = 0.6·sem + 0.3·ctx + bonus − penalização` consome `inlinks_historico_performance` via `_carregar_ajustes_historico` em `reranker.py:62`. Com poucas dezenas de execuções, a penalização (até −0.30) derruba scores abaixo do threshold default 0.78. **A "densidade dinâmica" (4-5 inlinks/1000 palavras) vira teatro** porque o gargalo está no reranker, não no inseridor. Confirmado em laboratório: após `DELETE FROM inlinks_historico_performance`, candidatos voltam a passar.

2. **Revisor sobrescreve `sugestao_manual` → `aplicado`.** Em `revisor.py:52` o status é setado cegamente pelo retorno do LLM revisor. Quando o inseridor marcou um item como `sugestao_manual` (porque o trecho não foi achado no parágrafo proposto pelo LLM), o revisor pode reclassificá-lo como `aplicado` — só que o link **não está** no markdown. UI fica enganosa: "1 inlink aplicado" sem link real.

3. **Aprendizado prematuro.** A SPEC v1 listou histórico/penalização como fora de escopo, mas o reranker já consumia esses dados desde a aplicação. Para evitar regressão silenciosa futura, **remover o subsistema inteiro** (tabela `inlinks_historico_performance`, modelo `InlinkPerformance`, service, dois endpoints, schemas, tipos frontend, botões 👍/👎). Reintroduzir aprendizado virá numa SPEC explícita no futuro.

## 2. Entrega A — Remover aprendizado/penalização

### A.1 Arquivos a deletar

- `backend/app/services/inlink_performance_service.py`
- `backend/app/models/inlink_performance.py`

### A.2 Backend — `backend/app/agents/inlinks/reranker.py`

Substituir o bloco de cálculo de score (linhas 62-76) por versão sem histórico:

```python
# ANTES:
ajustes = await _carregar_ajustes_historico(
    usuario_id, [c.get("url_canonica", c.get("url", "")) for c in candidatos]
)

for c in candidatos:
    url_key = c.get("url_canonica", c.get("url", ""))
    bonus, penalizacao = ajustes.get(url_key, (0.0, 0.0))
    c["score_bonus_historico"] = bonus
    c["score_penalizacao_historico"] = penalizacao
    c["score_total"] = float(
        0.6 * float(c.get("score_semantico", 0))
        + 0.3 * float(c.get("score_contexto", 0))
        + bonus
        - penalizacao
    )

# DEPOIS:
for c in candidatos:
    c["score_total"] = float(
        0.6 * float(c.get("score_semantico", 0))
        + 0.3 * float(c.get("score_contexto", 0))
    )
```

Remover a função inteira `_carregar_ajustes_historico` (linhas 82-106).

Arquivo final fica com: `rerank_candidatos` + `_RerankerAgent` + `_parse_rankings` apenas.

### A.3 Backend — `backend/app/agents/workflow_inlinks.py`

Em `node_persistir` (linhas ~626-638), **remover o bloco inteiro** de `registrar_evento`:

```python
# REMOVER:
evento = "aplicado" if il.get("status") == "aplicado" else "rejeitado_revisor"
await inlink_performance_service.registrar_evento(
    session,
    usuario_id=estado["usuario_id"],
    url_destino=il["url_destino"],
    evento=evento,
    motivo=il.get("motivo_rejeicao"),
    execucao_id=eid,
    metadata={
        "score_total": float(il.get("score_total", 0)),
        "anchor_text": il.get("anchor_text"),
    },
)
```

E remover o import `from app.services import inlink_performance_service` do escopo do nó.

### A.4 Backend — `backend/app/routers/ferramentas_inlinks.py`

Remover **dois endpoints inteiros**:

1. `POST /inlinks-automaticos/{execucao_id}/performance` (linhas 88-130).
2. `POST /historico/{execucao_id}/inlinks/{inlink_id}/feedback` (linhas 133-178).

Remover imports correspondentes do topo do arquivo:
- `from app.schemas.inlinks import ..., InlinkFeedbackRequest, PerformanceFeedbackRequest`
- `from app.services import inlink_performance_service` (se for o único uso)

### A.5 Backend — `backend/app/schemas/inlinks.py`

Remover classes inteiras:

```python
# REMOVER linhas 76-78:
class InlinkFeedbackRequest(BaseModel):
    decisao: Literal["aprovado", "rejeitado"]
    motivo: str | None = Field(default=None, max_length=500)

# REMOVER linhas 81-93:
class PerformanceFeedbackRequest(BaseModel):
    ...
```

Em `InlinkSugeridoResponse` (linhas 51-73), remover os 3 campos de feedback humano:

```python
# REMOVER:
status_humano: str | None = None
motivo_humano: str | None = None
revisado_humano_em: datetime | None = None
```

Se sobrar import não utilizado de `Literal` ou `datetime`, limpar.

### A.6 Backend — `backend/app/models/inlink_sugerido.py`

Remover linhas 32-34 (campos de feedback humano):

```python
# REMOVER:
status_humano: Mapped[str | None] = mapped_column(String(20), nullable=True)
motivo_humano: Mapped[str | None] = mapped_column(Text, nullable=True)
revisado_humano_em: Mapped[datetime | None] = mapped_column(nullable=True)
```

**Manter** os campos `trecho_original`, `conector_antes`, `conector_depois` — não são relacionados a aprendizado.

### A.7 Frontend — `frontend/src/types/ferramenta.ts`

Em `InlinkAplicado` (linhas 90-112), remover:

```ts
status_humano?: "aprovado_humano" | "rejeitado_humano" | null;
motivo_humano?: string | null;
revisado_humano_em?: string | null;
```

Manter `id?: string` (usado em outras partes da UI).

### A.8 Frontend — `frontend/src/lib/api.ts`

Remover função `enviarFeedbackInlink` (linhas 146-156) inteira.

### A.9 Frontend — `frontend/src/components/ferramentas/inlinks-resultado.tsx`

Componente fica significativamente menor. Remover:

- `import { Button } from "@/components/ui/button"` — só se não usar em outro botão. Verificar antes.
- `import { toast } from "sonner"` — só se não usar.
- `import { enviarFeedbackInlink } from "@/lib/api"` — sempre remover.
- `import { useState } from "react"` — manter se outro `useState` ficar.
- Estado `feedbackState` e função `getStatusHumano` (linhas ~68, 78-81).
- Funções `handleAprovar`, `handleRejeitar` (linhas 83-106).
- Prop `execucaoId?: string` da interface `Props` e da função `InlinksResultado`.
- Variáveis `humano`, `aprovadoHumano`, `rejeitadoHumano`, `podeFeedback` (linhas ~135-138).
- Classes condicionais `aprovadoHumano && "border-success/30"`, `rejeitadoHumano && "opacity-60"`, e `rejeitadoHumano && "line-through"` no `<li>`.
- Badges "Aprovado" e "Rejeitado por você" (linhas ~171-176).
- Bloco final de botões 👍 Aprovar / 👎 Rejeitar (linhas ~239-261) inteiro.

### A.10 Frontend — `frontend/src/components/ferramentas/execucao-detalhe-conteudo.tsx`

Linha 321: remover prop `execucaoId={id}` do `<InlinksResultado />`. A prop não existe mais no componente.

## 3. Entrega B — Threshold default 0.65

### `frontend/src/components/ferramentas/formulario-inlinks.tsx`

Localizar o estado do threshold (provavelmente `useState(0.78)` ou similar). Trocar default para `0.65`.

Se existir texto de ajuda mencionando "0.78", atualizar para "0.65".

A UI já tem `<spinbutton>` para `Score mínimo` — só o default que muda.

## 4. Entrega C — Revisor ignora `sugestao_manual`

### `backend/app/agents/inlinks/revisor.py`

Substituir `revisar_inlinks` (linhas 9-63) por:

```python
async def revisar_inlinks(
    pilar_original: str,
    pilar_modificado: str,
    inlinks: list[dict],
    usuario_id: str,
) -> list[dict]:
    if not inlinks:
        return inlinks

    # sugestao_manual nunca foi inserida no texto: não passa pelo revisor LLM.
    inlinks_revisaveis = [
        il for il in inlinks if il.get("status") != "sugestao_manual"
    ]

    if not inlinks_revisaveis:
        return inlinks

    agente = _RevisorAgent(usuario_id)

    lista = ""
    for i, il in enumerate(inlinks_revisaveis):
        lista += (
            f"\n{i+1}. URL: {il['url_destino']}\n"
            f"   Âncora: {il['anchor_text']}\n"
            f"   Parágrafo: {il['paragrafo_idx']}\n"
            f"   Score: {il.get('score_total', 0):.2f}"
        )

    prompt = f"""Você é um revisor de SEO. Verifique se os inlinks abaixo foram aplicados corretamente no texto.

REGRAS:
- Max 1 inlink por 200 palavras
- Distância mínima de 100 palavras entre inlinks
- Âncoras devem soar naturais
- O sentido do texto original deve ser preservado
- Max 8 inlinks total

INLINKS APLICADOS:
{lista}

TRECHO DO TEXTO MODIFICADO:
{pilar_modificado[:4000]}

Responda APENAS com JSON:
{{"revisao": [{{"indice": 1, "status": "aplicado", "motivo": ""}}, {{"indice": 2, "status": "rejeitado_revisor", "motivo": "âncora soa artificial"}}]}}

Status possíveis: "aplicado" ou "rejeitado_revisor"."""

    try:
        resultado = await agente._invoke_llm(prompt)
        revisao = _parse_revisao(resultado)
        for i, il in enumerate(inlinks_revisaveis):
            idx = i + 1
            if idx in revisao:
                r = revisao[idx]
                il["status"] = r.get("status", "aplicado")
                il["motivo_rejeicao"] = r.get("motivo", None)
            else:
                il["status"] = "aplicado"
                il["motivo_rejeicao"] = None
    except Exception as e:
        logger.warning("Revisor LLM falhou, mantendo todos aplicados: %s", e)
        for il in inlinks_revisaveis:
            il["status"] = "aplicado"
            il["motivo_rejeicao"] = None

    # Retorna a lista ORIGINAL (inclui os sugestao_manual intactos).
    return inlinks
```

Pontos-chave:

- `inlinks_revisaveis` é uma lista filtrada (não cópia profunda dos dicts; são as mesmas referências). Modificações via `il["status"] = ...` afetam os dicts originais.
- Os itens com `status == "sugestao_manual"` nunca são tocados.
- Index na string `lista` é `i+1` baseado em `inlinks_revisaveis`, não em `inlinks` total — evita bugs.
- A função final retorna `inlinks` (lista original com sugestao_manual preservados na posição original).

## 5. Entrega D — Migration 0009

### Arquivo novo `backend/migrations/versions/0009_remover_aprendizado.py`

```python
"""remover sistema de aprendizado/penalizacao

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-11
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("inlinks_historico_performance")
    op.drop_column("inlinks_sugeridos", "status_humano")
    op.drop_column("inlinks_sugeridos", "motivo_humano")
    op.drop_column("inlinks_sugeridos", "revisado_humano_em")


def downgrade() -> None:
    op.add_column(
        "inlinks_sugeridos",
        sa.Column("status_humano", sa.String(20), nullable=True),
    )
    op.add_column(
        "inlinks_sugeridos",
        sa.Column("motivo_humano", sa.Text(), nullable=True),
    )
    op.add_column(
        "inlinks_sugeridos",
        sa.Column("revisado_humano_em", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "inlinks_historico_performance",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "usuario_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url_destino", sa.Text, nullable=False),
        sa.Column("evento", sa.String(30), nullable=False),
        sa.Column("motivo", sa.Text, nullable=True),
        sa.Column(
            "execucao_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("metadata_json", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
```

Nota: o `downgrade` recria a tabela vazia. Não há rollback de dados (apagados no `upgrade`). Aceitável neste estágio do projeto.

## 6. Verificação ponta a ponta

### Migration

```bash
cd backend && alembic upgrade head
```

Validar no psql:
- `\d inlinks_sugeridos` → não tem `status_humano`, `motivo_humano`, `revisado_humano_em`.
- `\dt inlinks_historico_performance` → tabela não existe.

### Sanidade de import

```bash
cd /Users/yan/Documents/GitHub/Python-Sass2
grep -rEn "inlink_performance_service|InlinkPerformance|PerformanceFeedbackRequest|InlinkFeedbackRequest|enviarFeedbackInlink|_carregar_ajustes_historico|score_bonus_historico|score_penalizacao_historico|status_humano|motivo_humano|revisado_humano_em" backend/app frontend/src
```

Deve retornar **vazio**.

### Restart serviços

```bash
pkill -f "uvicorn app.main"; pkill -f "arq app.worker"; sleep 2
cd backend && nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
cd backend && nohup python3 -m arq app.worker.WorkerSettings > /tmp/arq.log 2>&1 &
```

### Build frontend

```bash
cd frontend && npm run build && cp -r out/* ../backend/static/
```

### Execução de teste

URL pilar: `https://www.hashtagtreinamentos.com/programacao-para-iniciantes-prog`
Candidatas:
- `https://www.hashtagtreinamentos.com/curriculo-programacao`
- `https://www.hashtagtreinamentos.com/roadmap-programacao`
- `https://www.hashtagtreinamentos.com/melhor-linguagem-de-programacao-iniciantes`

**Esperado:**
- Form mostra `Score mínimo: 0.65` (default).
- `n_candidatas_validas: 3`.
- `n_aplicadas ≥ 3` (sem penalização, todas as URLs passam o reranker porque cosine ~0.99).
- Densidade respeitada: pilar de ~1900 palavras → 4-9 inlinks.
- Se alguma inserção propôs trecho inexistente no parágrafo, vira `sugestao_manual`. Esse item permanece como `sugestao_manual` no final (revisor não toca).
- UI do detalhe: sem botões 👍/👎, sem badges "Aprovado por você"/"Rejeitado por você". Apenas badges de categoria (`Conexão forte/sólida/indireta/fraca`) e badges de sistema (`Sugestão manual`, `Rejeitado pelo revisor`).

## 7. Fora de escopo

- Tunar os pesos `0.6` (semântico) e `0.3` (contexto) — mantém atual; soma 0.9, o restante é "headroom" que ficou implícito.
- Adicionar telemetria de CTR via UTM/pixel — descartado.
- Reintroduzir qualquer forma de aprendizado — não há plano. Uma reintrodução futura precisaria de SPEC dedicada.

## 8. Riscos e mitigações

- **`downgrade` da migration recria tabela vazia.** Aceitável em dev/teste; em produção real seria perda de histórico irreversível. Não há produção atualmente.
- **Imports `Button` ou `toast` ainda usados no `inlinks-resultado.tsx`:** verificar antes de deletar para não quebrar build. O componente ainda tem badges e cards — pode precisar dos imports.
- **Lista vazia após filtrar `sugestao_manual` no revisor:** tratado pelo early-return `if not inlinks_revisaveis: return inlinks`.
- **Outros componentes/páginas referenciando símbolos removidos:** o grep da seção 6 detecta antes do build.
- **Cache de pyc:** ao reiniciar serviços, limpar `find backend -name __pycache__ -exec rm -rf {} +` se houver comportamento inesperado.
