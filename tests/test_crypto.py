"""Pruebas de cifrado en reposo de secretos (tokens de agentes)."""

from __future__ import annotations

from types import SimpleNamespace

from cryptography.fernet import Fernet

from app.core.crypto import decrypt_secret, encrypt_secret
from app.services.tenants import TenantRegistry


def _key() -> str:
    return Fernet.generate_key().decode()


def test_encrypt_decrypt_roundtrip(monkeypatch) -> None:
    key = _key()
    monkeypatch.setattr(
        "app.core.crypto.get_settings",
        lambda: SimpleNamespace(secret_encryption_key=key),
    )
    encrypted = encrypt_secret("EAAG-super-secreto")
    assert encrypted.startswith("enc:")
    assert decrypt_secret(encrypted) == "EAAG-super-secreto"


def test_plaintext_without_key(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.crypto.get_settings",
        lambda: SimpleNamespace(secret_encryption_key=""),
    )
    assert encrypt_secret("abc") == "abc"
    assert decrypt_secret("abc") == "abc"


def test_registry_encrypts_tokens_at_rest(monkeypatch, tmp_path) -> None:
    key = _key()
    monkeypatch.setattr(
        "app.core.crypto.get_settings",
        lambda: SimpleNamespace(secret_encryption_key=key),
    )
    file = tmp_path / "tenants.json"
    registry = TenantRegistry(file)
    registry.create(
        "juan", {"access_token": "EAAG-super-secreto", "phone_number_id": "111"}
    )

    raw = file.read_text(encoding="utf-8")
    assert "EAAG-super-secreto" not in raw  # nunca en texto plano
    assert "enc:" in raw

    # Al recargar se descifra para uso en memoria
    reloaded = TenantRegistry(file)
    assert reloaded.get("juan").access_token == "EAAG-super-secreto"


def test_decrypt_tolerates_legacy_plaintext(monkeypatch) -> None:
    key = _key()
    monkeypatch.setattr(
        "app.core.crypto.get_settings",
        lambda: SimpleNamespace(secret_encryption_key=key),
    )
    # Un token que ya estaba en texto plano (sin prefijo) se devuelve tal cual
    assert decrypt_secret("EAAG-legado") == "EAAG-legado"
