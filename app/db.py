"""Capa de base de datos (SQLAlchemy asíncrono).

Soporta SQLite (arranque/desarrollo) y PostgreSQL (producción) cambiando
`DATABASE_URL`. El ORM guarda: mappings conversación↔ticket, mensajes y (en
fases siguientes) auditoría y usuarios.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Clase base declarativa de todos los modelos."""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Devuelve (cachea) el motor de base de datos."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, echo=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Devuelve (cachea) la fábrica de sesiones."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def init_db() -> None:
    """Crea las tablas si no existen (llamado en el arranque)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
