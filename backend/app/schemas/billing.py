import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class PlanoResponse(BaseModel):
    id: uuid.UUID | None
    nome: str
    creditos_por_mes: int
    preco_mensal: float
    cliente_limite: int
    permite_extras: bool

    model_config = {"from_attributes": True}


class PacoteResponse(BaseModel):
    id: uuid.UUID
    nome: str
    creditos: int
    preco: float
    ativo: bool

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def parse_id(cls, v):
        if isinstance(v, str):
            return uuid.UUID(v)
        return v


class PacotesListResponse(BaseModel):
    pacotes: list[PacoteResponse]


class ComprarPacoteRequest(BaseModel):
    pacote_id: uuid.UUID


class CompraResponse(BaseModel):
    id: uuid.UUID
    tipo: str
    pacote_id: uuid.UUID | None
    valor_pago: float
    status: str
    criado_em: datetime

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def parse_id(cls, v):
        if isinstance(v, str):
            return uuid.UUID(v)
        return v


class ComprasListResponse(BaseModel):
    compras: list[CompraResponse]
    total: int


class MensagemResponse(BaseModel):
    mensagem: str
