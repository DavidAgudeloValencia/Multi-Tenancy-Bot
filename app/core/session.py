"""Almacén de sesiones de conversación (Fase 4).

Abstracción sobre el estado por cliente de WhatsApp con dos implementaciones:
  - `MemorySessionStore`: en memoria (desarrollo local, sin Redis).
  - `RedisSessionStore`: Redis real (producción, Docker Compose en Fase 6).

El TTL (24 h por defecto) hace que el contexto de cada cliente expire solo,
tal como recomienda el planning.md §4 (WhatsApp es asíncrono: un cliente puede
escribir hoy y volver en 3 días).
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger("multibot.session")

# Prefijo de las claves en Redis (evita colisiones con otras apps).
_KEY_PREFIX = "multibot:session:"


class SessionStore(ABC):
    """Contrato del almacén de sesiones (clave -> dict JSON)."""

    @abstractmethod
    async def get(self, key: str) -> dict | None:
        """Devuelve la sesión o None si no existe/expiró."""

    @abstractmethod
    async def set(self, key: str, value: dict, ttl: int | None = None) -> None:
        """Guarda la sesión con tiempo de vida (segundos)."""


class MemorySessionStore(SessionStore):
    """Implementación en memoria con expiración perezosa (solo desarrollo)."""

    def __init__(self, default_ttl: int = 86400) -> None:
        self._default_ttl = default_ttl
        self._data: dict[str, tuple[dict, float]] = {}

    async def get(self, key: str) -> dict | None:
        item = self._data.get(key)
        if item is None:
            return None
        value, expires_at = item
        if time.time() > expires_at:
            del self._data[key]
            return None
        return value

    async def set(self, key: str, value: dict, ttl: int | None = None) -> None:
        ttl = ttl or self._default_ttl
        self._data[key] = (value, time.time() + ttl)


class RedisSessionStore(SessionStore):
    """Implementación con Redis real (producción)."""

    def __init__(self, url: str, default_ttl: int = 86400) -> None:
        self._default_ttl = default_ttl
        self._redis = aioredis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> dict | None:
        raw = await self._redis.get(f"{_KEY_PREFIX}{key}")
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: dict, ttl: int | None = None) -> None:
        ttl = ttl or self._default_ttl
        payload = json.dumps(value, ensure_ascii=False)
        await self._redis.set(f"{_KEY_PREFIX}{key}", payload, ex=ttl)

    async def close(self) -> None:
        await self._redis.aclose()


class PrefixedSessionStore(SessionStore):
    """Envuelve un SessionStore y prefija las claves (namespace por tenant).

    Permite que varios agentes compartan el mismo Redis sin colisiones:
    las claves de este tenant quedan como `{prefix}:{key}`.
    """

    def __init__(self, store: SessionStore, prefix: str) -> None:
        self._store = store
        self._prefix = f"{prefix}:"

    async def get(self, key: str) -> dict | None:
        return await self._store.get(f"{self._prefix}{key}")

    async def set(self, key: str, value: dict, ttl: int | None = None) -> None:
        await self._store.set(f"{self._prefix}{key}", value, ttl=ttl)


# Singleton del almacén para toda la app.
_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Devuelve el almacén de sesiones según `settings.session_store`."""
    global _store
    if _store is None:
        settings = get_settings()
        if settings.session_store == "redis":
            logger.info("Usando Redis como almacén de sesiones: %s", settings.redis_url)
            _store = RedisSessionStore(settings.redis_url, settings.session_ttl_seconds)
        else:
            logger.info("Usando almacén de sesiones en memoria (desarrollo).")
            _store = MemorySessionStore(settings.session_ttl_seconds)
    return _store
