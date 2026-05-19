from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class PacoteCredito(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "pacotes_creditos"

    nome: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    creditos: Mapped[int] = mapped_column(Integer, nullable=False)
    preco: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
