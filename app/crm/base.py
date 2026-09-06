"""Contrato común de los conectores CRM (ICrmAdapter).

Todos los proveedores (Zendesk, HubSpot, Freshdesk, o el mock) implementan
esta interfaz. El resto de la plataforma depende SOLO de `ICrmAdapter`, nunca
de un proveedor concreto.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TicketMeta:
    """Metadatos de una conversación para crear el ticket."""

    tenant_id: str
    conversation_id: str
    subject: str = ""
    requester: str = ""            # número/whatsapp del cliente
    intent: str = ""               # soporte | venta | humano | saludo
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class TicketRef:
    """Identificador del ticket devuelto por el CRM."""

    ticket_id: str
    url: str = ""


class CrmError(Exception):
    """Error del adaptador CRM (red, auth, rate limit...)."""


class ICrmAdapter(ABC):
    """Interfaz que todo adaptador de CRM debe cumplir."""

    name: str = "base"

    @abstractmethod
    async def create_ticket(
        self, tenant_id: str, meta: TicketMeta, initial_message: str
    ) -> TicketRef:
        """Crea un ticket a partir del primer mensaje entrante."""

    @abstractmethod
    async def update_ticket(
        self,
        tenant_id: str,
        ticket_id: str,
        message: str,
        author: str,
        metadata: dict | None = None,
    ) -> str:
        """Añade/actualiza la conversación del ticket (devuelve estado)."""

    @abstractmethod
    async def add_internal_note(
        self, tenant_id: str, ticket_id: str, note: str, author: str
    ) -> str:
        """Añade una nota interna (visible solo para agentes)."""

    @abstractmethod
    async def assign_agent(
        self, tenant_id: str, ticket_id: str, agent_id: str
    ) -> str:
        """Asigna el ticket a un agente."""

    @abstractmethod
    async def search_tickets(self, tenant_id: str, query: str) -> list[dict]:
        """Busca tickets por texto (para el panel)."""
