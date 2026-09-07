"""Helpdesk nativo (nuestro propio CRM) — implementa `ICrmAdapter`.

No integra ningún proveedor externo: los tickets, notas, asignaciones y
estados viven en nuestras propias tablas (`tickets`, `ticket_notes`).
Implementa el MISMO contrato que tendría un Zendesk/Freshdesk, tomado como
referencia de funcionalidades (assignee, estado, prioridad, notas internas).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.crm.base import ICrmAdapter, TicketMeta, TicketRef
from app.db import get_session_factory
from app.models import Ticket, TicketNote, _utcnow


class NativeCrmAdapter(ICrmAdapter):
    """CRM nativo respaldado por la base de datos de la plataforma."""

    name = "native"

    def __init__(self, session_factory: Any | None = None) -> None:
        self._sf = session_factory or get_session_factory()

    async def create_ticket(
        self, tenant_id: str, meta: TicketMeta, initial_message: str
    ) -> TicketRef:
        async with self._sf() as session:
            ticket = Ticket(
                tenant_id=tenant_id,
                conversation_id=meta.conversation_id,
                subject=meta.subject or initial_message[:80],
                tags=meta.tags,
                meta={**meta.metadata, "intent": meta.intent, "requester": meta.requester},
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            return TicketRef(ticket_id=str(ticket.id), url=f"/admin/tickets/{ticket.id}")

    async def update_ticket(
        self,
        tenant_id: str,
        ticket_id: str,
        message: str,
        author: str,
        metadata: dict | None = None,
    ) -> str:
        async with self._sf() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if ticket is None:
                raise KeyError(ticket_id)
            ticket.updated_at = _utcnow()
            await session.commit()
            return ticket.status

    async def add_internal_note(
        self, tenant_id: str, ticket_id: str, note: str, author: str
    ) -> str:
        async with self._sf() as session:
            session.add(TicketNote(ticket_id=int(ticket_id), author=author, body=note))
            await session.commit()
            return "ok"

    async def assign_agent(
        self, tenant_id: str, ticket_id: str, agent_id: str
    ) -> str:
        async with self._sf() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if ticket is None:
                raise KeyError(ticket_id)
            ticket.assigned_to = agent_id
            await session.commit()
            return "ok"

    async def search_tickets(self, tenant_id: str, query: str) -> list[dict]:
        async with self._sf() as session:
            rows = (
                await session.execute(
                    select(Ticket).where(
                        Ticket.tenant_id == tenant_id,
                        Ticket.subject.ilike(f"%{query}%"),
                    )
                )
            ).scalars().all()
            return [
                {
                    "ticket_id": str(t.id),
                    "tenant_id": t.tenant_id,
                    "conversation_id": t.conversation_id,
                    "subject": t.subject,
                    "status": t.status,
                    "priority": t.priority,
                    "assigned_to": t.assigned_to,
                }
                for t in rows
            ]

    # --- Helpers para el panel / tests ---
    async def list_tickets(self, tenant_id: str) -> list[dict]:
        async with self._sf() as session:
            rows = (
                await session.execute(
                    select(Ticket)
                    .where(Ticket.tenant_id == tenant_id)
                    .order_by(Ticket.updated_at.desc())
                )
            ).scalars().all()
            return [
                {
                    "ticket_id": str(t.id),
                    "conversation_id": t.conversation_id,
                    "subject": t.subject,
                    "status": t.status,
                    "priority": t.priority,
                    "assigned_to": t.assigned_to,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                }
                for t in rows
            ]
