import os
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models.base import Base
from app.dependencies import get_db
from app.models.usuario import Usuario
from app.models.plano import Plano
import asyncio

# URL do banco de dados de teste do PostgreSQL
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5433/seo_saas_test")

@pytest.fixture(scope="session")
async def test_engine():
    """Cria engine de teste PostgreSQL"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Criar todas as tabelas
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Limpar e fechar
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def test_session(test_engine):
    """Cria sessão de teste"""
    async_session = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        
        # Limpar dados de teste
        await session.rollback()

@pytest.fixture
async def test_db(test_session):
    """Fixture que substitui o get_db do FastAPI para testes"""
    try:
        yield test_session
    finally:
        await test_session.close()

@pytest.fixture
async def test_user(test_session):
    """Cria um usuário de teste"""
    from app.core.seguranca import hash_senha as get_password_hash
    from datetime import datetime
    
    senha_hash = get_password_hash("testpass123")
    
    user = Usuario(
        email="test@example.com",
        nome="Test User",
        senha_hash=senha_hash,
        mfa_ativo=False,
        email_verificado=True,
        criado_em=datetime.utcnow(),
        modificado_em=datetime.utcnow(),
    )
    
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    
    yield user
    
    # Limpar
    await test_session.delete(user)
    await test_session.commit()

@pytest.fixture
async def auth_headers(test_user):
    """Cria headers de autenticação para testes"""
    from app.core.seguranca import gerar_jwt_access_token as create_access_token
    
    access_token = create_access_token(
        usuario_id=str(test_user.id),
        email=test_user.email,
        mfa_ativo=test_user.mfa_ativo,
    )
    return {"Authorization": f"Bearer {access_token}"}

@pytest.fixture(autouse=True)
def enable_db_access(test_db):
    """Fixture para injetar o banco de teste automaticamente"""
    # Esta fixture é aplicada automaticamente a todos os testes que pedem test_db
    pass