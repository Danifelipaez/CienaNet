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
engine = create_async_engine(
    settings.database_url_pooler.replace("postgresql://", "postgresql+asyncpg://"),
    connect_args={"statement_cache_size": 0},
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
