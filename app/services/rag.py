"""Motor RAG (Retrieval-Augmented Generation) — Fase 3.

Recupera los fragmentos más relevantes de ChromaDB y genera la respuesta
usando SOLO ese contexto (temperature=0) para evitar alucinaciones.

Diseño anti-alucinación:
  1. `temperature=0` en el LLM.
  2. El system prompt prohíbe responder fuera del contexto.
  3. Si ningún fragmento supera el umbral de relevancia
     (`RAG_SCORE_THRESHOLD`), se responde con un fallback controlado
     sin llamar al LLM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from chromadb import PersistentClient
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import get_settings

logger = logging.getLogger("multibot.rag")

# Respuesta controlada cuando no hay contexto suficiente (planning.md §4).
FALLBACK_ANSWER = (
    "Para esa duda específica sobre tu cobertura, prefiero que hables con tu "
    "asesor. ¿Te agendo una llamada?"
)

SYSTEM_PROMPT = """Eres el asistente virtual de un asesor de seguros experto.
Tu objetivo es resolver dudas operativas (siniestros, certificados, asistencias)
de forma clara y breve, SIEMPRE en español.

Reglas estrictas:
1. Responde SOLO con la información del CONTEXTO proporcionado.
2. Si el contexto no contiene la respuesta, responde exactamente con:
   "{fallback}"
3. No inventes coberturas, teléfonos, plazos, cifras ni procedimientos.
4. Si el cliente quiere comprar o cotizar un seguro, pídele los datos básicos
   (tipo de vehículo o seguro, marca, modelo, año, ciudad) y dile que un asesor
   lo contactará para la cotización.
5. Cuando uses información del contexto, menciona la fuente de forma breve
   (ej. "Según la guía de siniestros...")."""


@dataclass
class Answer:
    """Respuesta del motor RAG con trazabilidad de fuentes."""

    question: str
    answer: str
    sources: list[dict] = field(default_factory=list)
    used_context: bool = False


class RAGEngine:
    """Motor de preguntas y respuestas sobre la base de conocimiento."""

    def __init__(
        self,
        embedding_function: Embeddings | None = None,
        llm: Any | None = None,
        collection_name: str | None = None,
        persist_dir: Path | str | None = None,
        top_k: int | None = None,
        score_threshold: float | None = None,
        client: Any | None = None,
        model: str | None = None,
        temperature: float | None = None,
        fallback_answer: str | None = None,
    ) -> None:
        """Inicializa el motor conectándose a ChromaDB y preparando el LLM.

        Args:
            embedding_function: proveedor de embeddings (por defecto OpenAI).
            llm: objeto LLM compatible con `invoke(messages)` (por defecto
                ChatOpenAI). Se inyecta en las pruebas.
            collection_name: nombre de la colección vectorial (cada tenant
                tiene la suya, ej. `multibot_kb_{tenant_id}`).
            persist_dir: carpeta de persistencia de ChromaDB.
            top_k: número de fragmentos a recuperar por consulta.
            score_threshold: relevancia mínima (0-1) para responder con contexto.
            client: cliente ChromaDB compartido (multi-tenant); si no se pasa,
                se crea uno propio.
            model/temperature/fallback_answer: overrides por tenant (opcionales).
        """
        settings = get_settings()
        self.top_k = top_k if top_k is not None else settings.rag_top_k
        self.score_threshold = (
            score_threshold if score_threshold is not None else settings.rag_score_threshold
        )
        self._fallback_answer = fallback_answer or FALLBACK_ANSWER
        persist_dir = Path(persist_dir or settings.chroma_persist_dir)
        collection_name = collection_name or settings.chroma_collection

        embedding_function = embedding_function or OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )
        self._llm = llm or ChatOpenAI(
            model=model or settings.openai_model,
            temperature=settings.rag_temperature if temperature is None else temperature,
            api_key=settings.openai_api_key,
        )

        client = client or PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._vectorstore = Chroma(
            client=client,
            collection_name=collection_name,
            embedding_function=embedding_function,
            collection_metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    def retrieve(self, question: str, k: int | None = None) -> list[tuple[Any, float]]:
        """Recupera los fragmentos más relevantes con su puntaje (0-1)."""
        return self._vectorstore.similarity_search_with_relevance_scores(
            question,
            k=k or self.top_k,
        )

    # ------------------------------------------------------------------
    def ask(self, question: str) -> Answer:
        """Responde una pregunta usando únicamente el contexto recuperado."""
        results = self.retrieve(question)

        if not results:
            logger.info("Sin fragmentos recuperados -> fallback")
            return Answer(question=question, answer=self._fallback_answer)

        top_score = results[0][1]
        if top_score < self.score_threshold:
            logger.info(
                "Relevancia máxima %.2f < umbral %.2f -> fallback",
                top_score,
                self.score_threshold,
            )
            return Answer(
                question=question,
                answer=self._fallback_answer,
                sources=[self._source_info(doc, score) for doc, score in results],
            )

        context = "\n\n".join(
            f"[Fuente: {doc.metadata.get('source', '?')} | pág. "
            f"{doc.metadata.get('page', '?')}]\n{doc.page_content}"
            for doc, _ in results
        )
        messages = [
            SystemMessage(content=SYSTEM_PROMPT.format(fallback=self._fallback_answer)),
            HumanMessage(
                content=f"CONTEXTO:\n{context}\n\n"
                f"PREGUNTA DEL CLIENTE:\n{question}"
            ),
        ]

        try:
            response = self._llm.invoke(messages)
            answer_text = response.content
        except Exception as exc:  # noqa: BLE001 - nunca romper el chat
            logger.exception("Error llamando al LLM: %s", exc)
            answer_text = self._fallback_answer

        return Answer(
            question=question,
            answer=answer_text,
            sources=[self._source_info(doc, score) for doc, score in results],
            used_context=True,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _source_info(doc: Any, score: float) -> dict:
        """Construye la ficha de una fuente citada en la respuesta."""
        return {
            "source": doc.metadata.get("source", "?"),
            "page": doc.metadata.get("page", "?"),
            "score": round(float(score), 3),
        }


# Singleton del motor para toda la app (se usa desde la Fase 4).
_engine: RAGEngine | None = None


def get_rag_engine() -> RAGEngine:
    """Devuelve el motor RAG único de la aplicación (inicialización perezosa)."""
    global _engine
    if _engine is None:
        _engine = RAGEngine()
    return _engine
