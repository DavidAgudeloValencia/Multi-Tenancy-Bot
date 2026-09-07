"""Orquestador conversacional (Fase 4, planning.md §Fase 4).

`ConversationManager.handle_message(wa_id, text)` es el punto único por donde
pasa TODO mensaje entrante. Decide qué hacer según el estado de la sesión del
cliente (guardada en Redis/memoria con TTL de 24 h):

  - Si el bot ya hizo handoff a un humano (estado `human_paused`), no vuelve
    a intervenir con IA.
  - Si hay un flujo de venta en curso, avanza las preguntas del lead.
  - Si no, clasifica la intención:
      soporte -> motor RAG (respuesta con contexto, sin alucinar)
      venta   -> inicia el cuestionario de calificación (3-4 preguntas)
      humano  -> handoff inmediato con lo capturado hasta ahora
      saludo  -> mensaje de bienvenida con el menú de opciones
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.core.session import get_session_store
from app.services.notifier import AdvisorNotifier
from app.services.rag import RAGEngine, get_rag_engine
from app.services.router import LLMIntentRouter, is_human_request

logger = logging.getLogger("multibot.conversation")

# ---------------------------------------------------------------------------
# Respuestas del bot (texto plano/UTF-8; los emojis se renderizan en WhatsApp)
# ---------------------------------------------------------------------------
GREETING_REPLY = (
    "¡Hola! 👋 Soy el asistente virtual de tu asesor de seguros. "
    "Puedo ayudarte con:\n\n"
    "1️⃣ Siniestros y asistencias (accidentes, grúa, médico a domicilio, carné)\n"
    "2️⃣ Cotizaciones de seguros (auto, moto, vida, salud)\n\n"
    "Escríbeme tu consulta o dime que quieres cotizar. 📋"
)

HUMAN_PAUSED_REPLY = (
    "Tu caso ya está con un asesor humano, que te atenderá por este mismo "
    "canal. Si necesitas algo urgente, escríbele directamente. 🙏"
)

HANDOFF_REPLY = (
    "Entendido, te comunico con un asesor humano ahora mismo. "
    "Por favor espera su mensaje. 🙏"
)

LEAD_DONE_REPLY = (
    "¡Listo! 🙌 Ya tengo tu perfil de cotización. Un asesor humano te "
    "contactará muy pronto por este mismo canal para darte la mejor tarifa. "
    "¡Gracias!"
)

# ---------------------------------------------------------------------------
# Cuestionario de calificación de leads (planning.md §1.2B y §3.Fase3 prompt)
# ---------------------------------------------------------------------------
LEAD_QUESTIONS: dict[str, str] = {
    "lead_tipo": (
        "¡Con gusto te ayudo a cotizar! 📋 Primero, ¿qué tipo de seguro "
        "necesitas? (auto, moto, vida o salud)"
    ),
    "lead_marca_modelo": "¿Cuál es la marca y el modelo? (ej. Renault Logan)",
    "lead_anio": (
        "¿De qué año es el vehículo? (o año de nacimiento del asegurado, "
        "si es vida/salud)"
    ),
    "lead_ciudad": "¿En qué ciudad estás?",
}

# Estado de pregunta -> (campo del perfil, siguiente estado | None si termina)
LEAD_FLOW: dict[str, tuple[str, str | None]] = {
    "lead_tipo": ("tipo", "lead_marca_modelo"),
    "lead_marca_modelo": ("marca_modelo", "lead_anio"),
    "lead_anio": ("anio", "lead_ciudad"),
    "lead_ciudad": ("ciudad", None),
}


@dataclass
class BotSettings:
    """Perfil configurable del bot (por tenant).

    Cada campo vacío hereda el valor por defecto. Se construye desde un
    `Tenant` con `BotSettings.from_tenant(...)`.
    """

    greeting: str = GREETING_REPLY
    human_paused_reply: str = HUMAN_PAUSED_REPLY
    handoff_reply: str = HANDOFF_REPLY
    lead_done_reply: str = LEAD_DONE_REPLY
    lead_questions: dict[str, str] = field(
        default_factory=lambda: dict(LEAD_QUESTIONS)
    )

    @classmethod
    def from_tenant(cls, tenant: Any) -> "BotSettings":
        """Construye el perfil a partir de un Tenant (sobreescribiendo lo que defina)."""
        questions = dict(LEAD_QUESTIONS)
        if getattr(tenant, "lead_questions", None):
            questions.update(tenant.lead_questions)
        return cls(
            greeting=tenant.greeting or GREETING_REPLY,
            human_paused_reply=tenant.human_paused_reply or HUMAN_PAUSED_REPLY,
            handoff_reply=tenant.handoff_reply or HANDOFF_REPLY,
            lead_done_reply=tenant.lead_done_reply or LEAD_DONE_REPLY,
            lead_questions=questions,
        )


class ConversationManager:
    """Máquina de estados que decide la respuesta a cada mensaje."""

    def __init__(
        self,
        sessions: Any,
        router: Any,
        rag: RAGEngine,
        notifier: AdvisorNotifier,
        bot_settings: BotSettings | None = None,
    ) -> None:
        """Recibe dependencias inyectadas (fáciles de sustituir en pruebas)."""
        self._sessions = sessions
        self._router = router
        self._rag = rag
        self._notifier = notifier
        self._bs = bot_settings or BotSettings()

    # ------------------------------------------------------------------
    async def handle_message(self, wa_id: str, text: str) -> str:
        """Procesa un mensaje y devuelve la respuesta para el cliente."""
        session = await self._sessions.get(wa_id) or {"state": "idle", "lead": {}}
        state = session.get("state", "idle")

        # 1) Handoff hecho: la IA queda pausada para este número.
        if state == "human_paused":
            return self._bs.human_paused_reply

        # 2) Flujo de venta en curso: la respuesta avanza el cuestionario.
        if state in LEAD_FLOW:
            return await self._continue_lead(wa_id, session, state, text)

        # 3) Sin flujo activo: clasificar la intención del mensaje.
        intent = await self._router.classify(text)
        logger.info("Intención '%s' para wa_id=%s", intent, wa_id)

        if intent == "saludo":
            session["state"] = "idle"
            await self._sessions.set(wa_id, session)
            return self._bs.greeting

        if intent == "humano":
            return await self._handoff(wa_id, session)

        if intent == "venta":
            session["state"] = "lead_tipo"
            session["lead"] = {}
            await self._sessions.set(wa_id, session)
            return self._bs.lead_questions["lead_tipo"]

        # 4) soporte (por defecto): responder con el motor RAG.
        session["state"] = "idle"
        answer = await asyncio.to_thread(self._rag.ask, text)
        session["last_rag_sources"] = answer.sources or []
        await self._sessions.set(wa_id, session)
        return answer.answer

    # ------------------------------------------------------------------
    async def _continue_lead(
        self, wa_id: str, session: dict, state: str, text: str
    ) -> str:
        """Guarda la respuesta del lead y avanza (o completa) el cuestionario."""
        # El cliente puede pedir humano en cualquier momento del flujo.
        if is_human_request(text):
            return await self._handoff(wa_id, session)

        field, next_state = LEAD_FLOW[state]
        lead = session.setdefault("lead", {})
        lead[field] = text.strip()

        if next_state is None:
            # Cuestionario completado: calificar y notificar al asesor.
            await self._notifier.notify_lead(wa_id, lead)
            session["state"] = "human_paused"
            session["handoff_reason"] = "lead_calificado"
            await self._sessions.set(wa_id, session)
            return self._bs.lead_done_reply

        session["state"] = next_state
        await self._sessions.set(wa_id, session)
        return self._bs.lead_questions[next_state]

    # ------------------------------------------------------------------
    async def _handoff(self, wa_id: str, session: dict) -> str:
        """Pausa la IA y notifica al asesor con el perfil capturado."""
        lead = session.get("lead", {})
        await self._notifier.notify_lead(wa_id, lead, partial=True)
        session["state"] = "human_paused"
        session["handoff_reason"] = "humano"
        await self._sessions.set(wa_id, session)
        return self._bs.handoff_reply

    # ------------------------------------------------------------------
    async def get_session(self, wa_id: str) -> dict:
        """Devuelve la sesión completa del cliente (estado, lead, razón de handoff)."""
        return await self._sessions.get(wa_id) or {}


# Singleton del orquestador para toda la app.
_manager: ConversationManager | None = None


def get_conversation_manager() -> ConversationManager:
    """Devuelve el orquestador único (con dependencias reales)."""
    global _manager
    if _manager is None:
        _manager = ConversationManager(
            sessions=get_session_store(),
            router=LLMIntentRouter(),
            rag=get_rag_engine(),
            notifier=AdvisorNotifier(),
        )
    return _manager
