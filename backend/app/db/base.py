"""Camada de persistência: engine assíncrono, session factory e Base declarativa.

Naming convention determinística para constraints (ck_, uq_, ix_, fk_, pk_):
sem isto, o Postgres/SQLAlchemy gera nomes automáticos não determinísticos
para constraints, o que torna as migrações Alembic frágeis (o autogenerate
deteta "mudanças" em constraints que na prática não mudaram).
"""
from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


def utcnow() -> datetime.datetime:
    """Default de timestamp gerado em Python (UTC, com microssegundos).

    Usado como `default=`/`onupdate=` (client-side) em vez de depender
    apenas de `server_default=func.now()`. Motivo: o `CURRENT_TIMESTAMP`
    do SQLite (usado nos testes) só tem precisão ao segundo — duas
    linhas criadas no mesmo segundo ficavam com representações de texto
    diferentes das usadas na comparação do cursor de paginação
    (que inclui microssegundos), partindo silenciosamente a paginação
    keyset. Gerar o timestamp em Python garante que o valor comparado é
    sempre exatamente o valor armazenado, em qualquer dialeto.
    """
    return datetime.datetime.now(datetime.UTC)

# Convenção de nomenclatura idêntica à recomendada pela documentação oficial
# do Alembic para evitar nomes de constraint não determinísticos.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa partilhada por todos os modelos ORM."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=_settings.database_echo,
    future=True,
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency FastAPI: fornece uma sessão por pedido, com fecho garantido.

    Faz `commit()` no final de um pedido bem-sucedido e `rollback()` se
    uma exceção propagar — padrão unit-of-work: cada pedido HTTP é uma
    transação. Sem isto, os repositórios (que só fazem `flush()`,
    nunca `commit()`, ver Módulo 2) deixariam todas as escritas por
    confirmar, e a sessão fechada no fim do pedido reverteria-as
    silenciosamente em produção — um bug que os testes de integração
    não apanhavam porque partilham deliberadamente uma única sessão
    por teste (múltiplos pedidos HTTP simulados na mesma transação).
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
