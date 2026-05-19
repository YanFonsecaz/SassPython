"""
Seed script — cria um usuário de teste com créditos ilimitados.

Uso:
    cd backend
    uv run python -m scripts.seed_user

Credenciais criadas:
    Email: teste@seosaas.com
    Senha: Teste@12345678
    Créditos: 999.999.999 (ilimitado)
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

# Garante que o diretório backend/ esteja no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings  # noqa: E402
from app.core.seguranca import hash_senha  # noqa: E402
from app.db.session import async_session_factory, engine  # noqa: E402
from app.models.conta_credito import ContaCredito  # noqa: E402
from app.models.plano import Plano  # noqa: E402
from app.models.transacao_credito import TransacaoCredito  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402

EMAIL = "teste@seosaas.com"
SENHA = "Teste@12345678"
NOME = "Usuário Teste"
CREDITOS = 999_999_999


async def main() -> None:
    async with async_session_factory() as db:
        db: AsyncSession

        # ── 1. Plano Ilimitado ──────────────────────────────────
        resultado = await db.execute(select(Plano).where(Plano.nome == "Ilimitado"))
        plano = resultado.scalar_one_or_none()

        if not plano:
            plano = Plano(
                nome="Ilimitado",
                creditos_por_mes=CREDITOS,
                preco_mensal=0,
                cliente_limite=9999,
                permite_extras=True,
                ativo=True,
            )
            db.add(plano)
            await db.flush()
            print("✅ Plano 'Ilimitado' criado")
        else:
            print("✅ Plano 'Ilimitado' já existe")

        # ── 2. Usuário ──────────────────────────────────────────
        resultado = await db.execute(select(Usuario).where(Usuario.email == EMAIL))
        usuario = resultado.scalar_one_or_none()

        if not usuario:
            usuario = Usuario(
                email=EMAIL,
                nome=NOME,
                senha_hash=hash_senha(SENHA),
                email_verificado=True,
                plano_id=plano.id,
                ativo=True,
            )
            db.add(usuario)
            await db.flush()
            print(f"✅ Usuário criado: {EMAIL}")
        else:
            # Atualiza plano se já existir
            usuario.plano_id = plano.id
            await db.flush()
            print(f"✅ Usuário já existe, plano atualizado: {EMAIL}")

        # ── 3. Conta de Crédito com saldo "ilimitado" ───────────
        resultado = await db.execute(
            select(ContaCredito).where(ContaCredito.usuario_id == usuario.id)
        )
        conta = resultado.scalar_one_or_none()

        if not conta:
            conta = ContaCredito(
                usuario_id=usuario.id,
                saldo_plano=CREDITOS,
                saldo_extras=CREDITOS,
                ciclo_inicio=date.today(),
                ciclo_fim=date.today() + timedelta(days=36500),  # ~100 anos
            )
            db.add(conta)
            await db.flush()

            transacao = TransacaoCredito(
                conta_id=conta.id,
                tipo="credito_extra",
                quantidade=CREDITOS,
                descricao="Seed: créditos ilimitados de teste",
            )
            db.add(transacao)
            print(f"✅ Conta de crédito criada: {CREDITOS:,} créditos")
        else:
            conta.saldo_plano = CREDITOS
            conta.saldo_extras = CREDITOS
            conta.ciclo_fim = date.today() + timedelta(days=36500)
            print(f"✅ Conta de crédito atualizada: {CREDITOS:,} créditos")

        await db.commit()

        print()
        print("═══════════════════════════════════════════")
        print("  CREDENCIAIS DE TESTE")
        print("═══════════════════════════════════════════")
        print(f"  Email:    {EMAIL}")
        print(f"  Senha:    {SENHA}")
        print(f"  Plano:    Ilimitado")
        print(f"  Créditos: {conta.saldo_total:,}")
        print("═══════════════════════════════════════════")


if __name__ == "__main__":
    asyncio.run(main())
