"""Runtimes por tenant — multi-tenant.

Cada tenant tiene su propio `TenantRuntime` con:
  - su motor RAG (colección ChromaDB propia),
  - su almacén de sesiones con prefijo (namespace en Redis),
  - su notificador (asesor asignado a ese tenant).

Los runtimes se cachean por tenant: se crean una vez y se reutilizan.
"""

from __future__ import annotations

import logging
from typing import Any

from chromadb import PersistentClient
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings
from app.core.session import PrefixedSessionStore, get_session_store
from app.services.conversation import BotSettings, ConversationManager
from app.services.notifier import AdvisorNotifier
from app.services.rag import RAGEngine
from app.services.router import LLMIntentRouter
from app.services.tenants import Tenant

logger = logging.getLogger("multibot.runtime")

# Cliente ChromaDB compartido por todos los tenants (una sola conexión al
# mismo almacén persistente; cada tenant usa su propia colección).
_chroma_client: PersistentClient | None = None


def _get_chroma_client() -> PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        settings = get_settings()
        _chroma_client = PersistentClient(
            path=str(settings.chroma_persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


class TenantRuntime:
    """Agrupa las dependencias de IA y conversación de un tenant."""

    def __init__(self, tenant: Tenant) -> None:
        self.tenant = tenant
        settings = get_settings()

        # Motor RAG con overrides del perfil del agente.
        self.rag = RAGEngine(
            client=_get_chroma_client(),
            collection_name=tenant.effective_collection,
            persist_dir=settings.chroma_persist_dir,
            top_k=tenant.effective_top_k,
            score_threshold=tenant.effective_score_threshold,
            model=tenant.effective_model,
            temperature=tenant.effective_temperature,
            fallback_answer=tenant.fallback_answer or None,
        )
        self.notifier = AdvisorNotifier(
            advisor_number=tenant.advisor_notify_whatsapp,
            sender_phone_number_id=tenant.phone_number_id,
            sender_access_token=tenant.effective_token,
        )
        self.conversation = ConversationManager(
            sessions=PrefixedSessionStore(get_session_store(), tenant.id),
            router=LLMIntentRouter(),
            rag=self.rag,
            notifier=self.notifier,
            bot_settings=BotSettings.from_tenant(tenant),
        )

    async def handle_message(self, wa_id: str, text: str) -> str:
        """Procesa un mensaje con la configuración de este tenant."""
        return await self.conversation.handle_message(wa_id, text)


_runtimes: dict[str, TenantRuntime] = {}


def get_tenant_runtime(tenant: Tenant) -> TenantRuntime:
    """Devuelve (y cachea) el runtime de un tenant."""
    runtime = _runtimes.get(tenant.id)
    if runtime is None:
        runtime = TenantRuntime(tenant)
        _runtimes[tenant.id] = runtime
        logger.info("Runtime creado para el tenant '%s'", tenant.id)
    return runtime


def invalidate_runtime(tenant_id: str) -> None:
    """Descarta el runtime cacheado de un tenant (tras editar su perfil)."""
    if _runtimes.pop(tenant_id, None):
        logger.info("Runtime del tenant '%s' invalidado", tenant_id)


def invalidate_all_runtimes() -> None:
    """Descarta todos los runtimes cacheados (tras recargar el registro)."""
    _runtimes.clear()
    logger.info("Runtimes invalidados (recarga del registro)")
