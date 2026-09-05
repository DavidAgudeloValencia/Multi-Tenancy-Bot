"""Pruebas del motor RAG (Fase 3) — se ejecutan SIN llamar a OpenAI.

Usan embeddings deterministas (`FakeEmbeddings`) y un LLM falso, por lo que
funcionan sin API key. Cubren: ingesta a ChromaDB, recuperación con contexto
y fallback anti-alucinación cuando no hay información relevante.

Ejecutar con:  pytest -q
"""

from __future__ import annotations

import re
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.embeddings import Embeddings
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate

from app.services.ingestion import ingest_documents
from app.services.rag import FALLBACK_ANSWER, RAGEngine


class FakeEmbeddings(Embeddings):
    """Embeddings deterministas por presencia de tokens (solo pruebas)."""

    def __init__(self, dim: int = 512) -> None:
        self._dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for token in re.findall(r"[a-záéíóúñ]+", text.lower()):
            vec[zlib.crc32(token.encode("utf-8")) % self._dim] = 1.0
        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeLLM:
    """LLM falso que devuelve una respuesta fija (no llama a OpenAI)."""

    def invoke(self, messages: list) -> SimpleNamespace:
        return SimpleNamespace(
            content="Respuesta basada en el contexto proporcionado."
        )


@pytest.fixture
def knowledge_dir(tmp_path: Path) -> Path:
    """Crea un PDF de prueba en un directorio temporal."""
    pdf_path = tmp_path / "guia_asistencias.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
    styles = getSampleStyleSheet()
    doc.build(
        [
            Paragraph("Guía de Asistencias", styles["Title"]),
            Paragraph(
                "Para pedir un médico a domicilio, llama a la línea "
                "01 8000 789 123 disponible las 24 horas.",
                styles["BodyText"],
            ),
            Paragraph(
                "Para solicitar el carné digital ingresa a la aplicación "
                "Mi Salud en la sección Mi carné.",
                styles["BodyText"],
            ),
        ]
    )
    return tmp_path


@pytest.fixture
def engine(knowledge_dir: Path, tmp_path: Path) -> RAGEngine:
    """Ingesta el PDF de prueba y devuelve un motor RAG con dobles falsos."""
    persist = tmp_path / "chroma"
    result = ingest_documents(
        knowledge_dir=knowledge_dir,
        persist_dir=persist,
        collection_name="test_kb",
        embedding_function=FakeEmbeddings(),
        reset=True,
    )
    assert result["status"] == "ok"
    assert result["chunks"] > 0
    return RAGEngine(
        embedding_function=FakeEmbeddings(),
        llm=FakeLLM(),
        persist_dir=persist,
        collection_name="test_kb",
        score_threshold=0.3,
    )


def test_ingestion_ok(knowledge_dir: Path, tmp_path: Path) -> None:
    result = ingest_documents(
        knowledge_dir=knowledge_dir,
        persist_dir=tmp_path / "chroma",
        collection_name="test_kb",
        embedding_function=FakeEmbeddings(),
        reset=True,
    )
    assert result["status"] == "ok"
    assert result["chunks"] > 0
    assert result["pdfs"] > 0


def test_ask_uses_context(engine: RAGEngine) -> None:
    answer = engine.ask("¿Cómo pido un médico a domicilio?")
    assert answer.used_context is True
    assert answer.answer == "Respuesta basada en el contexto proporcionado."
    assert answer.sources, "Debe citar al menos una fuente"


def test_ask_fallback_when_no_context(engine: RAGEngine) -> None:
    answer = engine.ask("zzz qqq www yyy xxx vvv")
    assert answer.used_context is False
    assert answer.answer == FALLBACK_ANSWER


def test_ingestion_empty_dir_returns_error(tmp_path: Path) -> None:
    result = ingest_documents(
        knowledge_dir=tmp_path / "vacia",
        persist_dir=tmp_path / "chroma",
        collection_name="test_kb",
        embedding_function=FakeEmbeddings(),
    )
    assert result["status"] == "error"
