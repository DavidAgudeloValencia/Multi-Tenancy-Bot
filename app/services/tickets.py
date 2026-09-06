"""Servicio de tickets (plataforma de atención, Sprint 0).

Une el flujo entrante con el CRM y la persistencia:
  mensaje entrante -> mapping conversación↔ticket -> create/update en CRM
  + histórico en la base relacional.

Solo depende de `ICrmAdapter`, nunca de un proveedor concreto.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.crm.base import ICrmAdapter, TicketMeta
from app.crm.mock import MockCrmAdapter
from app.db import get_session_factory
from app.models import ConversationMessage, TicketMapping, _utcnow

logger = logging.getLogger("multibot.tickets")

# Singleton del adaptador mock (conserva estado por proceso en demo/tests).
_MOCK = MockCrmAdapter()


def get_crm_adapter() -> ICrmAdapter:
    """Devuelve el adaptador CRM según `CRM_PROVIDER` (mock | zendesk | ...)."""
    provider = get_settings().crm_provider.lower()
    if provider == "mock":
        return _MOCK
    if provider in ("zendesk", "hubspot", "freshdesk"):
        # Sprint 1: aquí se instancian los adaptadores reales.
        raise NotImplementedError(f"Adaptador '{provider}' aún no implementado")
    raise ValueError(f"Proveedor CRM desconocido: '{provider}'")


class TicketingService:
    """Crea/actualiza tickets y persiste el mapping por conversación."""

    def __init__(
        self,
        adapter: ICrmAdapter | None = None,
        session_factory: Any | None = None,
    ) -> None:
        self._adapter = adapter or get_crm_adapter()
        self._session_factory = session_factory or get_session_factory()

    async def ensure_ticket(
        self,
        tenant_id: str,
        conversation_id: str,
        message_text: str,
        intent: str = "",
        requester: str | None = None,
    ) -> dict:
        """Crea el ticket si no existe; si existe, actualiza el CRM.

        Devuelve: {"ticket_id", "ticket_url", "created"}.
        """
        requester = requester or conversation_id

        async with self._session_factory() as session:
            result = await session.execute(
                select(TicketMapping).where(
                    TicketMapping.tenant_id == tenant_id,
                    TicketMapping.conversation_id == conversation_id,
                )
            )
            mapping = result.scalar_one_or_none()

            # Histórico del mensaje entrante (siempre).
            session.add(
                ConversationMessage(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    direction="in",
                    sender=requester,
                    body=message_text,
                )
            )

            created = False
            if mapping is None:
                meta = TicketMeta(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    requester=requester,
                    intent=intent,
                    subject=message_text[:80],
                    tags=[f"intent:{intent or 'unknown'}", "channel:whatsapp"],
                )
                ref = await self._adapter.create_ticket(tenant_id, meta, message_text)
                mapping = TicketMapping(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    ticket_id=ref.ticket_id,
                    ticket_url=ref.url,
                    status="open",
                )
                session.add(mapping)
                created = True
            else:
                await self._adapter.update_ticket(
                    tenant_id,
                    mapping.ticket_id,
                    message_text,
                    author=requester,
                )
                mapping.updated_at = _utcnow()

            await session.commit()
            logger.info(
                "Ticket %s para %s/%s (creado=%s)",
                mapping.ticket_id,
                tenant_id,
                conversation_id,
                created,
            )
            return {
                "ticket_id": mapping.ticket_id,
                "ticket_url": mapping.ticket_url,
                "created": created,
            }

    async def record_outbound(
        self,
        tenant_id: str,
        conversation_id: str,
        message_text: str,
        sender: str = "bot",
    ) -> None:
        """Registra una respuesta (bot o agente) en el histórico."""
        async with self._session_factory() as session:
            session.add(
                ConversationMessage(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    direction="out",
                    sender=sender,
                    body=message_text,
                )
            )
            await session.commit()

    async def get_mapping(
        self, tenant_id: str, conversation_id: str
    ) -> TicketMapping | None:
        """Devuelve el mapping (o None) de una conversación."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TicketMapping).where(
                    TicketMapping.tenant_id == tenant_id,
                    TicketMapping.conversation_id == conversation_id,
                )
            )
            return result.scalar_one_or_none()


_service: TicketingService | None = None


def get_ticketing_service() -> TicketingService:
    """Devuelve el servicio de tickets único de la app."""
    global _service
    if _service is None:
        _service = TicketingService()
    return _service
