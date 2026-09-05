"""Pruebas de rate limiting y subida segura de PDFs (panel de administración)."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate

from app.core.ratelimit import RateLimiter
from app.services.tenants import TenantRegistry
from main import app


def _make_pdf_bytes(text: str = "Documento de prueba") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    doc.build([Paragraph(text, getSampleStyleSheet()["BodyText"])])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
def test_rate_limiter_limits() -> None:
    limiter = RateLimiter(limit=3, window_seconds=60)
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False  # 4ª petición -> rechazada
    assert limiter.allow("5.6.7.8") is True  # otra IP no se ve afectada


# ---------------------------------------------------------------------------
# Subida de PDFs
# ---------------------------------------------------------------------------
@pytest.fixture
def upload_client(monkeypatch, tmp_path: Path):
    registry = TenantRegistry(tmp_path / "tenants.json")
    registry.create(
        "juan",
        {
            "phone_number_id": "111",
            "knowledge_dir": str(tmp_path / "knowledge" / "juan"),
        },
    )
    monkeypatch.setattr("app.api.admin.get_tenant_registry", lambda: registry)
    monkeypatch.setattr(
        "app.api.admin.get_settings",
        lambda: SimpleNamespace(admin_api_key="clave", knowledge_dir=str(tmp_path / "knowledge")),
    )
    return TestClient(app)


def _auth():
    return {"X-Admin-Key": "clave"}


def test_upload_valid_pdf(upload_client) -> None:
    pdf = _make_pdf_bytes()
    r = upload_client.post(
        "/api/admin/tenants/juan/documents",
        headers=_auth(),
        files=[("files", ("guia.pdf", pdf, "application/pdf"))],
    )
    assert r.status_code == 201
    assert r.json()["saved"] == ["guia.pdf"]


def test_upload_rejects_non_pdf(upload_client) -> None:
    r = upload_client.post(
        "/api/admin/tenants/juan/documents",
        headers=_auth(),
        files=[("files", ("malo.pdf", b"esto no es un pdf", "application/pdf"))],
    )
    assert r.status_code == 415


def test_upload_rejects_wrong_extension(upload_client) -> None:
    r = upload_client.post(
        "/api/admin/tenants/juan/documents",
        headers=_auth(),
        files=[("files", ("virus.exe", _make_pdf_bytes(), "application/octet-stream"))],
    )
    assert r.status_code == 400


def test_upload_sanitizes_path_traversal(upload_client) -> None:
    pdf = _make_pdf_bytes()
    r = upload_client.post(
        "/api/admin/tenants/juan/documents",
        headers=_auth(),
        files=[("files", ("../../etc/passwd.pdf", pdf, "application/pdf"))],
    )
    assert r.status_code == 201
    # El nombre se limpió: no quedó ruta, solo el basename sanitizado.
    assert r.json()["saved"] == ["passwd.pdf"]


def test_upload_requires_auth(upload_client) -> None:
    r = upload_client.post(
        "/api/admin/tenants/juan/documents",
        files=[("files", ("x.pdf", _make_pdf_bytes(), "application/pdf"))],
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Disparador de ingesta
# ---------------------------------------------------------------------------
def test_ingest_tenant_endpoint(monkeypatch, tmp_path: Path):
    registry = TenantRegistry(tmp_path / "tenants.json")
    registry.create("juan", {"phone_number_id": "111"})
    monkeypatch.setattr("app.api.admin.get_tenant_registry", lambda: registry)
    monkeypatch.setattr(
        "app.api.admin.get_settings",
        lambda: SimpleNamespace(admin_api_key="clave", knowledge_dir=str(tmp_path / "knowledge")),
    )
    monkeypatch.setattr(
        "app.services.ingestion.ingest_documents",
        lambda **kwargs: {"status": "ok", "chunks": 4, "pdfs": 1},
    )
    client = TestClient(app)
    r = client.post("/api/admin/tenants/juan/ingest", headers=_auth())
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
