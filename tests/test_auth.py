"""Pruebas de autenticación: JWT (emitir/validar) y login con Google (con dobles)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import create_access_token, decode_access_token
from app.db import Base
from main import app


@pytest.fixture
def auth_settings(monkeypatch):
    monkeypatch.setattr(
        "app.core.auth.get_settings",
        lambda: SimpleNamespace(auth_jwt_secret="secreto", auth_token_hours=12),
    )


def test_jwt_roundtrip(auth_settings) -> None:
    token = create_access_token({"email": "ana@x.com", "name": "Ana", "role": "agent"})
    payload = decode_access_token(token)
    assert payload["email"] == "ana@x.com"
    assert payload["role"] == "agent"


def test_jwt_rejects_invalid_token(auth_settings) -> None:
    with pytest.raises(HTTPException) as exc:
        decode_access_token("token.invalido")
    assert exc.value.status_code == 401


@pytest.fixture
async def auth_client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.core.auth.get_settings",
        lambda: SimpleNamespace(auth_jwt_secret="secreto", auth_token_hours=12),
    )

    async def fake_exchange(code):
        return {"id_token": "id-token"}

    async def fake_verify(id_token):
        return {
            "email": "ana@x.com",
            "name": "Ana",
            "picture": "",
            "sub": "google-sub-1",
            "email_verified": True,
            "aud": "client-id",
        }

    monkeypatch.setattr("app.services.google_auth.exchange_code", fake_exchange)
    monkeypatch.setattr("app.services.google_auth.verify_id_token", fake_verify)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.api.auth.get_session_factory", lambda: factory)

    yield TestClient(app)
    await engine.dispose()


def test_google_callback_issues_token(auth_client) -> None:
    response = auth_client.get("/auth/google/callback", params={"code": "abc"})
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == "ana@x.com"
    assert data["user"]["role"] == "agent"
    assert data["token"]


def test_me_requires_bearer_token(auth_client) -> None:
    assert auth_client.get("/auth/me").status_code == 401

    response = auth_client.get("/auth/google/callback", params={"code": "abc"})
    token = response.json()["token"]

    me = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "ana@x.com"


def test_callback_redirects_with_token_when_state(auth_client) -> None:
    response = auth_client.get(
        "/auth/google/callback", params={"code": "abc", "state": "/agent/"}
    )
    # TestClient sigue el redirect al panel (/agent/) -> 200
    assert response.status_code == 200
    assert response.history  # hubo una redirección previa
    location = response.history[0].headers["location"]
    assert location.startswith("/agent/#token=")
