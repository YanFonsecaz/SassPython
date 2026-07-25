"""Schemas da Auditoria de SEO Técnico."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

StatusItem = Literal["aprovado", "atencao", "reprovado", "na", "sem_dados"]
FaseAuditoria = Literal["before", "implementacao", "after", "concluida"]


class AuditoriaCriar(BaseModel):
    cliente_id: UUID
    dominio: HttpUrl


class AuditoriaPatch(BaseModel):
    fase: FaseAuditoria | None = None


class AuditoriaResumo(BaseModel):
    id: UUID
    cliente_id: UUID
    dominio: str
    fase: str
    score_antes: float | None
    score_depois: float | None
    criado_em: datetime

    model_config = {"from_attributes": True}


class CrawlResumo(BaseModel):
    id: UUID
    fase_destino: str
    origem: str
    status: str
    erro_msg: str | None
    contadores_json: dict
    criado_em: datetime

    model_config = {"from_attributes": True}


class ItemResposta(BaseModel):
    item_slug: str
    nome: str
    categoria: str
    peso: int
    prioridade: str
    fonte: str
    modo: str
    status_antes: StatusItem | None
    status_depois: StatusItem | None
    # Onda 3 — IA: diagnóstico e recomendação gerados pelos agentes (ou editados
    # manualmente pelo consultor). None quando a IA ainda não rodou/item sem regra.
    diagnostico: str | None = None
    recomendacao: str | None = None
    evidencias_json: dict
    status_cliente: str | None
    validacao_seo: str | None
    observacao_cliente: str | None
    observacao_seo: str | None


class AuditoriaDetalhe(AuditoriaResumo):
    ultimo_crawl: CrawlResumo | None
    itens: list[ItemResposta]


class ItemPatch(BaseModel):
    status_antes: StatusItem | None = None
    status_depois: StatusItem | None = None
    # Permite o consultor sobrescrever o texto gerado pela IA (revisão humana).
    diagnostico: str | None = Field(default=None, max_length=10000)
    recomendacao: str | None = Field(default=None, max_length=10000)
    status_cliente: str | None = Field(default=None, max_length=2000)
    validacao_seo: str | None = Field(default=None, max_length=2000)
    observacao_cliente: str | None = Field(default=None, max_length=5000)
    observacao_seo: str | None = Field(default=None, max_length=5000)
