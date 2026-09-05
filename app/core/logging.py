"""Configuración del logging de la aplicación (salida a consola)."""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configura el logger raíz con formato legible y salida a stdout.

    `force=True` garantiza que la configuración se aplique incluso si el
    intérprete ya tenía un logging definido (ej. con `--reload`).
    """
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
