"""Engine async de SQLAlchemy y dependencia de sesión para FastAPI."""

import os
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos ORM."""


# Runtime usa el pooler de Supabase (puerto 6543, modo transaction).
# pgBouncer en modo transaction no soporta prepared statements de asyncpg;
# statement_cache_size=0 es obligatorio o las queries fallan intermitentemente.
def _asyncpg_url(raw: str) -> str:
    """Normaliza la URL de Postgres a asyncpg. Falla claro si viene vacía/inválida."""
    if "://" not in raw:
        raise RuntimeError(
            "POSTGRES_PRISMA_URL vacío o inválido. Copia la connection string de Supabase "
            "(Settings → Database → Transaction pooler, puerto 6543) al .env."
        )
    # ponytail: Vercel emite postgres:// con ?sslmode=require; asyncpg usa ssl= en connect_args
    return "postgresql+asyncpg://" + raw.split("://", 1)[1].split("?")[0]


def _engine_kwargs(serverless: bool) -> dict[str, Any]:
    """Config del engine según la plataforma. Ver docs/DEPLOYMENT.md.

    Serverless (Vercel): NullPool. El contenedor se congela entre invocaciones,
    así que un pool en proceso guarda conexiones que del otro lado ya están
    muertas, y cada instancia concurrente multiplica su propio pool contra el
    límite de conexiones de Supabase. El pooler (pgBouncer) ya hace el pooling
    real — abrir y cerrar por request es lo correcto acá.

    Proceso persistente (servidor universitario): pool por defecto, con
    pool_pre_ping para descartar conexiones que el pooler cerró por su cuenta.
    """
    connect_args = {"statement_cache_size": 0, "ssl": "require"}
    if serverless:
        return {"connect_args": connect_args, "poolclass": NullPool}
    return {"connect_args": connect_args, "pool_pre_ping": True}


# VERCEL="1" lo define la propia plataforma en build y en runtime — no hay que
# configurarla a mano en el dashboard.
engine = create_async_engine(
    _asyncpg_url(settings.postgres_prisma_url),
    **_engine_kwargs(serverless=bool(os.getenv("VERCEL"))),
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
