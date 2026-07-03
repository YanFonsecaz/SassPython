"""Testes do julgamento único do inseridor (SPEC_Inlinks_Julgamento_Unico).

Cobre: mapeamento decisão→status, anti-alucinação preservada, retry de densidade,
flag de pisos legado, CTA fallback com título e motivo nunca vazio.
"""
from typing import Any, ClassVar

import pytest

import app.agents.inlinks.inseridor as ins
from app.agents.inlinks.inseridor import DecisaoInsercaoSchema, inserir_inlinks

# 3 parágrafos elegíveis (>80 chars), ~160 palavras no total → min_distance = 50.
PILAR = (
    "A revenda sem estoque vem crescendo entre novos empreendedores no Brasil, "
    "porque reduz o capital inicial e o risco da operacao de comercio digital, "
    "permitindo validar produtos e nichos sem comprar mercadoria antecipadamente, "
    "o que atrai quem esta comecando com pouco dinheiro guardado no banco.\n\n"
    "Outro caminho consistente e a producao de conteudo em blogs e canais de video, "
    "que monetizam por publicidade, afiliacao e produtos proprios ao longo do tempo, "
    "construindo uma audiencia fiel que se torna um ativo duravel do negocio, "
    "embora o retorno financeiro demore mais para aparecer de forma relevante.\n\n"
    "Seja qual for o modelo escolhido, formalize seu empreendimento desde cedo para "
    "emitir nota fiscal, vender para empresas e evitar bloqueios de pagamento, "
    "pois a formalizacao tambem abre acesso a credito bancario mais barato e a "
    "plataformas que exigem cadastro de pessoa juridica para liberar recursos."
)

CANDIDATO = {
    "url": "https://ex.com/loja-virtual",
    "titulo": "Como abrir uma loja virtual (dropshipping)",
    "resumo": "Guia de loja virtual e dropshipping",
    "palavras_chave": ["loja virtual", "dropshipping"],
    "score_total": 0.9,
    "score_semantico": 0.5,
    "score_contexto": 0.9,
}


def _fake_embeddings(monkeypatch):
    async def fake_batch(textos: list[str], usuario_id: str):
        return [[1.0, 0.0] for _ in textos]  # cosine 1.0 entre quaisquer pares

    monkeypatch.setattr(ins, "gerar_embeddings_batch", fake_batch)


class _AgenteFake:
    """Substitui _InseridorAgent; respostas enfileiradas POR URL do prompt."""

    respostas_por_url: ClassVar[dict[str, list[DecisaoInsercaoSchema]]] = {}
    chamadas: ClassVar[int] = 0

    def __init__(self, usuario_id: str):
        pass

    async def invoke_structured(self, prompt: str, schema: Any):
        cls = type(self)
        cls.chamadas += 1
        for url, fila in cls.respostas_por_url.items():
            if url in prompt:
                return fila.pop(0) if len(fila) > 1 else fila[0]
        raise AssertionError("prompt sem URL conhecida")

    async def _invoke_llm(self, prompt: str) -> str:
        raise AssertionError("fallback não deveria ser usado nos testes")


@pytest.fixture(autouse=True)
def _reset_agente(monkeypatch):
    _AgenteFake.respostas_por_url = {}
    _AgenteFake.chamadas = 0
    monkeypatch.setattr(ins, "_InseridorAgent", _AgenteFake)


async def test_decisao_aplicar_vira_aplicado(monkeypatch):
    _fake_embeddings(monkeypatch)
    _AgenteFake.respostas_por_url = {CANDIDATO["url"]: [DecisaoInsercaoSchema(
        decisao="aplicar", paragrafo_idx=0, trecho_original="revenda sem estoque",
        anchor_text="revenda sem estoque", confianca=0.9, motivo="Sinônimo direto de dropshipping.",
    )]}
    texto, inseridos = await inserir_inlinks(PILAR, [CANDIDATO], "u1")
    aplicados = [i for i in inseridos if i.status == "aplicado"]
    assert len(aplicados) == 1
    assert "[revenda sem estoque](https://ex.com/loja-virtual)" in texto
    assert aplicados[0].confianca == 0.9
    assert aplicados[0].sinal_cos_contexto is not None


async def test_decisao_sugerir_vira_sugestao_manual(monkeypatch):
    _fake_embeddings(monkeypatch)
    _AgenteFake.respostas_por_url = {CANDIDATO["url"]: [DecisaoInsercaoSchema(
        decisao="sugerir", motivo="Mencionar dropshipping no parágrafo de modelos.",
    )]}
    texto, inseridos = await inserir_inlinks(PILAR, [CANDIDATO], "u1", permitir_cta_fallback=False)
    assert "](https" not in texto
    assert [i.status for i in inseridos] == ["sugestao_manual"]
    assert "dropshipping" in (inseridos[0].motivo_sugestao or "")


async def test_decisao_descartar_vira_rejeitado_com_motivo(monkeypatch):
    _fake_embeddings(monkeypatch)
    _AgenteFake.respostas_por_url = {CANDIDATO["url"]: [DecisaoInsercaoSchema(
        decisao="descartar", motivo="Temas desconectados para o leitor.",
    )]}
    _texto, inseridos = await inserir_inlinks(PILAR, [CANDIDATO], "u1", permitir_cta_fallback=False)
    assert [i.status for i in inseridos] == ["rejeitado"]
    assert inseridos[0].motivo_rejeicao == "Temas desconectados para o leitor."


async def test_trecho_inexistente_vira_sugestao(monkeypatch):
    """Anti-alucinação: trecho que não existe literalmente nunca é aplicado."""
    _fake_embeddings(monkeypatch)
    _AgenteFake.respostas_por_url = {CANDIDATO["url"]: [DecisaoInsercaoSchema(
        decisao="aplicar", paragrafo_idx=0, trecho_original="vendas por atacado maritimo",
        anchor_text="vendas por atacado maritimo", motivo="ok",
    )]}
    texto, inseridos = await inserir_inlinks(PILAR, [CANDIDATO], "u1", permitir_cta_fallback=False)
    assert "](https" not in texto
    assert inseridos[0].status == "sugestao_manual"
    assert "não encontrado" in (inseridos[0].motivo_sugestao or "")


async def test_motivo_vazio_ganha_default(monkeypatch):
    _fake_embeddings(monkeypatch)
    _AgenteFake.respostas_por_url = {CANDIDATO["url"]: [DecisaoInsercaoSchema(decisao="sugerir", motivo="")]}
    _texto, inseridos = await inserir_inlinks(PILAR, [CANDIDATO], "u1", permitir_cta_fallback=False)
    assert inseridos[0].status == "sugestao_manual"
    assert inseridos[0].motivo_sugestao  # nunca vazio


async def test_pisos_legado_rebaixam_cosine_baixo(monkeypatch):
    """Com aplicar_pisos_legado=True, cosine 0 rebaixa para sugestão (rollback Distribuir)."""

    async def fake_batch_ortogonal(textos: list[str], usuario_id: str):
        return [[1.0, 0.0] if i % 2 == 0 else [0.0, 1.0] for i, _t in enumerate(textos)]

    monkeypatch.setattr(ins, "gerar_embeddings_batch", fake_batch_ortogonal)
    _AgenteFake.respostas_por_url = {CANDIDATO["url"]: [DecisaoInsercaoSchema(
        decisao="aplicar", paragrafo_idx=0, trecho_original="revenda sem estoque",
        anchor_text="revenda sem estoque", motivo="ok",
    )]}
    _texto, inseridos = await inserir_inlinks(
        PILAR, [CANDIDATO], "u1", permitir_cta_fallback=False, aplicar_pisos_legado=True,
    )
    assert inseridos[0].status == "sugestao_manual"


async def test_sem_pisos_legado_cosine_baixo_nao_rebaixa(monkeypatch):
    """No modo padrão o cosine é só sinal: mesma situação permanece aplicada."""

    async def fake_batch_ortogonal(textos: list[str], usuario_id: str):
        return [[1.0, 0.0] if i % 2 == 0 else [0.0, 1.0] for i, _t in enumerate(textos)]

    monkeypatch.setattr(ins, "gerar_embeddings_batch", fake_batch_ortogonal)
    _AgenteFake.respostas_por_url = {CANDIDATO["url"]: [DecisaoInsercaoSchema(
        decisao="aplicar", paragrafo_idx=0, trecho_original="revenda sem estoque",
        anchor_text="revenda sem estoque", motivo="ok",
    )]}
    _texto, inseridos = await inserir_inlinks(PILAR, [CANDIDATO], "u1", permitir_cta_fallback=False)
    assert inseridos[0].status == "aplicado"
    assert inseridos[0].sinal_cos_contexto == 0.0


async def test_colisao_min_distance_faz_retry_em_outro_paragrafo(monkeypatch):
    """Dois candidatos na mesma região: o 2º re-julga e aplica em parágrafo distante."""
    _fake_embeddings(monkeypatch)
    c2 = {**CANDIDATO, "url": "https://ex.com/formalizacao", "titulo": "Guia de formalização de empresas",
          "palavras_chave": ["formalizacao", "nota fiscal"], "score_total": 0.8}
    _AgenteFake.respostas_por_url = {
        CANDIDATO["url"]: [DecisaoInsercaoSchema(
            decisao="aplicar", paragrafo_idx=0, trecho_original="revenda sem estoque",
            anchor_text="revenda sem estoque", motivo="ok")],
        c2["url"]: [
            # 1ª proposta: trecho no MESMO parágrafo inicial → colide (< 50 palavras)
            DecisaoInsercaoSchema(decisao="aplicar", paragrafo_idx=0, trecho_original="novos empreendedores",
                                  anchor_text="novos empreendedores", motivo="ok"),
            # retry: trecho que só existe no 3º parágrafo (distante)
            DecisaoInsercaoSchema(decisao="aplicar", paragrafo_idx=0, trecho_original="formalize seu empreendimento",
                                  anchor_text="formalize seu empreendimento", motivo="ok"),
        ],
    }
    _texto, inseridos = await inserir_inlinks(
        PILAR, [CANDIDATO, c2], "u1", max_inlinks=2, permitir_cta_fallback=False,
    )
    aplicados = {i.url_destino: i for i in inseridos if i.status == "aplicado"}
    assert "https://ex.com/loja-virtual" in aplicados
    assert "https://ex.com/formalizacao" in aplicados, [
        (i.url_destino, i.status, i.motivo_sugestao) for i in inseridos
    ]
    assert _AgenteFake.chamadas == 3  # 2 julgamentos + 1 retry


async def test_cta_fallback_usa_titulo_sem_ancoras_preferidas(monkeypatch):
    _fake_embeddings(monkeypatch)
    _AgenteFake.respostas_por_url = {CANDIDATO["url"]: [DecisaoInsercaoSchema(
        decisao="sugerir", motivo="Sem âncora natural.",
    )]}
    texto, inseridos = await inserir_inlinks(PILAR, [CANDIDATO], "u1", permitir_cta_fallback=True)
    assert "> Leia também: [Como abrir uma loja virtual (dropshipping)](https://ex.com/loja-virtual)" in texto
    assert any(i.status == "aplicado" for i in inseridos)
