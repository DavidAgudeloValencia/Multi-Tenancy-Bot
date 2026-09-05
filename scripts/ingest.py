"""Ingesta la base de conocimiento a ChromaDB (Fase 3 + multi-tenant).

Uso:
    python -m scripts.ingest                                  # ingesta global
    python -m scripts.ingest --reset                          # borra y reingesta
    python -m scripts.ingest --tenant juan --reset            # solo el agente 'juan'
    python -m scripts.ingest --dir ../otros_pdfs              # otra carpeta de PDFs

Multi-tenant: cada agente (tenants.json) tiene su carpeta `knowledge/{id}` y
su colección `multibot_kb_{id}`. Ingiere su conocimiento con `--tenant`.

Requiere OPENAI_API_KEY en `.env` (para los embeddings).
"""

import argparse

from app.core.logging import setup_logging
from app.services.ingestion import ingest_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta de PDFs a ChromaDB")
    parser.add_argument("--dir", default=None, help="Carpeta con los PDFs")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Borrar la colección y reingestar desde cero",
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help="ID del agente (tenants.json) cuyo conocimiento se ingesta",
    )
    args = parser.parse_args()

    setup_logging("INFO")
    result = ingest_documents(
        knowledge_dir=args.dir,
        reset=args.reset,
        tenant_id=args.tenant,
    )

    if result["status"] == "ok":
        scope = f" del agente '{args.tenant}'" if args.tenant else " global"
        print(
            f"OK: {result['chunks']} fragmento(s) indexados{scope} "
            f"(a partir de {result['pdfs']} página(s))."
        )
    else:
        print(f"ERROR: {result['detail']}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
