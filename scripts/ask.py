"""Prueba el motor RAG con preguntas reales (Fase 3).

Uso:
    python -m scripts.ask "¿Cómo pido un médico a domicilio?"
    python -m scripts.ask                    # modo interactivo

Requiere OPENAI_API_KEY en `.env` y haber ingerido antes la base de
conocimiento: `python -m scripts.ingest --reset`.
"""

import argparse
import sys

from app.core.logging import setup_logging
from app.services.rag import Answer, get_rag_engine


def show_answer(answer: Answer) -> None:
    """Imprime la respuesta y las fuentes usadas."""
    print(f"\nPregunta : {answer.question}")
    print(f"Respuesta: {answer.answer}\n")
    if answer.sources:
        print("Fuentes consultadas:")
        for source in answer.sources:
            print(
                f"  - {source['source']} (pág. {source['page']}) "
                f"relevancia={source['score']}"
            )
    print("-" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Consulta el motor RAG")
    parser.add_argument(
        "question",
        nargs="?",
        help="Pregunta (si se omite, entra en modo interactivo)",
    )
    args = parser.parse_args()

    setup_logging("INFO")
    engine = get_rag_engine()

    if args.question:
        show_answer(engine.ask(args.question))
        return

    print("Modo interactivo — escribe 'salir' para terminar.\n")
    while True:
        try:
            question = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in {"salir", "exit", "quit"}:
            break
        if question:
            show_answer(engine.ask(question))

    sys.exit(0)


if __name__ == "__main__":
    main()
