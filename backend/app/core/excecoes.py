from fastapi import HTTPException, status


class CredenciaisInvalidas(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais invalidas",
        )


class TokenInvalido(HTTPException):
    def __init__(self, detail: str = "Token invalido ou expirado"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )


class TokenExpirado(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
        )


class RateLimitExcedido(HTTPException):
    def __init__(self, detail: str = "Muitas tentativas. Aguarde alguns minutos."):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )


class SenhaForteRequerida(HTTPException):
    def __init__(self, detail: str = "Senha nao atende aos requisitos de seguranca"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )


class RecursoNaoEncontrado(HTTPException):
    def __init__(self, detail: str = "Recurso nao encontrado"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )


class MfaNaoAtivo(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA nao esta ativo para este usuario",
        )


class MfaCodigoInvalido(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Codigo MFA invalido",
        )


class CsrfInvalido(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF invalido",
        )


class UsuarioInativo(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Conta inativa",
        )


class EmailJaExiste(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este e-mail ja esta cadastrado",
        )


class SenhaAtualIncorreta(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Senha atual incorreta",
        )


class ErroTransitorio(Exception):
    """Falha temporaria: pode ser retentada."""


class ErroPermanente(Exception):
    """Falha permanente: nao retentar."""
