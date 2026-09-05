"""Capa de salida hacia la WhatsApp Cloud API (Meta) — Fase 5.

Envío asíncrono (httpx) de mensajes con manejo tipado de errores:

  - `send_text_message`      : mensaje de texto libre (respuesta a un cliente
                               dentro de la ventana de 24 h).
  - `send_template_message`  : plantilla pre-aprobada (mensajes INICIADOS por
                               el bot: recordatorios de renovación, etc.).
                               Meta exige plantillas para iniciar conversación
                               (planning.md §4).
  - `send_document_message`  : envía un documento (PDF del carné, póliza...).
  - `send_image_message`     : envía una imagen (foto, infografía...).

Los errores de la Graph API se convierten en `WhatsAppError` con el código de
Meta (p. ej. 131026 = ventana de 24 h cerrada) para que el bot pueda actuar o
informar con precisión.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("multibot.whatsapp")

_API_TIMEOUT_SECONDS = 15

# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------


class WhatsAppError(Exception):
    """Error devuelto por la Graph API de Meta (con código de error)."""

    def __init__(self, code: int | None, message: str, raw: dict | None = None) -> None:
        self.code = code
        self.raw = raw or {}
        super().__init__(message)

    def __str__(self) -> str:
        detail = describe_error(self.code)
        return f"[{self.code}] {detail} | {super().__str__()}"


# Códigos de error comunes de la Graph API (mensajes accionables).
_ERROR_DESCRIPTIONS: dict[int, str] = {
    190: "Token de acceso inválido o expirado. Regenera el System User Token.",
    131026: "Ventana de 24 h cerrada: para iniciar conversación usa una "
    "plantilla aprobada (send_template_message).",
    131030: "El número del destinatario no está en la lista de autorizados "
    "del modo test.",
    131047: "El número no puede recibir este tipo de mensaje.",
    131048: "Permiso insuficiente para usar esta funcionalidad.",
    132000: "El número de teléfono del destinatario no está registrado en "
    "WhatsApp.",
    133010: "La plantilla no está aprobada o no existe.",
    133012: "Faltan parámetros en la plantilla (componentes inválidos).",
    133014: "Idioma de plantilla inválido.",
}


def describe_error(code: int | None) -> str:
    """Devuelve una descripción accionable para un código de error de Meta."""
    if code is None:
        return "Error desconocido de la Graph API."
    return _ERROR_DESCRIPTIONS.get(
        code, "Error de la Graph API (consulta la documentación de Meta)."
    )


# ---------------------------------------------------------------------------
# Transporte
# ---------------------------------------------------------------------------


async def _post(
    payload: dict,
    phone_number_id: str | None = None,
    access_token: str | None = None,
) -> dict:
    """Envía el payload al endpoint /messages de la Graph API.

    En multi-tenant cada agente envía con SU número y (opcional) SU token;
    si no se pasan, se usan los globales del .env.
    """
    settings = get_settings()
    pnid = phone_number_id or settings.whatsapp_phone_number_id
    token = access_token or settings.whatsapp_access_token
    url = f"{settings.graph_api_base_url}/{pnid}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        logger.error("Error de red con la Graph API: %s", exc)
        raise WhatsAppError(None, f"Error de red: {exc}") from exc

    if response.status_code != 200:
        error = response.json().get("error", {})
        raise WhatsAppError(
            code=error.get("code"),
            message=error.get("message", response.text[:300]),
            raw=error,
        )

    logger.info("Mensaje enviado (HTTP 200) a la Graph API (número %s)", pnid)
    return response.json()


# ---------------------------------------------------------------------------
# Funciones de envío
# ---------------------------------------------------------------------------


async def send_text_message(
    to_number: str,
    message_text: str,
    phone_number_id: str | None = None,
    access_token: str | None = None,
) -> dict:
    """Envía un mensaje de texto libre (ventana de 24 h del cliente)."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "text",
        "text": {"body": message_text, "preview_url": False},
    }
    result = await _post(payload, phone_number_id, access_token)
    logger.info("Texto enviado a %s", to_number)
    return result


async def send_template_message(
    to_number: str,
    template_name: str,
    language_code: str = "es",
    parameters: list[str] | None = None,
    phone_number_id: str | None = None,
    access_token: str | None = None,
) -> dict:
    """Envía una plantilla pre-aprobada (mensaje iniciado por el bot).

    Args:
        to_number: destinatario en formato internacional sin '+'.
        template_name: nombre de la plantilla aprobada en Meta.
        language_code: código de idioma de la plantilla (ej. 'es').
        parameters: valores de los variables {{1}}, {{2}}... de la plantilla.
    """
    components: list[dict] = []
    if parameters:
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in parameters],
            }
        )
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            **({"components": components} if components else {}),
        },
    }
    result = await _post(payload, phone_number_id, access_token)
    logger.info("Plantilla '%s' enviada a %s", template_name, to_number)
    return result


async def send_document_message(
    to_number: str,
    document_link: str,
    caption: str | None = None,
    filename: str | None = None,
    phone_number_id: str | None = None,
    access_token: str | None = None,
) -> dict:
    """Envía un documento (PDF, etc.) alojado en una URL pública."""
    document: dict[str, Any] = {"link": document_link}
    if filename:
        document["filename"] = filename
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "document",
        "document": document,
    }
    if caption:
        payload["document"]["caption"] = caption
    result = await _post(payload, phone_number_id, access_token)
    logger.info("Documento enviado a %s", to_number)
    return result


async def send_image_message(
    to_number: str,
    image_link: str,
    caption: str | None = None,
    phone_number_id: str | None = None,
    access_token: str | None = None,
) -> dict:
    """Envía una imagen alojada en una URL pública."""
    image: dict[str, Any] = {"link": image_link}
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "image",
        "image": image,
    }
    if caption:
        payload["image"]["caption"] = caption
    result = await _post(payload, phone_number_id, access_token)
    logger.info("Imagen enviada a %s", to_number)
    return result
