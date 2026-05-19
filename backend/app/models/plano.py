from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class Plano(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "planos"

    nome: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    creditos_por_mes: Mapped[int] = mapped_column(Integer, nullable=False)
    preco_mensal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    cliente_limite: Mapped[int] = mapped_column(Integer, nullable=False)
    permite_extras: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
