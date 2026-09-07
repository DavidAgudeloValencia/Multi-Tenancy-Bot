"""Pruebas automáticas de los endpoints del webhook (Fase 2).

Ejecutar con:  pytest -q
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from main import app

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures"


def test_health_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": get_settings().app_name}


def test_webhook_verification_ok() -> None:
    """Meta valida la URL: con el token correcto respondemos el challenge."""
    token = get_settings().whatsapp_verify_token
    response = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": token,
            "hub.challenge": "CHALLENGE_123",
        },
    )
    assert response.status_code == 200
    assert response.text == "CHALLENGE_123"


def test_webhook_verification_rejected() -> None:
    """Token incorrecto -> 403, Meta nunca suscribe la URL."""
    response = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token-incorrecto",
            "hub.challenge": "CHALLENGE_123",
        },
    )
    assert response.status_code == 403


def test_webhook_receive_message(monkeypatch) -> None:
    """Un payload real de mensaje entrante debe procesarse con 200."""
    monkeypatch.setattr("main.settings.webhook_app_secret", "")
    payload = json.loads(
        (FIXTURES / "webhook_message.json").read_text(encoding="utf-8")
    )
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "received"}


def test_webhook_receive_unknown_object(monkeypatch) -> None:
    """Eventos de otros objetos (ej. 'page') se ignoran sin error."""
    monkeypatch.setattr("main.settings.webhook_app_secret", "")
    response = client.post("/webhook", json={"object": "page", "entry": []})
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
