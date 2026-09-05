"""Pruebas del multi-tenant (Fase 7) — sin llamar a APIs ni a Redis.

Cubren: carga del registro de agentes, resolución por phone_number_id,
propiedades efectivas (colección/carpeta/token) y aislamiento de sesiones
entre tenants (PrefixedSessionStore).

Ejecutar con:  pytest -q
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.session import MemorySessionStore, PrefixedSessionStore
from app.services.tenants import TenantRegistry


def _write_tenants(tmp_path: Path, tenants: list[dict]) -> Path:
    file = tmp_path / "tenants.json"
    file.write_text(
        json.dumps({"tenants": tenants}, ensure_ascii=False), encoding="utf-8"
    )
    return file


def test_registry_loads_and_resolves(tmp_path: Path) -> None:
    file = _write_tenants(
        tmp_path,
        [
            {"id": "david", "name": "David", "phone_number_id": "111"},
            {
                "id": "ana",
                "phone_number_id": "222",
                "collection": "kb_ana",
                "knowledge_dir": "knowledge/ana",
            },
        ],
    )
    registry = TenantRegistry(file)

    assert len(registry.all()) == 2
    assert registry.by_phone_number_id("111").id == "david"
    assert registry.by_phone_number_id("999") is None
    assert registry.get("ana").effective_collection == "kb_ana"
    assert registry.get("ana").effective_knowledge_dir == "knowledge/ana"
    # Colección y carpeta por defecto derivadas del id
    assert registry.get("david").effective_collection == "multibot_kb_david"
    assert registry.get("david").effective_knowledge_dir == "knowledge/david"


def test_registry_missing_file_is_empty(tmp_path: Path) -> None:
    registry = TenantRegistry(tmp_path / "no_existe.json")
    assert registry.all() == []
    assert registry.by_phone_number_id("x") is None


def test_effective_token_fallback(monkeypatch, tmp_path: Path) -> None:
    file = _write_tenants(tmp_path, [{"id": "david", "access_token": ""}])
    monkeypatch.setattr(
        "app.services.tenants.get_settings",
        lambda: SimpleNamespace(whatsapp_access_token="TOKEN_GLOBAL"),
    )
    registry = TenantRegistry(file)
    assert registry.get("david").effective_token == "TOKEN_GLOBAL"

    file2 = _write_tenants(tmp_path, [{"id": "ana", "access_token": "TOKEN_ANA"}])
    registry2 = TenantRegistry(file2)
    assert registry2.get("ana").effective_token == "TOKEN_ANA"


def test_routing_by_metadata_phone_number_id(tmp_path: Path) -> None:
    """El webhook resuelve el agente con metadata.phone_number_id."""
    file = _write_tenants(
        tmp_path, [{"id": "david", "phone_number_id": "123456789012345"}]
    )
    registry = TenantRegistry(file)
    metadata = {"phone_number_id": "123456789012345"}
    tenant = registry.by_phone_number_id(metadata["phone_number_id"])
    assert tenant is not None
    assert tenant.id == "david"


async def test_prefixed_session_store_isolates_tenants() -> None:
    store = MemorySessionStore(default_ttl=60)
    david = PrefixedSessionStore(store, "david")
    ana = PrefixedSessionStore(store, "ana")

    await david.set("573001111111", {"state": "lead_tipo", "lead": {}})

    # Ana no ve la sesión de David (mismo Redis, keys con prefijo).
    assert await ana.get("573001111111") is None
    assert await david.get("573001111111") == {"state": "lead_tipo", "lead": {}}


def test_ingest_resolves_tenant_dirs(tmp_path: Path, monkeypatch) -> None:
    """La ingesta con --tenant usa la carpeta y colección del agente."""
    from app.services import ingestion

    fake_tenant = SimpleNamespace(
        effective_knowledge_dir="knowledge/david",
        effective_collection="multibot_kb_david",
    )
    monkeypatch.setattr(
        "app.services.tenants.get_tenant_registry",
        lambda: SimpleNamespace(
            get=lambda tid: fake_tenant if tid == "david" else None
        ),
    )

    # Sin PDFs en knowledge/david -> error claro (sin llamar a OpenAI).
    result = ingestion.ingest_documents(
        tenant_id="david",
        persist_dir=str(tmp_path / "chroma"),
        embedding_function=None,
    )
    assert result["status"] == "error"
    assert "david" in result["detail"]

    # Tenant inexistente -> error de configuración.
    result = ingestion.ingest_documents(tenant_id="zzz", persist_dir=str(tmp_path / "c"))
    assert result["status"] == "error"
    assert "no existe" in result["detail"]
