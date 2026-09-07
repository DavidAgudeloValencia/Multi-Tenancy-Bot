"""Configuración centralizada de la aplicación.

Todas las variables se leen de variables de entorno o del archivo `.env`
(ver `.env.example`). Un único punto de acceso: `get_settings()`.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Valores de configuración tipados de la aplicación."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Aplicación ---
    app_name: str = "MultiBot"
    app_env: str = "development"
    log_level: str = "INFO"

    # --- Meta WhatsApp Cloud API ---
    # Token de verificación del webhook (obligatorio desde la Fase 2).
    whatsapp_verify_token: str = ""
    # Token permanente del sistema (System User Token) — se usa desde la Fase 5.
    whatsapp_access_token: str = ""
    # ID del número de WhatsApp Business — se usa desde la Fase 5.
    whatsapp_phone_number_id: str = ""
    # Versión de la Graph API de Meta.
    whatsapp_api_version: str = "v21.0"

    # --- OpenAI (Fase 3) ---
    openai_api_key: str = ""
    # Modelo de chat (rápido y económico) y modelo de embeddings.
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    # Temperatura del LLM: 0.0 = determinista (cero alucinaciones).
    rag_temperature: float = 0.0

    # --- Base de conocimiento (RAG) ---
    knowledge_dir: str = "knowledge"
    chroma_persist_dir: str = "data/chroma"
    chroma_collection: str = "multibot_kb"
    rag_top_k: int = 4
    rag_score_threshold: float = 0.3

    # --- Sesión y conversación (Fase 4) ---
    # "memory" para desarrollo local sin Redis | "redis" para producción.
    session_store: str = "memory"
    redis_url: str = "redis://localhost:6379/0"
    # TTL de la sesión por cliente: 24 h (planning.md §4 - WhatsApp es asíncrono).
    session_ttl_seconds: int = 86400
    # Número del asesor (formato internacional) que recibe la notificación de
    # leads por WhatsApp. Vacío = solo se notifica por consola/log.
    advisor_notify_whatsapp: str = ""

    # --- Multi-tenant (Fase 7) ---
    # Archivo JSON con el registro de agentes/vendedores (ver tenants.example.json).
    tenants_file: str = "data/tenants.json"

    # --- Seguridad ---
    # Clave del panel de administración (header X-Admin-Key). Obligatoria para
    # usar el panel web. Genera una larga y aleatoria; nunca la subas a git.
    admin_api_key: str = ""
    # App Secret de Meta (App -> Settings -> Basic) para validar la FIRMA de los
    # webhooks (X-Hub-Signature-256). En producción es obligatorio configurarla.
    webhook_app_secret: str = ""

    # --- Plataforma de atención (CRM / tickets) ---
    # URL de la base de datos relacional (SQLAlchemy). SQLite para arrancar,
    # PostgreSQL en producción.
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    # Backend de tickets: "native" (helpdesk propio, por defecto) o "mock" (demo).
    crm_provider: str = "native"
    # Si True, el webhook crea/actualiza tickets por cada mensaje.
    crm_enabled: bool = False
    # TTL (segundos) del "claim" de un ticket por un agente (lock).
    claim_ttl_seconds: int = 900

    # --- Autenticación (Google OAuth + JWT) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""   # ej. https://<host>/auth/google/callback
    auth_jwt_secret: str = ""       # firma HS256 de los tokens de sesión
    auth_token_hours: int = 12

    # --- Cifrado en reposo ---
    # Clave Fernet (base64 de 32 bytes) para cifrar los access_token de los
    # agentes en tenants.json. Si está vacía, se guardan en texto plano (dev).
    secret_encryption_key: str = ""

    @property
    def graph_api_base_url(self) -> str:
        """URL base de la Graph API de Meta."""
        return f"https://graph.facebook.com/{self.whatsapp_api_version}"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la instancia única (cacheada) de Settings."""
    return Settings()
