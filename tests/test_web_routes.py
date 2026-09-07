"""Pruebas de rutas web y de salud: Landing page, Health check y Paneles estáticos."""

from __future__ import annotations

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_landing_page_serves_html() -> None:
    """La ruta raíz '/' debe responder con HTML (Landing Page)."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Multi-Tenancy Bot" in response.text
    assert "Panel de Asesores" in response.text


def test_health_check_endpoint() -> None:
    """La ruta '/health' debe retornar JSON de estado del servicio."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_admin_and_agent_static_pages() -> None:
    """Las rutas de paneles /admin/ y /agent/ deben servir sus respectivas interfaces."""
    admin_res = client.get("/admin/")
    assert admin_res.status_code == 200
    assert "Multi-Tenancy Bot" in admin_res.text

    agent_res = client.get("/agent/")
    assert agent_res.status_code == 200
    assert "Panel de Asesores" in agent_res.text
