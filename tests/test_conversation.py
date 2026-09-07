"""Pruebas del orquestador conversacional (Fase 4) — sin llamar a APIs.

Usan dobles para router, RAG, notificador y almacén de sesiones, por lo que
funcionan sin OpenAI, sin Redis y sin WhatsApp.

Ejecutar con:  pytest -q
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.session import MemorySessionStore
from app.services.conversation import (
    GREETING_REPLY,
    HANDOFF_REPLY,
    HUMAN_PAUSED_REPLY,
    LEAD_DONE_REPLY,
    ConversationManager,
)
from app.services.rag import Answer


class FakeRouter:
    """Devuelve intenciones en orden; registra los mensajes clasificados."""

    def __init__(self, intents: list[str]) -> None:
        self._intents = list(intents)
        self.calls: list[str] = []

    async def classify(self, text: str) -> str:
        self.calls.append(text)
        return self._intents.pop(0) if self._intents else "soporte"


class FakeRAG:
    """RAG falso que devuelve una respuesta fija y registra las preguntas."""

    def __init__(self) -> None:
        self.questions: list[str] = []

    def ask(self, question: str) -> Answer:
        self.questions.append(question)
        return Answer(question=question, answer="RESPUESTA_RAG", used_context=True)


class FakeNotifier:
    """Registra las notificaciones de leads enviadas al asesor."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, bool]] = []

    async def notify_lead(self, wa_id: str, profile: dict, partial: bool = False) -> None:
        self.calls.append((wa_id, dict(profile), partial))


@pytest.fixture
def make_manager():
    """Fábrica de ConversationManager con dobles frescos por prueba."""

    def _make(intents: list[str] | None = None) -> SimpleNamespace:
        router = FakeRouter(intents or [])
        rag = FakeRAG()
        notifier = FakeNotifier()
        sessions = MemorySessionStore()
        manager = ConversationManager(
            sessions=sessions,
            router=router,
            rag=rag,
            notifier=notifier,
        )
        return SimpleNamespace(
            manager=manager,
            router=router,
            rag=rag,
            notifier=notifier,
            sessions=sessions,
        )

    return _make


async def test_soporte_intent_uses_rag(make_manager) -> None:
    ctx = make_manager(["soporte"])
    reply = await ctx.manager.handle_message("573001111111", "Me chocaron, ¿qué hago?")
    assert reply == "RESPUESTA_RAG"
    assert ctx.rag.questions == ["Me chocaron, ¿qué hago?"]


async def test_saludo_returns_greeting(make_manager) -> None:
    ctx = make_manager(["saludo"])
    reply = await ctx.manager.handle_message("573001111111", "Hola")
    assert reply == GREETING_REPLY
    assert ctx.rag.questions == []


async def test_venta_flow_questions_and_handoff(make_manager) -> None:
    ctx = make_manager(["venta"])
    wa_id = "573001111111"

    # 1) Intención venta -> primera pregunta
    r1 = await ctx.manager.handle_message(wa_id, "Quiero cotizar un seguro")
    assert "¿qué tipo de seguro" in r1

    # 2-5) Respuestas secuenciales -> pregunta siguiente -> completar
    r2 = await ctx.manager.handle_message(wa_id, "Auto")
    assert "marca y el modelo" in r2

    r3 = await ctx.manager.handle_message(wa_id, "Renault Logan")
    assert "año" in r3

    r4 = await ctx.manager.handle_message(wa_id, "2022")
    assert "ciudad" in r4

    r5 = await ctx.manager.handle_message(wa_id, "Bogotá")
    assert r5 == LEAD_DONE_REPLY

    # El asesor fue notificado con el perfil completo
    assert len(ctx.notifier.calls) == 1
    wa, profile, partial = ctx.notifier.calls[0]
    assert wa == wa_id
    assert profile == {
        "tipo": "Auto",
        "marca_modelo": "Renault Logan",
        "anio": "2022",
        "ciudad": "Bogotá",
    }
    assert partial is False

    # Después del handoff la IA queda pausada para ese número
    r6 = await ctx.manager.handle_message(wa_id, "¿Y el precio?")
    assert r6 == HUMAN_PAUSED_REPLY
    assert ctx.rag.questions == []


async def test_humano_mid_flow_handoff_with_partial_profile(make_manager) -> None:
    ctx = make_manager(["venta"])
    wa_id = "573001111111"

    await ctx.manager.handle_message(wa_id, "Quiero cotizar")       # -> pregunta tipo
    reply = await ctx.manager.handle_message(
        wa_id, "Mejor prefiero hablar con un humano"
    )
    assert reply == HANDOFF_REPLY

    # Handoff parcial con el perfil vacío (aún no respondió ninguna pregunta)
    assert len(ctx.notifier.calls) == 1
    _, profile, partial = ctx.notifier.calls[0]
    assert profile == {}
    assert partial is True


async def test_humano_intent_handoff(make_manager) -> None:
    ctx = make_manager(["humano"])
    reply = await ctx.manager.handle_message("573001111111", "Quiero hablar con alguien")
    assert reply == HANDOFF_REPLY
    session = await ctx.manager.get_session("573001111111")
    assert session["state"] == "human_paused"
    assert session["handoff_reason"] == "humano"


async def test_lead_complete_sets_handoff_reason(make_manager) -> None:
    ctx = make_manager(["venta"])
    m = ctx.manager
    await m.handle_message("w", "Quiero cotizar")
    await m.handle_message("w", "Moto")
    await m.handle_message("w", "Yamaha")
    await m.handle_message("w", "2023")
    await m.handle_message("w", "Medellín")

    session = await m.get_session("w")
    assert session["state"] == "human_paused"
    assert session["handoff_reason"] == "lead_calificado"
    assert session["lead"] == {
        "tipo": "Moto",
        "marca_modelo": "Yamaha",
        "anio": "2023",
        "ciudad": "Medellín",
    }


async def test_soporte_stores_rag_sources() -> None:
    from app.core.session import MemorySessionStore
    from app.services.conversation import ConversationManager
    from app.services.rag import Answer

    class RAGWithSources:
        def ask(self, question):
            return Answer(
                question=question,
                answer="respuesta",
                sources=[{"source": "guia.pdf", "page": 0, "score": 0.8}],
            )

    class Router:
        async def classify(self, text):
            return "soporte"

    class Notifier:
        async def notify_lead(self, *a, **k):
            pass

    manager = ConversationManager(
        sessions=MemorySessionStore(),
        router=Router(),
        rag=RAGWithSources(),
        notifier=Notifier(),
    )
    await manager.handle_message("573001111111", "¿médico a domicilio?")
    session = await manager.get_session("573001111111")
    assert session["last_rag_sources"] == [
        {"source": "guia.pdf", "page": 0, "score": 0.8}
    ]


async def test_memory_session_store_roundtrip_and_expiry() -> None:
    # ttl negativo -> expira en el pasado (prueba determinista de expiración)
    store = MemorySessionStore(default_ttl=-1)
    await store.set("wa_1", {"state": "lead_tipo"})
    assert await store.get("wa_1") is None  # ya expiró

    store2 = MemorySessionStore(default_ttl=60)
    await store2.set("wa_1", {"state": "lead_tipo"})
    assert await store2.get("wa_1") == {"state": "lead_tipo"}
