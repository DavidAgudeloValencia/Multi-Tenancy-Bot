"""Cifrado en reposo de secretos (tokens de acceso de los agentes).

Usa Fernet (AES-128-CBC + HMAC) con `SECRET_ENCRYPTION_KEY`. Los valores se
guardan con prefijo `enc:` cuando están cifrados; sin clave configurada se
mantiene el texto plano (compatibilidad con desarrollo).
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

_PREFIX = "enc:"


def _fernet() -> Fernet | None:
    key = get_settings().secret_encryption_key
    if not key:
        return None
    return Fernet(key.encode("utf-8"))


def encrypt_secret(plain: str) -> str:
    """Cifra un secreto. Sin clave configurada, lo devuelve sin cifrar."""
    if not plain:
        return plain
    fernet = _fernet()
    if fernet is None:
        return plain
    return _PREFIX + fernet.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(stored: str) -> str:
    """Descifra un secreto (acepta texto plano legado sin romper)."""
    if not stored:
        return ""
    fernet = _fernet()
    if fernet is None or not stored.startswith(_PREFIX):
        return stored  # sin clave o ya en texto plano
    try:
        return fernet.decrypt(stored[len(_PREFIX):].encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # No se pudo descifrar (clave rotada o dato corrupto): devolver tal cual
        # evita romper el arranque; el operador verá el error al usarlo.
        return stored
