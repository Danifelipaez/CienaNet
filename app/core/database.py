"""Engine async de SQLAlchemy y dependencia de sesión para FastAPI."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

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


engine = create_async_engine(
    _asyncpg_url(settings.postgres_prisma_url),
    connect_args={"statement_cache_size": 0, "ssl": "require"},
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
