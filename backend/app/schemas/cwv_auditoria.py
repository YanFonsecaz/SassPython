"""Schemas da auditoria CWV (SPEC_CWV_Auditoria_Ciclo_De_Vida)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

FaseAuditoria = Literal["before", "aguardando_implementacao", "after", "concluida"]
OrigemItem = Literal["psi_audit", "page_experience", "field_data"]
StatusCheck = Literal["pass", "fail", "na"]
StatusImplementacao = Literal["nao_executado", "em_andamento", "implementado"]


class AuditoriaCriarRequest(BaseModel):
    cliente_id: UUID
    execucao_id: UUID
    titulo: str | None = None


class ChecklistItemResposta(BaseModel):
    id: UUID
    origem: OrigemItem
    item_codigo: str
    titulo: str
    status_before: StatusCheck
    status_after: StatusCheck | None = None
    status_implementacao: StatusImplementacao = "nao_executado"
    nota_cliente: str | None = None
    nota_seo: str | None = None
    prioridade: int = 0
    esforco: str | None = None
    escopo_json: dict = {}


class AuditoriaResposta(BaseModel):
    id: UUID
    cliente_id: UUID
    titulo: str
    fase: FaseAuditoria
    execucao_before_id: UUID | None = None
    execucao_after_id: UUID | None = None
    health_score_before: float | None = None
    health_score_after: float | None = None
    consolidacao_status: str = "nao_executada"
    checklist: list[ChecklistItemResposta] = []
    n_pass_before: int = 0
    n_fail_before: int = 0
    n_implementados: int = 0
    criado_em: str
    atualizado_em: str


class AuditoriaResumo(BaseModel):
    id: UUID
    titulo: str
    fase: FaseAuditoria
    health_score_before: float | None = None
    health_score_after: float | None = None
    n_itens: int = 0
    criado_em: str


class AuditoriaListResponse(BaseModel):
    auditorias: list[AuditoriaResumo]


class AuditoriaPatch(BaseModel):
    fase: FaseAuditoria | None = None
    titulo: str | None = None


class ChecklistItemPatch(BaseModel):
    status_implementacao: StatusImplementacao | None = None
    nota_cliente: str | None = None
    nota_seo: str | None = None
