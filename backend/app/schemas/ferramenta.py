import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class GerarArtigoRequest(BaseModel):
    cliente_id: uuid.UUID
    persona_id: str = Field(min_length=1, max_length=100)
    topico: str = Field(min_length=1, max_length=500)
    palavra_chave_principal: str = Field(min_length=1, max_length=200)
    palavras_chave_secundarias: list[str] = Field(default_factory=list, max_length=20)
    tipo_conteudo: str = Field(default="blog")
    meta_palavras: int = Field(default=2000, ge=300, le=5000)
    objetivo: str = Field(default="", max_length=1000)
    artigo_introdutorio: str = Field(default="", max_length=2000)
    perguntas_clientes: str = Field(default="", max_length=2000)
    instrucoes_adicionais: str = Field(default="", max_length=2000)

    @field_validator("palavras_chave_secundarias")
    @classmethod
    def validar_secundarias(cls, v: list[str]) -> list[str]:
        for kw in v:
            if len(kw) > 100:
                raise ValueError(f"Palavra-chave secundaria excede 100 caracteres: {kw[:30]}...")
        return v

    @field_validator("tipo_conteudo")
    @classmethod
    def validar_tipo(cls, v: str) -> str:
        validos = {"blog", "produto", "categoria", "noticias", "instagram", "topico"}
        if v not in validos:
            raise ValueError(f"Tipo de conteudo invalido: {v}. Validos: {validos}")
        return v


class AprovacaoRequest(BaseModel):
    acao: str = Field(pattern=r"^(aprovar|reprovar)$")
    feedback: str | None = Field(default=None, max_length=2000)


class ExecucaoResponse(BaseModel):
    id: uuid.UUID
    ferramenta: str
    status: str
    etapa_atual: str | None
    creditos_cobrados: int
    erro_msg: str | None
    tentativas_revisao: int
    tentativas_feedback: int
    criado_em: datetime
    concluida_em: datetime | None

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def parse_id(cls, v):
        if isinstance(v, str):
            return uuid.UUID(v)
        return v


class ExecucaoDetalheResponse(ExecucaoResponse):
    entrada_json: dict[str, Any]
    resultado_json: dict[str, Any] | None
    cliente_id: uuid.UUID | None


class VersaoResponse(BaseModel):
    versao: int
    origem: str
    titulo: str
    conteudo_markdown: str
    contagem_palavras: int
    score_revisao: float | None
    feedback_recebido: str | None
    criado_em: datetime

    model_config = {"from_attributes": True}


class VersoesListResponse(BaseModel):
    execucao_id: uuid.UUID
    versoes: list[VersaoResponse]


class ExecucaoCriadaResponse(BaseModel):
    id: uuid.UUID
    ferramenta: str
    status: str
    etapa_atual: str | None
    creditos_cobrados: int
    criado_em: datetime


class ExecucoesListResponse(BaseModel):
    execucoes: list[ExecucaoResponse]
    total: int


class CancelarResponse(BaseModel):
    id: uuid.UUID
    status: str
    creditos_cobrados: int
    mensagem: str


class CustoItem(BaseModel):
    acao: str
    custo_creditos: int
    chamadas_llm_estimadas: int


class CustosResponse(BaseModel):
    custos: list[CustoItem]


class MensagemResponse(BaseModel):
    mensagem: str
