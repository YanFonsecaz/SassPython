import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=64)


class CadastroRequest(BaseModel):
    nome: str = Field(min_length=1, max_length=255)
    email: EmailStr
    senha: str = Field(min_length=12, max_length=64)
    senha_confirmacao: str

    @field_validator("senha")
    @classmethod
    def validar_complexidade(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Senha deve ter pelo menos uma letra maiuscula")
        if not re.search(r"[a-z]", v):
            raise ValueError("Senha deve ter pelo menos uma letra minuscula")
        if not re.search(r"\d", v):
            raise ValueError("Senha deve ter pelo menos um numero")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]", v):
            raise ValueError("Senha deve ter pelo menos um caractere especial")
        return v


class MfaVerificarRequest(BaseModel):
    token_temporario: str
    codigo_totp: str = Field(min_length=6, max_length=6)


class RefreshRequest(BaseModel):
    pass


class AlterarSenhaRequest(BaseModel):
    senha_atual: str = Field(min_length=1, max_length=64)
    nova_senha: str = Field(min_length=12, max_length=64)
    nova_senha_confirmacao: str
    codigo_totp: str | None = Field(default=None, min_length=6, max_length=6)

    @field_validator("nova_senha")
    @classmethod
    def validar_complexidade(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Senha deve ter pelo menos uma letra maiuscula")
        if not re.search(r"[a-z]", v):
            raise ValueError("Senha deve ter pelo menos uma letra minuscula")
        if not re.search(r"\d", v):
            raise ValueError("Senha deve ter pelo menos um numero")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]", v):
            raise ValueError("Senha deve ter pelo menos um caractere especial")
        return v


class RecuperarSenhaRequest(BaseModel):
    email: EmailStr


class ResetarSenhaRequest(BaseModel):
    token: str = Field(min_length=1)
    nova_senha: str = Field(min_length=12, max_length=64)
    nova_senha_confirmacao: str

    @field_validator("nova_senha")
    @classmethod
    def validar_complexidade(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Senha deve ter pelo menos uma letra maiuscula")
        if not re.search(r"[a-z]", v):
            raise ValueError("Senha deve ter pelo menos uma letra minuscula")
        if not re.search(r"\d", v):
            raise ValueError("Senha deve ter pelo menos um numero")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]", v):
            raise ValueError("Senha deve ter pelo menos um caractere especial")
        return v


class MfaConfigurarRequest(BaseModel):
    tipo: str = Field(default="totp")
    nome: str = Field(min_length=1, max_length=100)


class MfaAtivarRequest(BaseModel):
    dispositivo_id: str
    codigo: str = Field(min_length=6, max_length=6)
    senha_confirmacao: str = Field(min_length=1, max_length=64)


class MfaRemoverRequest(BaseModel):
    codigo_totp: str = Field(min_length=6, max_length=6)


class UsuarioResponse(BaseModel):
    id: uuid.UUID
    email: str
    nome: str
    mfa_ativo: bool
    email_verificado: bool
    plano: str | None = None
    criado_em: datetime

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def parse_id(cls, v):
        if isinstance(v, str):
            return uuid.UUID(v)
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    csrf_token: str | None = None


class MensagemResponse(BaseModel):
    mensagem: str


class MfaRequeridoResponse(BaseModel):
    mfa_requerido: bool = True
    tipo: str
    token_temporario: str


class MfaConfigurarResponse(BaseModel):
    dispositivo_id: str
    qr_code_base64: str
    segredo: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    csrf_token: str | None = None
