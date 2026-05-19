import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class SaldoResponse(BaseModel):
    saldo_plano: int
    saldo_extras: int
    saldo_reservado: int = 0
    saldo_disponivel: int
    saldo_total: int
    ciclo_inicio: str
    ciclo_fim: str


class TransacaoResponse(BaseModel):
    id: uuid.UUID
    tipo: str
    quantidade: int
    descricao: str
    ferramenta: str | None
    criado_em: datetime

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def parse_id(cls, v):
        if isinstance(v, str):
            return uuid.UUID(v)
        return v


class TransacoesListResponse(BaseModel):
    transacoes: list[TransacaoResponse]
    total: int
