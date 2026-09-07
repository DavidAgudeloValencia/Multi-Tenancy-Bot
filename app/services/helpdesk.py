"""Servicio del helpdesk (panel de agentes).

Operaciones del agente sobre tickets nativos: listar, ver detalle (histórico +
notas), claim/release con lock TTL, transferencia, notas internas y respuesta
al cliente (que se envía por WhatsApp y queda en el histórico).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db import get_session_factory
from app.models import ConversationMessage, Ticket, TicketNote
from app.services import whatsapp as whatsapp_service
from app.services.tenants import get_tenant_registry

logger = logging.getLogger("multibot.helpdesk")


class HelpdeskError(Exception):
    """Error operativo del helpdesk (no encontrado, no dueño, ya reclamado...)."""


class AlreadyClaimed(HelpdeskError):
    """El ticket ya está reclamado por otro agente dentro del TTL."""

    def __init__(self, owner: str) -> None:
        self.owner = owner
        super().__init__(f"Ticket ya reclamado por {owner}")


class NotOwner(HelpdeskError):
    """La operación exige ser el agente dueño del ticket."""


def _ticket_dict(t: Ticket) -> dict:
    return {
        "ticket_id": str(t.id),
        "tenant_id": t.tenant_id,
        "conversation_id": t.conversation_id,
        "subject": t.subject,
        "status": t.status,
        "priority": t.priority,
        "assigned_to": t.assigned_to,
        "tags": t.tags or [],
        "meta": t.meta or {},
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


class HelpdeskService:
    """Casos de uso del agente sobre el helpdesk nativo."""

    def __init__(
        self,
        session_factory: Any | None = None,
        send_message: Any | None = None,
    ) -> None:
        self._sf = session_factory or get_session_factory()
        self._send_message = send_message or whatsapp_service.send_text_message

    # ------------------------------------------------------------------
    async def list_tickets(self, tenant_id: str, status: str | None = None) -> list[dict]:
        async with self._sf() as session:
            query = (
                select(Ticket)
                .where(Ticket.tenant_id == tenant_id)
                .order_by(Ticket.updated_at.desc())
            )
            if status:
                query = query.where(Ticket.status == status)
            rows = (await session.execute(query)).scalars().all()
            return [_ticket_dict(t) for t in rows]

    async def get_detail(self, tenant_id: str, ticket_id: str) -> dict | None:
        async with self._sf() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if ticket is None or ticket.tenant_id != tenant_id:
                return None

            messages = (
                await session.execute(
                    select(ConversationMessage)
                    .where(
                        ConversationMessage.tenant_id == tenant_id,
                        ConversationMessage.conversation_id == ticket.conversation_id,
                    )
                    .order_by(ConversationMessage.id)
                )
            ).scalars().all()
            notes = (
                await session.execute(
                    select(TicketNote)
                    .where(TicketNote.ticket_id == ticket.id)
                    .order_by(TicketNote.id)
                )
            ).scalars().all()

            detail = _ticket_dict(ticket)
            detail["messages"] = [
                {
                    "direction": m.direction,
                    "sender": m.sender,
                    "body": m.body,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ]
            detail["notes"] = [
                {
                    "author": n.author,
                    "body": n.body,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                }
                for n in notes
            ]
            return detail

    # ------------------------------------------------------------------
    async def claim(self, tenant_id: str, ticket_id: str, agent_email: str) -> dict:
        """Reclama el ticket para un agente (respeta el lock TTL)."""
        now = datetime.now(timezone.utc)
        ttl = get_settings().claim_ttl_seconds
        async with self._sf() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if ticket is None or ticket.tenant_id != tenant_id:
                raise HelpdeskError("Ticket no encontrado")

            if ticket.assigned_to and ticket.assigned_to != agent_email:
                assigned_at = ticket.assigned_at
                if assigned_at is not None and assigned_at.tzinfo is None:
                    # SQLite devuelve naive; lo tratamos como UTC.
                    assigned_at = assigned_at.replace(tzinfo=timezone.utc)
                if assigned_at is not None and (now - assigned_at) < timedelta(
                    seconds=ttl
                ):
                    raise AlreadyClaimed(ticket.assigned_to)

            ticket.assigned_to = agent_email
            ticket.assigned_at = now
            if ticket.status != "closed":
                ticket.status = "open"
            await session.commit()
            return _ticket_dict(ticket)

    async def release(self, tenant_id: str, ticket_id: str, agent_email: str) -> dict:
        """Libera el ticket (solo el dueño)."""
        async with self._sf() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if ticket is None or ticket.tenant_id != tenant_id:
                raise HelpdeskError("Ticket no encontrado")
            if ticket.assigned_to and ticket.assigned_to != agent_email:
                raise NotOwner("Solo el agente dueño puede liberarlo")
            ticket.assigned_to = ""
            ticket.assigned_at = None
            await session.commit()
            return _ticket_dict(ticket)

    async def transfer(
        self,
        tenant_id: str,
        ticket_id: str,
        to_agent: str,
        note: str,
        author: str,
    ) -> dict:
        """Transfiere el ticket a otro agente dejando una nota de contexto."""
        async with self._sf() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if ticket is None or ticket.tenant_id != tenant_id:
                raise HelpdeskError("Ticket no encontrado")
            ticket.assigned_to = to_agent
            ticket.assigned_at = datetime.now(timezone.utc)
            session.add(
                TicketNote(
                    ticket_id=ticket.id,
                    author=author,
                    body=f"Transferido a {to_agent}: {note}",
                )
            )
            await session.commit()
            return _ticket_dict(ticket)

    async def mark_pending(
        self, tenant_id: str, conversation_id: str, note: str
    ) -> dict | None:
        """Marca el ticket como pendiente de humano y deja una nota de contexto.

        Usado en el handoff bot→humano. Devuelve None si no existe ticket.
        """
        async with self._sf() as session:
            ticket = (
                await session.execute(
                    select(Ticket).where(
                        Ticket.tenant_id == tenant_id,
                        Ticket.conversation_id == conversation_id,
                    )
                )
            ).scalar_one_or_none()
            if ticket is None:
                return None
            ticket.status = "pending"
            session.add(TicketNote(ticket_id=ticket.id, author="bot", body=note))
            await session.commit()
            logger.info(
                "Ticket %s marcado como pendiente (handoff) en %s/%s",
                ticket.id, tenant_id, conversation_id,
            )
            return _ticket_dict(ticket)

    async def add_note(
        self, tenant_id: str, ticket_id: str, note: str, author: str
    ) -> dict:
        async with self._sf() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if ticket is None or ticket.tenant_id != tenant_id:
                raise HelpdeskError("Ticket no encontrado")
            session.add(TicketNote(ticket_id=ticket.id, author=author, body=note))
            await session.commit()
            return {"status": "ok"}

    async def reply(
        self, tenant_id: str, ticket_id: str, message_text: str, author: str
    ) -> dict:
        """Envía la respuesta del agente por WhatsApp y la registra."""
        async with self._sf() as session:
            ticket = await session.get(Ticket, int(ticket_id))
            if ticket is None or ticket.tenant_id != tenant_id:
                raise HelpdeskError("Ticket no encontrado")

        tenant = get_tenant_registry().get(tenant_id)
        if tenant is None:
            raise HelpdeskError(f"Agente (tenant) '{tenant_id}' no encontrado")

        await self._send_message(
            ticket.conversation_id,
            message_text,
            phone_number_id=tenant.phone_number_id,
            access_token=tenant.effective_token,
        )

        async with self._sf() as session:
            session.add(
                ConversationMessage(
                    tenant_id=tenant_id,
                    conversation_id=ticket.conversation_id,
                    direction="out",
                    sender=author,
                    body=message_text,
                )
            )
            session.add(
                TicketNote(
                    ticket_id=ticket.id,
                    author=author,
                    body=f"Respuesta enviada al cliente: {message_text[:120]}",
                )
            )
            await session.commit()

        logger.info("Respuesta del agente %s enviada en ticket %s", author, ticket_id)
        return {"status": "ok"}


_service: HelpdeskService | None = None


def get_helpdesk_service() -> HelpdeskService:
    global _service
    if _service is None:
        _service = HelpdeskService()
    return _service
