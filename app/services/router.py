"""Router de intención (Fase 4, planning.md §Fase 4.2).

Clasifica cada mensaje entrante en una de cuatro intenciones:
  - "soporte": dudas operativas (siniestros, asistencias, pagos, carné...).
  - "venta"  : el cliente quiere cotizar o comprar un seguro.
  - "humano" : el cliente pide hablar con una persona real.
  - "saludo" : saludo inicial sin consulta específica.

Estrategia en producción (defensa en profundidad):
  1. Fast-path por palabras clave para "humano" (crítico: el cliente siempre
     debe poder llegar a una persona) — sin costo ni latencia de LLM.
  2. Clasificación con LLM (temperature=0) para el resto.
  3. Fallback a "soporte" si el LLM falla (el bot nunca deja de atender).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings

logger = logging.getLogger("multibot.router")

ALLOWED_INTENTS = {"soporte", "venta", "humano", "saludo"}

# Frases que indican petición explícita de atención humana.
HUMAN_REQUEST_PHRASES = (
    "hablar con un humano",
    "hablar con alguien",
    "persona real",
    "un asesor humano",
    "atención humana",
    "agente humano",
    "atención personal",
)

_ROUTER_PROMPT = """Clasifica la intención del mensaje de un cliente de seguros.
Devuelve ÚNICAMENTE JSON con esta forma:
{{"intent": "soporte|venta|humano|saludo", "reason": "explicación breve"}}

Reglas:
- soporte: dudas operativas (siniestros, asistencias, grúa, médico a domicilio,
  carné, pagos, certificados, directorio).
- venta: quiere cotizar, comprar o saber precios de un seguro (auto, moto,
  vida, salud).
- humano: pide explícitamente hablar con una persona real o un asesor.
- saludo: saludo inicial o conversación trivial sin consulta específica.

Mensaje del cliente: {message}"""


def is_human_request(text: str) -> bool:
    """True si el texto pide explícitamente atención humana (fast-path)."""
    lowered = text.lower()
    return any(phrase in lowered for phrase in HUMAN_REQUEST_PHRASES)


def _extract_json(content: str) -> dict:
    """Extrae el primer objeto JSON del contenido (tolera fences de markdown)."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No se encontró JSON en: {content!r}")
    return json.loads(content[start : end + 1])


class LLMIntentRouter:
    """Clasificador de intención: keywords rápidas + LLM (temperature=0)."""

    def __init__(self, llm: Any | None = None) -> None:
        settings = get_settings()
        self._llm = llm or ChatOpenAI(
            model=settings.openai_model,
            temperature=0.0,
            api_key=settings.openai_api_key,
        )

    async def classify(self, text: str) -> str:
        """Devuelve la intención del mensaje (siempre una de ALLOWED_INTENTS)."""
        # 1) Fast-path: petición explícita de humano (sin llamar al LLM).
        if is_human_request(text):
            return "humano"

        # 2) Clasificación con LLM.
        try:
            response = await self._llm.ainvoke(
                [
                    SystemMessage(
                        content="Eres un clasificador de intenciones preciso."
                    ),
                    HumanMessage(content=_ROUTER_PROMPT.format(message=text)),
                ]
            )
            payload = _extract_json(response.content)
            intent = payload.get("intent")
            if intent in ALLOWED_INTENTS:
                return intent
            logger.warning("Intención no válida del LLM: %r", intent)
        except Exception as exc:  # noqa: BLE001 - el router nunca debe fallar
            logger.exception("Error clasificando intención: %s", exc)

        # 3) Fallback seguro: tratar como soporte.
        return "soporte"
