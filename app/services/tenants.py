"""Registro de inquilinos (tenants) — multi-tenant + perfiles de bot.

Cada tenant = un agente/vendedor con:
  - su propio número de WhatsApp (phone_number_id de Meta),
  - su propia base de conocimiento (colección ChromaDB + carpeta de PDFs),
  - su asesor para notificaciones de leads,
  - su PERFIL DE BOT configurable (saludo, preguntas del lead, respuestas,
    modelo IA, temperatura, umbral de relevancia).

El registro vive en un archivo JSON (`data/tenants.json`) y se administra
desde el panel web (API `/api/admin`). Las escrituras son ATÓMICAS (archivo
temporal + os.replace). Los `access_token` se cifran en reposo con Fernet
(`SECRET_ENCRYPTION_KEY`).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger("multibot.tenants")

# ID de agente: minúsculas, números, guiones y guiones bajos (máx. 64).
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class Tenant:
    """Configuración completa de un agente/vendedor del servicio."""

    id: str
    name: str = ""
    # --- Identidad WhatsApp ---
    phone_number_id: str = ""
    whatsapp_number: str = ""
    access_token: str = ""           # vacío -> token global del .env
    advisor_notify_whatsapp: str = ""
    # --- Conocimiento ---
    collection: str = ""             # vacío -> multibot_kb_{id}
    knowledge_dir: str = ""          # vacío -> knowledge/{id}
    # --- Estado ---
    enabled: bool = True
    # --- Perfil de bot ---
    greeting: str = ""               # vacío -> saludo por defecto
    fallback_answer: str = ""        # vacío -> fallback por defecto (RAG)
    handoff_reply: str = ""
    lead_done_reply: str = ""
    human_paused_reply: str = ""
    openai_model: str = ""           # vacío -> settings.openai_model
    rag_temperature: float | None = None
    rag_top_k: int | None = None
    rag_score_threshold: float | None = None
    lead_questions: dict[str, str] = field(default_factory=dict)

    # --- Propiedades efectivas (con fallback a la config global) ---
    @property
    def effective_collection(self) -> str:
        return self.collection or f"multibot_kb_{self.id}"

    @property
    def effective_knowledge_dir(self) -> str:
        return self.knowledge_dir or f"knowledge/{self.id}"

    @property
    def effective_token(self) -> str:
        return self.access_token or get_settings().whatsapp_access_token

    @property
    def effective_model(self) -> str:
        return self.openai_model or get_settings().openai_model

    @property
    def effective_temperature(self) -> float:
        s = get_settings()
        return self.rag_temperature if self.rag_temperature is not None else s.rag_temperature

    @property
    def effective_top_k(self) -> int:
        return self.rag_top_k if self.rag_top_k is not None else get_settings().rag_top_k

    @property
    def effective_score_threshold(self) -> float:
        s = get_settings()
        return self.rag_score_threshold if self.rag_score_threshold is not None else s.rag_score_threshold


class TenantRegistry:
    """Carga, consulta y persiste el registro de tenants (JSON atómico)."""

    _KNOWN_FIELDS = set(Tenant.__dataclass_fields__)

    def __init__(self, tenants_file: Path | str) -> None:
        self._file = Path(tenants_file)
        self._tenants: list[Tenant] = []
        self._by_phone_id: dict[str, Tenant] = {}
        self._by_id: dict[str, Tenant] = {}
        self.reload()

    # ------------------------------------------------------------------
    def reload(self) -> None:
        """(Re)carga el registro desde el archivo JSON (descifra tokens)."""
        if not self._file.exists():
            logger.warning(
                "No existe el archivo de tenants %s: sin agentes configurados",
                self._file,
            )
            self._tenants, self._by_phone_id, self._by_id = [], {}, {}
            return

        raw = json.loads(self._file.read_text(encoding="utf-8"))
        tenants: list[Tenant] = []
        for item in raw.get("tenants", []):
            data = {k: v for k, v in item.items() if k in self._KNOWN_FIELDS}
            if data.get("access_token"):
                data["access_token"] = decrypt_secret(data["access_token"])
            tenants.append(Tenant(**data))
        self._tenants = tenants
        self._reindex()
        logger.info("Registro multi-tenant: %d agente(s) cargado(s)", len(self._tenants))

    def _reindex(self) -> None:
        self._by_phone_id = {
            t.phone_number_id: t for t in self._tenants if t.phone_number_id
        }
        self._by_id = {t.id: t for t in self._tenants}

    def _persist(self) -> None:
        """Escribe el registro de forma ATÓMICA (tmp + os.replace)."""
        self._file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "tenants": [
                    {**asdict(t), "access_token": encrypt_secret(t.access_token)}
                    for t in self._tenants
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._file)

    # ------------------------------------------------------------------
    def all(self) -> list[Tenant]:
        return list(self._tenants)

    def get(self, tenant_id: str) -> Tenant | None:
        return self._by_id.get(tenant_id)

    def by_phone_number_id(self, phone_number_id: str) -> Tenant | None:
        return self._by_phone_id.get(phone_number_id)

    # ------------------------------------------------------------------
    # CRUD (usado por el panel de administración)
    # ------------------------------------------------------------------
    def create(self, tenant_id: str, data: dict) -> Tenant:
        """Crea un tenant y persiste (falla si el id ya existe)."""
        if tenant_id in self._by_id:
            raise ValueError(f"El agente '{tenant_id}' ya existe.")
        self._validate(tenant_id, data)
        clean = {k: v for k, v in data.items() if k in self._KNOWN_FIELDS}
        tenant = Tenant(id=tenant_id, **clean)
        self._tenants.append(tenant)
        self._reindex()
        self._persist()
        logger.info("Agente '%s' creado", tenant_id)
        return tenant

    def update(self, tenant_id: str, data: dict) -> Tenant:
        """Actualiza un tenant existente y persiste."""
        if tenant_id not in self._by_id:
            raise KeyError(tenant_id)
        self._validate(tenant_id, data)
        clean = {k: v for k, v in data.items() if k in self._KNOWN_FIELDS and k != "id"}
        updated = Tenant(id=tenant_id, **clean)
        self._tenants = [t if t.id != tenant_id else updated for t in self._tenants]
        self._reindex()
        self._persist()
        logger.info("Agente '%s' actualizado", tenant_id)
        return updated

    def delete(self, tenant_id: str) -> bool:
        """Elimina un tenant y persiste. Devuelve False si no existía."""
        if tenant_id not in self._by_id:
            return False
        self._tenants = [t for t in self._tenants if t.id != tenant_id]
        self._reindex()
        self._persist()
        logger.info("Agente '%s' eliminado", tenant_id)
        return True

    def _validate(self, tenant_id: str, data: dict) -> None:
        if not _SLUG_RE.match(tenant_id):
            raise ValueError(
                "El 'id' solo admite minúsculas, números, '-' y '_' (máx. 64)."
            )
        phone = data.get("phone_number_id", "")
        if phone:
            for t in self._tenants:
                if t.phone_number_id == phone and t.id != tenant_id:
                    raise ValueError("El phone_number_id ya está asignado a otro agente.")

    # ------------------------------------------------------------------
    @staticmethod
    def to_public(tenant: Tenant) -> dict:
        """Representación segura (SIN el token) para la API de administración."""
        data = asdict(tenant)
        data["access_token_configured"] = bool(tenant.access_token)
        data.pop("access_token", None)
        return data


_registry: TenantRegistry | None = None


def get_tenant_registry() -> TenantRegistry:
    """Devuelve el registro único de tenants de la aplicación."""
    global _registry
    if _registry is None:
        _registry = TenantRegistry(get_settings().tenants_file)
    return _registry
