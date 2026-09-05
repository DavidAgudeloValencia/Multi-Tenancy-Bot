"""Pipeline de ingesta de la base de conocimiento (Fase 3).

Carga los PDFs de la carpeta `knowledge/`, los divide en fragmentos
solapados, genera sus embeddings y los almacena en ChromaDB.

Uso (ver scripts/ingest.py):
    python -m scripts.ingest            # ingesta normal
    python -m scripts.ingest --reset    # borra la colección y reingesta
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from chromadb import PersistentClient
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings

logger = logging.getLogger("multibot.ingestion")

# Separadores que respetan la estructura del español (párrafos y oraciones).
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

_splitter: Any | None = None


def _get_text_splitter() -> Any:
    """Devuelve el text splitter (creación perezosa y tolerante a red).

    Prefiere división por tokens (tiktoken), pero si el encoding no está
    disponible localmente (sin red o descarga bloqueada), cae a división por
    caracteres para que el import nunca dependa de internet.
    """
    global _splitter
    if _splitter is None:
        try:
            _splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
                model_name="text-embedding-3-small",
                chunk_size=800,
                chunk_overlap=100,
                separators=_SEPARATORS,
            )
        except Exception as exc:  # noqa: BLE001 - tiktoken puede requerir descarga
            logger.warning(
                "tiktoken no disponible (%s); se usará división por caracteres",
                exc,
            )
            _splitter = RecursiveCharacterTextSplitter(
                chunk_size=800,
                chunk_overlap=100,
                separators=_SEPARATORS,
            )
    return _splitter


def load_pdfs(knowledge_dir: Path) -> list[Document]:
    """Carga todos los PDFs de un directorio como documentos LangChain.

    Cada página de un PDF se convierte en un Document con metadatos
    `source` (ruta del archivo) y `page` (número de página).
    """
    documents: list[Document] = []
    pdf_files = sorted(knowledge_dir.glob("*.pdf"))
    if not pdf_files:
        logger.warning("No se encontraron PDFs en %s", knowledge_dir)
        return documents

    for pdf_path in pdf_files:
        loader = PyPDFLoader(str(pdf_path))
        pages = loader.load()
        logger.info("Cargado %s (%d página(s))", pdf_path.name, len(pages))
        documents.extend(pages)

    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    """Divide los documentos en fragmentos solapados (chunks)."""
    chunks = _get_text_splitter().split_documents(documents)
    logger.info("Documentos divididos en %d fragmento(s)", len(chunks))
    return chunks


def _chunk_id(chunk: Document) -> str:
    """ID determinista por contenido: re-ingestar reemplaza (upsert) el chunk."""
    source = chunk.metadata.get("source", "unknown")
    page = chunk.metadata.get("page", 0)
    raw = f"{source}|{page}|{chunk.page_content}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def ingest_documents(
    knowledge_dir: Path | str | None = None,
    persist_dir: Path | str | None = None,
    collection_name: str | None = None,
    embedding_function: Embeddings | None = None,
    reset: bool = False,
    tenant_id: str | None = None,
) -> dict:
    """Ejecuta el pipeline completo de ingesta y devuelve un resumen.

    Args:
        knowledge_dir: carpeta con los PDFs (por defecto `settings.knowledge_dir`).
        persist_dir: carpeta de persistencia de ChromaDB.
        collection_name: nombre de la colección vectorial.
        embedding_function: proveedor de embeddings (por defecto OpenAI).
        reset: si True, borra la colección antes de ingestar (reemplaza todo).
        tenant_id: si se indica, ingesta SOLO el conocimiento de ese agente
            (su carpeta `knowledge/{id}` y su colección `multibot_kb_{id}`).

    Returns:
        Dict con el resumen: {"status": "ok", "chunks": N, "pdfs": M}.
    """
    settings = get_settings()

    # Multi-tenant: resolver carpeta y colección del agente.
    if tenant_id:
        from app.services.tenants import get_tenant_registry

        tenant = get_tenant_registry().get(tenant_id)
        if tenant is None:
            return {"status": "error", "detail": f"El agente '{tenant_id}' no existe en tenants.json"}
        knowledge_dir = Path(knowledge_dir or tenant.effective_knowledge_dir)
        collection_name = collection_name or tenant.effective_collection

    knowledge_dir = Path(knowledge_dir or settings.knowledge_dir)
    persist_dir = Path(persist_dir or settings.chroma_persist_dir)
    collection_name = collection_name or settings.chroma_collection
    embedding_function = embedding_function or OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )

    documents = load_pdfs(knowledge_dir)
    if not documents:
        return {"status": "error", "detail": f"No hay PDFs en {knowledge_dir}"}

    chunks = split_documents(documents)

    persist_dir.mkdir(parents=True, exist_ok=True)
    client = PersistentClient(
        path=str(persist_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )

    if reset:
        try:
            client.delete_collection(collection_name)
            logger.info("Colección '%s' eliminada (reset)", collection_name)
        except Exception:  # noqa: BLE001 - la colección puede no existir aún
            pass

    vectorstore = Chroma(
        client=client,
        collection_name=collection_name,
        embedding_function=embedding_function,
        collection_metadata={"hnsw:space": "cosine"},
    )

    ids = [_chunk_id(chunk) for chunk in chunks]
    vectorstore.add_documents(chunks, ids=ids)
    logger.info(
        "Ingesta completada: %d fragmento(s) en la colección '%s'",
        len(chunks),
        collection_name,
    )

    return {
        "status": "ok",
        "chunks": len(chunks),
        "pdfs": len(documents),
    }
