"""Pruebas del helpdesk nativo (nuestro propio CRM).

Usan SQLite temporal y `NativeCrmAdapter`, sin proveedores externos.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.crm.base import TicketMeta
from app.crm.native import NativeCrmAdapter
from app.db import Base
from app.models import Ticket, TicketNote
from app.services.tickets import TicketingService


@pytest.fixture
async def native(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'native.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    adapter = NativeCrmAdapter(session_factory=factory)
    svc = TicketingService(adapter=adapter, session_factory=factory)
    yield svc, adapter, factory
    await engine.dispose()


async def test_create_ticket_persists_native_row(native) -> None:
    svc, adapter, factory = native
    r = await svc.ensure_ticket(
        "t1", "573001234567", "Me chocaron", intent="soporte"
    )
    assert r["created"] is True

    async with factory() as s:
        ticket = (
            await s.execute(select(Ticket).where(Ticket.conversation_id == "573001234567"))
        ).scalar_one()
        assert ticket.tenant_id == "t1"
        assert ticket.status == "open"
        assert "intent:soporte" in ticket.tags
        assert ticket.meta["intent"] == "soporte"


async def test_update_reuses_same_ticket(native) -> None:
    svc, adapter, factory = native
    await svc.ensure_ticket("t1", "573001234567", "hola")
    r2 = await svc.ensure_ticket("t1", "573001234567", "otra cosa")
    assert r2["created"] is False

    async with factory() as s:
        count = len((await s.execute(select(Ticket))).scalars().all())
        assert count == 1


async def test_note_and_assign(native) -> None:
    svc, adapter, factory = native
    r = await svc.ensure_ticket("t1", "573001234567", "hola")
    ticket_id = int(r["ticket_id"])

    await adapter.add_internal_note("t1", str(ticket_id), "cliente VIP", "ana@x.com")
    await adapter.assign_agent("t1", str(ticket_id), "ana@x.com")

    async with factory() as s:
        ticket = await s.get(Ticket, ticket_id)
        assert ticket.assigned_to == "ana@x.com"
        notes = (
            await s.execute(select(TicketNote).where(TicketNote.ticket_id == ticket_id))
        ).scalars().all()
        assert len(notes) == 1
        assert notes[0].body == "cliente VIP"


async def test_search_and_list(native) -> None:
    svc, adapter, factory = native
    await svc.ensure_ticket("t1", "573001111111", "siniestro de auto")
    await svc.ensure_ticket("t1", "573002222222", "medico a domicilio")

    hits = await adapter.search_tickets("t1", "siniestro")
    assert len(hits) == 1
    assert hits[0]["conversation_id"] == "573001111111"

    listed = await adapter.list_tickets("t1")
    assert len(listed) == 2
    assert {t["conversation_id"] for t in listed} == {"573001111111", "573002222222"}
