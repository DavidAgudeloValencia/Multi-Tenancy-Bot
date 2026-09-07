"""API del panel de agentes (helpdesk).

Operaciones del agente sobre tickets: listar, detalle (histórico + notas),
claim/release (lock TTL), transferencia, notas internas y respuesta.

Autenticación: JWT de sesión (login con Google) con roles
`admin` | `supervisor` | `agent`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import require_role
from app.services.helpdesk import (
    AlreadyClaimed,
    HelpdeskError,
    HelpdeskService,
    NotOwner,
    get_helpdesk_service,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Cualquiera de estos roles puede operar el panel de agentes.
_require_agent_user = require_role("admin", "supervisor", "agent")


class _Claim(BaseModel):
    agent_email: str


class _Release(BaseModel):
    agent_email: str


class _Transfer(BaseModel):
    to_agent: str
    note: str = ""
    author: str


class _Note(BaseModel):
    note: str
    author: str


class _Reply(BaseModel):
    message: str
    author: str


def _svc() -> HelpdeskService:
    return get_helpdesk_service()


@router.get(
    "/tenants/{tenant_id}/tickets", dependencies=[Depends(_require_agent_user)]
)
async def list_tickets(tenant_id: str, status: str | None = None) -> list[dict]:
    return await _svc().list_tickets(tenant_id, status)


@router.get(
    "/tenants/{tenant_id}/tickets/{ticket_id}",
    dependencies=[Depends(_require_agent_user)],
)
async def get_ticket(tenant_id: str, ticket_id: str) -> dict:
    detail = await _svc().get_detail(tenant_id, ticket_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return detail


@router.post(
    "/tenants/{tenant_id}/tickets/{ticket_id}/claim",
    dependencies=[Depends(_require_agent_user)],
)
async def claim_ticket(tenant_id: str, ticket_id: str, body: _Claim) -> dict:
    try:
        return await _svc().claim(tenant_id, ticket_id, body.agent_email)
    except AlreadyClaimed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HelpdeskError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/tenants/{tenant_id}/tickets/{ticket_id}/release",
    dependencies=[Depends(_require_agent_user)],
)
async def release_ticket(tenant_id: str, ticket_id: str, body: _Release) -> dict:
    try:
        return await _svc().release(tenant_id, ticket_id, body.agent_email)
    except NotOwner as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HelpdeskError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/tenants/{tenant_id}/tickets/{ticket_id}/transfer",
    dependencies=[Depends(_require_agent_user)],
)
async def transfer_ticket(tenant_id: str, ticket_id: str, body: _Transfer) -> dict:
    try:
        return await _svc().transfer(
            tenant_id, ticket_id, body.to_agent, body.note, body.author
        )
    except HelpdeskError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/tenants/{tenant_id}/tickets/{ticket_id}/notes",
    dependencies=[Depends(_require_agent_user)],
)
async def add_note(tenant_id: str, ticket_id: str, body: _Note) -> dict:
    try:
        return await _svc().add_note(tenant_id, ticket_id, body.note, body.author)
    except HelpdeskError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/tenants/{tenant_id}/tickets/{ticket_id}/reply",
    dependencies=[Depends(_require_agent_user)],
)
async def reply_ticket(tenant_id: str, ticket_id: str, body: _Reply) -> dict:
    try:
        return await _svc().reply(tenant_id, ticket_id, body.message, body.author)
    except HelpdeskError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
