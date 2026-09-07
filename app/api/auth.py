"""Endpoints de autenticación: login con Google y perfil del usuario."""

from __future__ import annotations

import logging
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.config import get_settings
from app.core.auth import create_access_token, get_current_user
from app.db import get_session_factory
from app.models import User
from app.services import google_auth

logger = logging.getLogger("multibot.auth")

router = APIRouter(tags=["auth"])


@router.get("/auth/google/login")
async def google_login() -> RedirectResponse:
    """Redirige al consentimiento de Google."""
    settings = get_settings()
    if not settings.google_client_id or not settings.google_redirect_uri:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth no configurado (GOOGLE_CLIENT_ID / GOOGLE_REDIRECT_URI)",
        )
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return RedirectResponse(url)


@router.get("/auth/google/callback")
async def google_callback(code: str) -> dict:
    """Intercambia el código, valida el ID token y emite un JWT de sesión."""
    try:
        tokens = await google_auth.exchange_code(code)
        info = await google_auth.verify_id_token(tokens["id_token"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Login Google falló: %s", exc)
        raise HTTPException(status_code=401, detail="No se pudo autenticar con Google")

    email = info["email"]
    name = info.get("name", "")
    picture = info.get("picture", "")
    sub = info.get("sub", "")

    factory = get_session_factory()
    async with factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                name=name,
                picture=picture,
                google_sub=sub,
                role="agent",  # el primer login crea al usuario como agente
            )
            session.add(user)
        else:
            user.name = name
            user.picture = picture
            user.google_sub = sub
        await session.commit()
        role = user.role

    user_dict = {"email": email, "name": name, "picture": picture, "role": role}
    token = create_access_token(user_dict)
    logger.info("Login Google OK para %s (rol %s)", email, role)
    return {"token": token, "user": user_dict}


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)) -> dict:
    """Devuelve el usuario autenticado (extraído del JWT)."""
    return user
