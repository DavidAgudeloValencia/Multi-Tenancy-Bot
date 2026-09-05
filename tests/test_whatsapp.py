"""Pruebas de la capa de envío de WhatsApp (Fase 5) — sin llamar a Meta.

Se sustituye `_post` para capturar los payloads y simular errores de la
Graph API, verificando la estructura de cada tipo de mensaje y el manejo
de errores tipados (WhatsAppError).

Ejecutar con:  pytest -q
"""

from __future__ import annotations

import pytest

from app.services.whatsapp import (
    WhatsAppError,
    describe_error,
    send_document_message,
    send_image_message,
    send_template_message,
    send_text_message,
)


@pytest.fixture
def capture_post(monkeypatch):
    """Captura el payload enviado a `_post` y devuelve una respuesta fake."""
    captured: dict = {}

    async def fake_post(payload: dict, phone_number_id=None, access_token=None) -> dict:
        captured["payload"] = payload
        captured["phone_number_id"] = phone_number_id
        captured["access_token"] = access_token
        return {"messaging_product": "whatsapp", "messages": [{"id": "wamid.TEST"}]}

    monkeypatch.setattr("app.services.whatsapp._post", fake_post)
    return captured


async def test_send_text_message_payload(capture_post) -> None:
    await send_text_message("573001234567", "Hola, esto es una prueba")
    payload = capture_post["payload"]
    assert payload["messaging_product"] == "whatsapp"
    assert payload["to"] == "573001234567"
    assert payload["type"] == "text"
    assert payload["text"]["body"] == "Hola, esto es una prueba"


async def test_send_with_tenant_credentials(capture_post) -> None:
    """En multi-tenant se envía con el número y token del agente."""
    await send_text_message(
        "573001234567",
        "Hola",
        phone_number_id="999999999",
        access_token="TOKEN_AGENTE",
    )
    assert capture_post["phone_number_id"] == "999999999"
    assert capture_post["access_token"] == "TOKEN_AGENTE"


async def test_send_template_message_payload(capture_post) -> None:
    await send_template_message(
        "573001234567",
        "recordatorio_renovacion",
        language_code="es",
        parameters=["Juan", "2025-06-30"],
    )
    payload = capture_post["payload"]
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "recordatorio_renovacion"
    assert payload["template"]["language"] == {"code": "es"}
    assert payload["template"]["components"] == [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "Juan"},
                {"type": "text", "text": "2025-06-30"},
            ],
        }
    ]


async def test_send_template_message_without_parameters(capture_post) -> None:
    await send_template_message("573001234567", "saludo_general")
    payload = capture_post["payload"]
    assert payload["template"]["name"] == "saludo_general"
    assert "components" not in payload["template"]


async def test_send_document_message_payload(capture_post) -> None:
    await send_document_message(
        "573001234567",
        "https://cdn.example.com/carne.pdf",
        caption="Tu carné digital",
        filename="carne.pdf",
    )
    payload = capture_post["payload"]
    assert payload["type"] == "document"
    assert payload["document"]["link"] == "https://cdn.example.com/carne.pdf"
    assert payload["document"]["filename"] == "carne.pdf"
    assert payload["document"]["caption"] == "Tu carné digital"


async def test_send_image_message_payload(capture_post) -> None:
    await send_image_message(
        "573001234567",
        "https://cdn.example.com/infografia.png",
        caption="Guía rápida",
    )
    payload = capture_post["payload"]
    assert payload["type"] == "image"
    assert payload["image"]["link"] == "https://cdn.example.com/infografia.png"
    assert payload["image"]["caption"] == "Guía rápida"


async def test_whatsapp_error_is_raised_with_code(monkeypatch) -> None:
    async def failing_post(payload: dict, phone_number_id=None, access_token=None) -> dict:
        raise WhatsAppError(131026, "Message undeliverable", raw={})

    monkeypatch.setattr("app.services.whatsapp._post", failing_post)
    with pytest.raises(WhatsAppError) as excinfo:
        await send_text_message("573001234567", "Hola")
    assert excinfo.value.code == 131026
    assert "24 h" in str(excinfo.value)


def test_describe_error_mapping() -> None:
    assert "plantilla" in describe_error(131026)
    assert "autorizados" in describe_error(131030)
    assert "Token" in describe_error(190)
    assert "desconocido" in describe_error(None)
    assert "documentación" in describe_error(999999)
