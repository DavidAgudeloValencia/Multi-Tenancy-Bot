"""Adaptador CRM en memoria (demo/desarrollo).

Implementa `ICrmAdapter` sin depender de un proveedor externo, para desarrollar
y probar el flujo completo antes de conectar Zendesk/HubSpot/Freshdesk.
"""

from __future__ import annotations

import itertools

from app.crm.base import ICrmAdapter, TicketMeta, TicketRef


class MockCrmAdapter(ICrmAdapter):
    """Guarda tickets en un dict por proceso (útil en tests y demos)."""

    name = "mock"

    def __init__(self) -> None:
        self._tickets: dict[tuple[str, str], dict] = {}
        self._counter = itertools.count(1)

    async def create_ticket(
        self, tenant_id: str, meta: TicketMeta, initial_message: str
    ) -> TicketRef:
        ticket_id = f"T-{next(self._counter)}"
        self._tickets[(tenant_id, ticket_id)] = {
            "ticket_id": ticket_id,
            "tenant_id": tenant_id,
            "conversation_id": meta.conversation_id,
            "subject": meta.subject or initial_message[:80],
            "messages": [initial_message],
            "notes": [],
            "agent_id": None,
            "status": "open",
            "tags": meta.tags,
        }
        return TicketRef(ticket_id=ticket_id, url=f"mock://tickets/{ticket_id}")

    async def update_ticket(
        self,
        tenant_id: str,
        ticket_id: str,
        message: str,
        author: str,
        metadata: dict | None = None,
    ) -> str:
        ticket = self._tickets.get((tenant_id, ticket_id))
        if ticket is None:
            raise KeyError(ticket_id)
        ticket["messages"].append(message)
        return ticket["status"]

    async def add_internal_note(
        self, tenant_id: str, ticket_id: str, note: str, author: str
    ) -> str:
        ticket = self._tickets.get((tenant_id, ticket_id))
        if ticket is None:
            raise KeyError(ticket_id)
        ticket["notes"].append({"author": author, "note": note})
        return "ok"

    async def assign_agent(
        self, tenant_id: str, ticket_id: str, agent_id: str
    ) -> str:
        ticket = self._tickets.get((tenant_id, ticket_id))
        if ticket is None:
            raise KeyError(ticket_id)
        ticket["agent_id"] = agent_id
        return "ok"

    async def search_tickets(self, tenant_id: str, query: str) -> list[dict]:
        results = []
        for (tid, ticket_id), ticket in self._tickets.items():
            if tid == tenant_id and (
                query.lower() in ticket["subject"].lower()
                or any(query.lower() in m.lower() for m in ticket["messages"])
            ):
                results.append(dict(ticket))
        return results

    # --- Helpers de inspección para tests/demo ---
    def get(self, tenant_id: str, ticket_id: str) -> dict | None:
        return self._tickets.get((tenant_id, ticket_id))

    def all(self, tenant_id: str | None = None) -> list[dict]:
        return [
            dict(t)
            for (tid, _), t in self._tickets.items()
            if tenant_id is None or tid == tenant_id
        ]
