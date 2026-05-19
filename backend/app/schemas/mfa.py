
from pydantic import BaseModel


class MfaDispositivoResponse(BaseModel):
    id: str
    nome: str
    tipo: str
    criado_em: str

class MfaConfigurarRequest(BaseModel):
    nome: str

class MfaAtivarRequest(BaseModel):
    dispositivo_id: str
    codigo: str
    senha_confirmacao: str

class MfaRemoverRequest(BaseModel):
    codigo_totp: str
