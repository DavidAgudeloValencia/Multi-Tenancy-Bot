"""Autenticación de la plataforma: JWT + dependencias de roles.

Tras el login con Google se emite un token JWT (HS256) firmado con
`AUTH_JWT_SECRET`. Las dependencias `get_current_user` y `require_role`
protegen los endpoints del panel de agentes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException

from app.config import get_settings


def create_access_token(user: dict) -> str:
    """Emite un JWT de sesión para el usuario (12 h por defecto)."""
    settings = get_settings()
    if not settings.auth_jwt_secret:
        raise RuntimeError("AUTH_JWT_SECRET no configurado")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.get("email"),
        "email": user.get("email"),
        "name": user.get("name", ""),
        "role": user.get("role", "agent"),
        "iat": now,
        "exp": now + timedelta(hours=settings.auth_token_hours),
    }
    return jwt.encode(payload, settings.auth_jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """Valida y decodifica el JWT (lanza 401 si es inválido/expirado)."""
    settings = get_settings()
    if not settings.auth_jwt_secret:
        raise HTTPException(status_code=503, detail="Autenticación no configurada")
    try:
        return jwt.decode(token, settings.auth_jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Token inválido o expirado") from exc


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> dict:
    """Dependencia: extrae el usuario autenticado del header Authorization."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")
    return decode_access_token(authorization[7:])


def require_role(*roles: str):
    """Dependencia que exige uno de los roles dados (admin|supervisor|agent)."""

    async def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Permisos insuficientes")
        return user

    return dependency
