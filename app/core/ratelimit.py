"""Rate limiting en memoria (fijo por ventana de tiempo).

Protege el webhook y el panel de administración contra abuso (p. ej. fuerza
bruta de la clave de admin o inundación del webhook).

En producción multi-instancia, sustituir por un limiter distribuido (Redis +
script Lua) para compartir el contador entre réplicas.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    """Límite por ventana fija (por clave, p. ej. IP), thread-safe."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Registra un intento y devuelve True si está dentro del límite."""
        now = time.monotonic()
        with self._lock:
            queue = self._hits[key]
            while queue and now - queue[0] > self._window:
                queue.popleft()
            if len(queue) >= self._limit:
                return False
            queue.append(now)
            return True


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def make_rate_limit_dependency(limiter: RateLimiter):
    """Crea una dependencia de FastAPI que aplica el limiter por IP."""

    async def dependency(request: Request) -> None:
        ip = _client_ip(request)
        if not limiter.allow(ip):
            raise HTTPException(
                status_code=429,
                detail="Demasiadas solicitudes. Intenta de nuevo en unos segundos.",
            )

    return dependency
