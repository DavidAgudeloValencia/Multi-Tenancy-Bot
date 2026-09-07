"""Pruebas del panel de agentes (helpdesk): claim/release, transferencia,
notas internas y respuesta por WhatsApp (con envío falso)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.crm.native import NativeCrmAdapter
from app.db import Base
from app.models import User
from app.services.helpdesk import (
    AlreadyClaimed,
    HelpdeskService,
    NotOwner,
)
from app.services.tickets import TicketingService


@pytest.fixture
async def hd(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'hd.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    ticketing = TicketingService(
        adapter=NativeCrmAdapter(factory), session_factory=factory
    )
    send_calls: list = []

    async def fake_send(to, text, phone_number_id=None, access_token=None):
        send_calls.append((to, text, phone_number_id, access_token))
        return {"messages": [{"id": "wamid.X"}]}

    service = HelpdeskService(session_factory=factory, send_message=fake_send)
    yield service, ticketing, factory, send_calls
    await engine.dispose()


async def _make_ticket(ticketing, tenant="t1", conv="573001234567"):
    return await ticketing.ensure_ticket(tenant, conv, "hola, necesito ayuda", intent="soporte")


async def _add_user(factory, email, role="agent", active=True):
    async with factory() as session:
        session.add(User(email=email, name=email, role=role, active=active))
        await session.commit()


async def test_claim_and_conflict(hd) -> None:
    service, ticketing, factory, _ = hd
    ticket = await _make_ticket(ticketing)

    claimed = await service.claim("t1", ticket["ticket_id"], "ana@x.com")
    assert claimed["assigned_to"] == "ana@x.com"

    with pytest.raises(AlreadyClaimed):
        await service.claim("t1", ticket["ticket_id"], "bea@x.com")

    listed = await service.list_tickets("t1")
    assert listed[0]["assigned_to"] == "ana@x.com"


async def test_claim_after_ttl_is_reassignable(hd, monkeypatch) -> None:
    service, ticketing, factory, _ = hd
    monkeypatch.setattr(
        "app.services.helpdesk.get_settings",
        lambda: SimpleNamespace(claim_ttl_seconds=0),
    )
    ticket = await _make_ticket(ticketing)
    await service.claim("t1", ticket["ticket_id"], "ana@x.com")
    # TTL 0 -> el claim está expirado de inmediato, otro agente puede tomarlo
    claimed = await service.claim("t1", ticket["ticket_id"], "bea@x.com")
    assert claimed["assigned_to"] == "bea@x.com"


async def test_release_owner_only(hd) -> None:
    service, ticketing, factory, _ = hd
    ticket = await _make_ticket(ticketing)
    await service.claim("t1", ticket["ticket_id"], "ana@x.com")

    with pytest.raises(NotOwner):
        await service.release("t1", ticket["ticket_id"], "bea@x.com")

    released = await service.release("t1", ticket["ticket_id"], "ana@x.com")
    assert released["assigned_to"] == ""


async def test_transfer_and_note(hd) -> None:
    service, ticketing, factory, _ = hd
    ticket = await _make_ticket(ticketing)
    await service.claim("t1", ticket["ticket_id"], "ana@x.com")

    transferred = await service.transfer(
        "t1", ticket["ticket_id"], "carla@x.com", "especialista en autos", "ana@x.com"
    )
    assert transferred["assigned_to"] == "carla@x.com"

    detail = await service.get_detail("t1", ticket["ticket_id"])
    assert any("Transferido a carla@x.com" in n["body"] for n in detail["notes"])


async def test_reply_sends_and_records(hd, monkeypatch) -> None:
    service, ticketing, factory, send_calls = hd
    monkeypatch.setattr(
        "app.services.helpdesk.get_tenant_registry",
        lambda: SimpleNamespace(
            get=lambda tid: SimpleNamespace(
                phone_number_id="111", effective_token="TOKEN"
            )
            if tid == "t1"
            else None
        ),
    )
    ticket = await _make_ticket(ticketing)

    await service.reply("t1", ticket["ticket_id"], "Ya lo reviso, un momento", "ana@x.com")

    assert send_calls == [
        ("573001234567", "Ya lo reviso, un momento", "111", "TOKEN")
    ]

    detail = await service.get_detail("t1", ticket["ticket_id"])
    assert detail["messages"][-1]["direction"] == "out"
    assert detail["messages"][-1]["body"] == "Ya lo reviso, un momento"


async def test_mark_pending_on_handoff(hd) -> None:
    service, ticketing, factory, _ = hd
    await _make_ticket(ticketing)  # crea ticket + mapping

    result = await service.mark_pending(
        "t1", "573001234567", "Handoff bot→humano (humano). Perfil: {}"
    )
    assert result is not None
    assert result["status"] == "pending"

    detail = await service.get_detail("t1", result["ticket_id"])
    assert detail["status"] == "pending"
    assert any("Handoff bot→humano" in n["body"] for n in detail["notes"])


async def test_metrics(hd) -> None:
    service, ticketing, factory, _ = hd
    await _make_ticket(ticketing)  # open
    await ticketing.ensure_ticket("t1", "573009999999", "otro caso")  # open
    await service.mark_pending("t1", "573001234567", "handoff")  # pending

    metrics = await service.metrics("t1")
    assert metrics["total"] == 2
    assert metrics["open"] == 1
    assert metrics["pending"] == 1
    assert metrics["closed"] == 0


async def test_audit_log_records_actions(hd) -> None:
    service, ticketing, factory, _ = hd
    ticket = await _make_ticket(ticketing)

    await service.claim("t1", ticket["ticket_id"], "ana@x.com")
    await service.transfer(
        "t1", ticket["ticket_id"], "bea@x.com", "especialista", "ana@x.com"
    )
    await service.release("t1", ticket["ticket_id"], "bea@x.com")

    audit = await service.list_audit("t1")
    actions = [a["action"] for a in audit]
    assert "claim" in actions
    assert "transfer" in actions
    assert "release" in actions
    # ordenado: el más reciente primero
    assert audit[0]["action"] == "release"
    assert audit[0]["actor"] == "bea@x.com"


async def test_audit_log_records_handoff(hd) -> None:
    service, ticketing, factory, _ = hd
    await _make_ticket(ticketing)
    await service.mark_pending("t1", "573001234567", "handoff")

    audit = await service.list_audit("t1")
    assert any(a["action"] == "handoff" and a["actor"] == "bot" for a in audit)


async def test_auto_assign_least_busy(hd) -> None:
    service, ticketing, factory, _ = hd
    await _add_user(factory, "ana@x.com")
    await _add_user(factory, "bea@x.com")
    await _add_user(factory, "carla@x.com", active=False)  # inactiva: no cuenta

    t1 = await _make_ticket(ticketing, conv="573001111111")
    t2 = await _make_ticket(ticketing, conv="573002222222")

    await service.claim("t1", t1["ticket_id"], "ana@x.com")  # ana con carga 1
    assigned = await service.auto_assign("t1", t2["ticket_id"])
    assert assigned["assigned_to"] == "bea@x.com"  # la menos ocupada


async def test_auto_assign_no_agents(hd) -> None:
    service, ticketing, factory, _ = hd
    ticket = await _make_ticket(ticketing)
    assert await service.auto_assign("t1", ticket["ticket_id"]) is None


async def test_auto_assign_respects_existing_owner(hd) -> None:
    service, ticketing, factory, _ = hd
    await _add_user(factory, "ana@x.com")
    ticket = await _make_ticket(ticketing)
    await service.claim("t1", ticket["ticket_id"], "ana@x.com")
    assigned = await service.auto_assign("t1", ticket["ticket_id"])
    assert assigned["assigned_to"] == "ana@x.com"  # no cambia al dueño actual
