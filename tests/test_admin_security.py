"""Pruebas de seguridad y del panel de administración (multi-tenant).

Cubren: firma del webhook (HMAC), autenticación del panel, CRUD de agentes
con secretos enmascarados, y perfiles de bot.

Ejecutar con:  pytest -q
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.services.conversation import BotSettings, LEAD_QUESTIONS
from app.services.tenants import TenantRegistry
from main import app, _verify_meta_signature


# ---------------------------------------------------------------------------
# Firma del webhook
# ---------------------------------------------------------------------------
def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_signature_ok_when_secret_not_configured(monkeypatch) -> None:
    monkeypatch.setattr("main.settings.webhook_app_secret", "")
    assert _verify_meta_signature(b"{}", None) is True


def test_signature_valid_and_invalid(monkeypatch) -> None:
    monkeypatch.setattr("main.settings.webhook_app_secret", "s3cr3t")
    body = b'{"object":"whatsapp_business_account"}'
    assert _verify_meta_signature(body, _sign(body, "s3cr3t")) is True
    assert _verify_meta_signature(body, "sha256=deadbeef") is False
    assert _verify_meta_signature(body, None) is False
    assert _verify_meta_signature(body, "md5=abc") is False


def test_webhook_endpoint_rejects_forged_request(monkeypatch) -> None:
    """Sin firma o con firma inválida -> 401."""
    monkeypatch.setattr("main.settings.webhook_app_secret", "s3cr3t")
    client = TestClient(app)
    payload = {"object": "whatsapp_business_account", "entry": []}
    assert client.post("/webhook", json=payload).status_code == 401

    body = json.dumps(payload).encode()
    good = client.post(
        "/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body, "s3cr3t")},
    )
    assert good.status_code == 200


# ---------------------------------------------------------------------------
# Panel de administración (auth + CRUD + enmascarado)
# ---------------------------------------------------------------------------
@pytest.fixture
def admin_client(monkeypatch, tmp_path: Path):
    registry = TenantRegistry(tmp_path / "tenants.json")
    monkeypatch.setattr("app.api.admin.get_tenant_registry", lambda: registry)
    monkeypatch.setattr(
        "app.api.admin.get_settings",
        lambda: SimpleNamespace(admin_api_key="clave-muy-secreta"),
    )
    return TestClient(app)


def _auth(headers=None):
    return {"X-Admin-Key": "clave-muy-secreta", **(headers or {})}


def test_admin_requires_key(admin_client) -> None:
    assert admin_client.get("/api/admin/tenants").status_code == 401
    assert (
        admin_client.get("/api/admin/tenants", headers={"X-Admin-Key": "mala"}).status_code
        == 401
    )


def test_admin_crud_and_secret_masking(admin_client) -> None:
    # Crear
    r = admin_client.post(
        "/api/admin/tenants",
        headers=_auth(),
        json={"id": "juan", "name": "Juan", "phone_number_id": "111", "access_token": "TOKEN_SECRETO"},
    )
    assert r.status_code == 201
    body = r.json()
    # El token nunca se devuelve
    assert "access_token" not in body
    assert body["access_token_configured"] is True
    assert body["id"] == "juan"

    # Listar (enmascarado)
    r = admin_client.get("/api/admin/tenants", headers=_auth())
    assert r.status_code == 200
    assert all("access_token" not in t for t in r.json())

    # Actualizar perfil de bot
    r = admin_client.put(
        "/api/admin/tenants/juan",
        headers=_auth(),
        json={"greeting": "Hola Juan-bot!", "enabled": False},
    )
    assert r.status_code == 200
    assert r.json()["greeting"] == "Hola Juan-bot!"
    assert r.json()["enabled"] is False

    # Duplicado -> 409
    r = admin_client.post(
        "/api/admin/tenants",
        headers=_auth(),
        json={"id": "juan", "phone_number_id": "222"},
    )
    assert r.status_code == 409

    # Eliminar -> 204
    r = admin_client.delete("/api/admin/tenants/juan", headers=_auth())
    assert r.status_code == 204
    assert admin_client.get("/api/admin/tenants/juan", headers=_auth()).status_code == 404


def test_admin_invalid_id_rejected(admin_client) -> None:
    r = admin_client.post(
        "/api/admin/tenants", headers=_auth(), json={"id": "ID CON ESPACIOS"}
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Perfil de bot por tenant
# ---------------------------------------------------------------------------
def test_bot_settings_from_tenant_overrides() -> None:
    tenant = SimpleNamespace(
        greeting="Hola personalizado",
        human_paused_reply="",
        handoff_reply="Habla con el asesor",
        lead_done_reply="",
        lead_questions={"lead_ciudad": "¿Cuál es tu ciudad?"},
    )
    bs = BotSettings.from_tenant(tenant)
    assert bs.greeting == "Hola personalizado"
    assert bs.handoff_reply == "Habla con el asesor"
    # Los no definidos heredan el default
    assert bs.human_paused_reply != ""
    assert bs.lead_done_reply != ""
    # Pregunta sobreescrita + resto por defecto
    assert bs.lead_questions["lead_ciudad"] == "¿Cuál es tu ciudad?"
    assert bs.lead_questions["lead_tipo"] == LEAD_QUESTIONS["lead_tipo"]


def test_registry_persists_atomically(tmp_path: Path) -> None:
    file = tmp_path / "tenants.json"
    registry = TenantRegistry(file)
    registry.create("juan", {"name": "Juan", "phone_number_id": "111"})
    # Recargar desde disco y verificar que persistió
    registry2 = TenantRegistry(file)
    assert registry2.get("juan") is not None
    assert registry2.get("juan").name == "Juan"
    # Sin archivo temporal residual
    assert not file.with_suffix(".json.tmp").exists()
