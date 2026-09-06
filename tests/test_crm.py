"""Pruebas de la plataforma de atención (Sprint 0): CRM + tickets.

Usan SQLite en un archivo temporal y `MockCrmAdapter`, sin APIs externas.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.crm.base import TicketMeta
from app.crm.mock import MockCrmAdapter
from app.db import Base
from app.models import ConversationMessage
from app.services.tickets import TicketingService


@pytest.fixture
async def service(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    adapter = MockCrmAdapter()
    svc = TicketingService(adapter=adapter, session_factory=factory)
    yield svc, adapter, factory
    await engine.dispose()


async def test_first_message_creates_ticket(service) -> None:
    svc, adapter, _ = service
    r = await svc.ensure_ticket(
        "t1", "573001234567", "Me chocaron, qué hago?", intent="soporte"
    )
    assert r["created"] is True
    assert r["ticket_id"].startswith("T-")

    mapping = await svc.get_mapping("t1", "573001234567")
    assert mapping is not None and mapping.ticket_id == r["ticket_id"]

    tickets = adapter.all("t1")
    assert len(tickets) == 1
    assert tickets[0]["messages"] == ["Me chocaron, qué hago?"]
    assert tickets[0]["tags"] == ["intent:soporte", "channel:whatsapp"]


async def test_second_message_updates_same_ticket(service) -> None:
    svc, adapter, _ = service
    await svc.ensure_ticket("t1", "573001234567", "hola")
    r2 = await svc.ensure_ticket("t1", "573001234567", "segundo mensaje")
    assert r2["created"] is False
    tickets = adapter.all("t1")
    assert len(tickets) == 1
    assert tickets[0]["messages"] == ["hola", "segundo mensaje"]


async def test_tenants_are_isolated(service) -> None:
    svc, adapter, _ = service
    await svc.ensure_ticket("t1", "573001234567", "a")
    await svc.ensure_ticket("t2", "573001234567", "b")
    assert len(adapter.all("t1")) == 1
    assert len(adapter.all("t2")) == 1

    m1 = await svc.get_mapping("t1", "573001234567")
    m2 = await svc.get_mapping("t2", "573001234567")
    assert m1.ticket_id != m2.ticket_id  # misma conversación, distinto tenant


async def test_record_outbound_persists_history(service) -> None:
    svc, _, factory = service
    await svc.ensure_ticket("t1", "573001234567", "hola")
    await svc.record_outbound("t1", "573001234567", "respuesta bot")

    async with factory() as session:
        rows = (
            await session.execute(
                select(ConversationMessage).order_by(ConversationMessage.id)
            )
        ).scalars().all()
    assert [m.direction for m in rows] == ["in", "out"]
    assert [m.body for m in rows] == ["hola", "respuesta bot"]


async def test_mock_adapter_notes_assign_and_search() -> None:
    adapter = MockCrmAdapter()
    ref = await adapter.create_ticket(
        "t1",
        TicketMeta(tenant_id="t1", conversation_id="c1", subject="siniestro"),
        "hola, me chocaron",
    )
    await adapter.add_internal_note("t1", ref.ticket_id, "cliente frecuente", "agente-1")
    await adapter.assign_agent("t1", ref.ticket_id, "agente-1")

    ticket = adapter.get("t1", ref.ticket_id)
    assert ticket["notes"] == [{"author": "agente-1", "note": "cliente frecuente"}]
    assert ticket["agent_id"] == "agente-1"

    hits = await adapter.search_tickets("t1", "chocaron")
    assert len(hits) == 1
    assert hits[0]["ticket_id"] == ref.ticket_id
