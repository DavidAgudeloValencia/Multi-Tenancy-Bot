"""API del panel de agentes (helpdesk).

Operaciones del agente sobre tickets: listar, detalle (histórico + notas),
claim/release (lock TTL), transferencia, notas internas y respuesta.

Autenticación provisional: header `X-Admin-Key` (se reemplazará por el login
de Google con JWT y roles en la siguiente fase).
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.services.helpdesk import (
    AlreadyClaimed,
    HelpdeskError,
    HelpdeskService,
    NotOwner,
    get_helpdesk_service,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])


async def require_agent(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> None:
    """Autenticación provisional del agente (TODO: sustituir por Google/JWT)."""
    expected = get_settings().admin_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="Autenticación no configurada")
    if not x_admin_key or not hmac.compare_digest(
        x_admin_key.encode(), expected.encode()
    ):
        raise HTTPException(status_code=401, detail="No autorizado")


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


@router.get("/tenants/{tenant_id}/tickets", dependencies=[Depends(require_agent)])
async def list_tickets(tenant_id: str, status: str | None = None) -> list[dict]:
    return await _svc().list_tickets(tenant_id, status)


@router.get(
    "/tenants/{tenant_id}/tickets/{ticket_id}", dependencies=[Depends(require_agent)]
)
async def get_ticket(tenant_id: str, ticket_id: str) -> dict:
    detail = await _svc().get_detail(tenant_id, ticket_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return detail


@router.post(
    "/tenants/{tenant_id}/tickets/{ticket_id}/claim",
    dependencies=[Depends(require_agent)],
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
    dependencies=[Depends(require_agent)],
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
    dependencies=[Depends(require_agent)],
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
    dependencies=[Depends(require_agent)],
)
async def add_note(tenant_id: str, ticket_id: str, body: _Note) -> dict:
    try:
        return await _svc().add_note(tenant_id, ticket_id, body.note, body.author)
    except HelpdeskError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/tenants/{tenant_id}/tickets/{ticket_id}/reply",
    dependencies=[Depends(require_agent)],
)
async def reply_ticket(tenant_id: str, ticket_id: str, body: _Reply) -> dict:
    try:
        return await _svc().reply(tenant_id, ticket_id, body.message, body.author)
    except HelpdeskError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
