"""Cliente mínimo de Google OAuth 2.0 (code → tokens → verificación de ID token).

Sin librerías externas: usa la API de tokens y el endpoint `tokeninfo` de
Google mediante httpx. Las funciones son inyectables para poder probarlas sin
credenciales reales.
"""

from __future__ import annotations

import httpx

from app.config import get_settings

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


async def exchange_code(code: str) -> dict:
    """Intercambia el código de autorización por tokens (devuelve `id_token`)."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def verify_id_token(id_token: str) -> dict:
    """Valida el ID token de Google y devuelve el perfil (email, name, sub...)."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            GOOGLE_TOKENINFO_URL, params={"id_token": id_token}
        )
        response.raise_for_status()
        info = response.json()

    if info.get("aud") != settings.google_client_id:
        raise ValueError("audiencia del token no coincide con el client_id")
    if not info.get("email_verified"):
        raise ValueError("email no verificado en Google")
    return info
