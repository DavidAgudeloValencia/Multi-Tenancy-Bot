"""Esquemas Pydantic del panel de administración (multi-tenant)."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class TenantPayload(BaseModel):
    """Campos editables de un agente (perfil de bot incluido)."""

    name: str = ""
    phone_number_id: str = ""
    whatsapp_number: str = ""
    access_token: str = ""              # nunca se devuelve en las respuestas
    advisor_notify_whatsapp: str = ""
    collection: str = ""
    knowledge_dir: str = ""
    enabled: bool = True

    # --- Perfil del bot ---
    greeting: str = ""
    fallback_answer: str = ""
    handoff_reply: str = ""
    lead_done_reply: str = ""
    human_paused_reply: str = ""
    openai_model: str = ""
    rag_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    rag_top_k: int | None = Field(default=None, ge=1, le=20)
    rag_score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    lead_questions: dict[str, str] = Field(default_factory=dict)


class TenantCreate(TenantPayload):
    id: str

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _SLUG_RE.match(value):
            raise ValueError(
                "El 'id' solo admite minúsculas, números, '-' y '_' (máx. 64)."
            )
        return value


class TenantUpdate(TenantPayload):
    """Actualización: el id no cambia (va en la URL)."""
