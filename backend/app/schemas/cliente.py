import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PersonaSchema(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    tom_voz: str = Field(default="profissional")
    nivel_tecnico: str = Field(default="intermediario")
    estilo_escrita: str = Field(default="didatico")
    objetivo: str = Field(default="", max_length=500)
    palavras_proibidas: list[str] = Field(default_factory=list, max_length=50)
    palavras_recomendadas: list[str] = Field(default_factory=list, max_length=50)
    instrucoes_gerais: str = Field(default="", max_length=1000)


class PersonaGlobalSchema(BaseModel):
    tom_voz: str = Field(default="profissional")
    nivel_tecnico: str = Field(default="intermediario")
    estilo_escrita: str = Field(default="didatico")
    instrucoes_gerais: str = Field(default="", max_length=1000)
    exemplos_textos: list[str] = Field(default_factory=list)


class ConfigJsonSchema(BaseModel):
    persona_global: PersonaGlobalSchema = Field(default_factory=PersonaGlobalSchema)
    personas: list[PersonaSchema] = Field(default_factory=list)


class ClienteCreateRequest(BaseModel):
    nome: str = Field(min_length=2, max_length=255)
    site_url: str | None = Field(default=None, max_length=500)
    config_json: ConfigJsonSchema = Field(default_factory=ConfigJsonSchema)

    @field_validator("site_url")
    @classmethod
    def validar_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL deve comecar com http:// ou https://")
        if not v.endswith("/"):
            v = v + "/"
        return v

    @field_validator("config_json")
    @classmethod
    def validar_personas_unicas(cls, v: ConfigJsonSchema) -> ConfigJsonSchema:
        nomes = [p.nome.lower() for p in v.personas]
        if len(nomes) != len(set(nomes)):
            raise ValueError("Nomes de personas devem ser unicos dentro do cliente")
        return v


class ClienteUpdateRequest(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=255)
    site_url: str | None = Field(default=None, max_length=500)
    config_json: ConfigJsonSchema | None = None

    @field_validator("site_url")
    @classmethod
    def validar_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL deve comecar com http:// ou https://")
        if not v.endswith("/"):
            v = v + "/"
        return v


class ClienteResponse(BaseModel):
    id: uuid.UUID
    nome: str
    site_url: str | None
    config_json: dict[str, Any]
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def parse_id(cls, v):
        if isinstance(v, str):
            return uuid.UUID(v)
        return v


class ClienteListResponse(BaseModel):
    clientes: list[ClienteResponse]
    total: int


class MensagemResponse(BaseModel):
    mensagem: str
