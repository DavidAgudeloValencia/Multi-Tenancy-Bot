"""API de administración (panel web) — multi-tenant.

Autenticación: header `X-Admin-Key`, comparado en TIEMPO CONSTANTE contra
`ADMIN_API_KEY`. Los tokens de acceso NUNCA se devuelven en las respuestas
(solo el booleano `access_token_configured`).

Seguridad adicional:
  - Rate limiting por IP (contra fuerza bruta de la clave).
  - Subida de PDFs con validación de tipo (magic bytes), tamaño y nombre
    (anti path-traversal).

Las escrituras invalidan el runtime cacheado del agente para que los cambios
de perfil apliquen en el siguiente mensaje, sin reiniciar el servicio.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import re
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    UploadFile,
)

from app.config import get_settings
from app.core.ratelimit import RateLimiter, make_rate_limit_dependency
from app.schemas.admin import TenantCreate, TenantUpdate
from app.services.runtime import invalidate_all_runtimes, invalidate_runtime
from app.services.tenants import get_tenant_registry

logger = logging.getLogger("multibot.admin")

# --- Límites: 30 req/min por IP en el panel (anti fuerza bruta). ---
_admin_limiter = RateLimiter(limit=30, window_seconds=60)

# --- Subida de PDFs: máx. 20 MB por archivo. ---
MAX_PDF_BYTES = 20 * 1024 * 1024
_PDF_MAGIC = b"%PDF-"
_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]")


async def require_admin(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> None:
    """Valida la clave de administrador (tiempo constante)."""
    expected = get_settings().admin_api_key
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Panel no configurado: define ADMIN_API_KEY en el .env",
        )
    if not x_admin_key or not hmac.compare_digest(
        x_admin_key.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Clave de administrador inválida")


def _sanitize_filename(name: str) -> str:
    """Limpia el nombre del archivo y exige extensión .pdf (anti traversal)."""
    name = Path(name or "documento.pdf").name  # descarta cualquier ruta
    name = _SAFE_FILENAME_RE.sub("_", name).strip("._")
    if not name.lower().endswith(".pdf"):
        raise ValueError("Solo se aceptan archivos con extensión .pdf")
    return name or "documento.pdf"


def _is_pdf(content: bytes) -> bool:
    """Valida la firma (magic bytes) de un PDF, no solo la extensión."""
    return content[:5] == _PDF_MAGIC


def _tenant_knowledge_target(tenant_id: str) -> Path:
    """Resuelve la carpeta de PDFs de un agente, restringida a knowledge/."""
    tenant = get_tenant_registry().get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Agente '{tenant_id}' no encontrado")

    base = Path(get_settings().knowledge_dir).resolve()
    target = Path(tenant.effective_knowledge_dir).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Carpeta de conocimiento inválida")
    return target


router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(make_rate_limit_dependency(_admin_limiter)), Depends(require_admin)],
)


@router.get("/tenants")
async def list_tenants() -> list[dict]:
    registry = get_tenant_registry()
    return [registry.to_public(t) for t in registry.all()]


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str) -> dict:
    tenant = get_tenant_registry().get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Agente '{tenant_id}' no encontrado")
    return get_tenant_registry().to_public(tenant)


@router.post("/tenants", status_code=201)
async def create_tenant(payload: TenantCreate) -> dict:
    registry = get_tenant_registry()
    try:
        tenant = registry.create(payload.id, payload.model_dump(exclude={"id"}))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    invalidate_runtime(tenant.id)
    return registry.to_public(tenant)


@router.put("/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, payload: TenantUpdate) -> dict:
    registry = get_tenant_registry()
    try:
        tenant = registry.update(tenant_id, payload.model_dump())
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agente '{tenant_id}' no encontrado")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    invalidate_runtime(tenant_id)
    return registry.to_public(tenant)


@router.delete("/tenants/{tenant_id}", status_code=204)
async def delete_tenant(tenant_id: str):
    from fastapi import Response

    registry = get_tenant_registry()
    if not registry.delete(tenant_id):
        raise HTTPException(status_code=404, detail=f"Agente '{tenant_id}' no encontrado")
    invalidate_runtime(tenant_id)
    return Response(status_code=204)


@router.post("/reload")
async def reload_registry() -> dict:
    """Recarga tenants.json desde disco (por si se editó manualmente)."""
    registry = get_tenant_registry()
    registry.reload()
    invalidate_all_runtimes()
    return {"status": "ok", "tenants": len(registry.all())}


@router.post("/tenants/{tenant_id}/documents", status_code=201)
async def upload_documents(
    tenant_id: str,
    files: list[UploadFile] = File(...),
) -> dict:
    """Sube PDFs a la carpeta de conocimiento del agente (validados).

    Valida: extensión, magic bytes `%PDF-` y tamaño máximo. Los nombres se
    sanitizan para impedir path-traversal.
    """
    target = _tenant_knowledge_target(tenant_id)
    target.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    for upload in files:
        try:
            name = _sanitize_filename(upload.filename or "")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        content = await upload.read()
        if len(content) > MAX_PDF_BYTES:
            raise HTTPException(status_code=413, detail=f"'{name}' supera el tamaño máximo")
        if not _is_pdf(content):
            raise HTTPException(status_code=415, detail=f"'{name}' no es un PDF válido")

        (target / name).write_bytes(content)
        saved.append(name)
        logger.info("PDF subido para el agente '%s': %s", tenant_id, name)

    return {"status": "ok", "tenant": tenant_id, "saved": saved}


@router.post("/tenants/{tenant_id}/ingest")
async def ingest_tenant(tenant_id: str) -> dict:
    """Reingesta la base de conocimiento del agente (en un hilo, sin bloquear)."""
    if get_tenant_registry().get(tenant_id) is None:
        raise HTTPException(status_code=404, detail=f"Agente '{tenant_id}' no encontrado")

    from app.services.ingestion import ingest_documents

    result = await asyncio.to_thread(ingest_documents, tenant_id=tenant_id, reset=True)
    if result.get("status") != "ok":
        raise HTTPException(status_code=500, detail=result.get("detail", "Error de ingesta"))
    return result
