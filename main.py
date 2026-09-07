"""
MultiBot — Agente conversacional para asesores de seguros (WhatsApp Cloud API)
===============================================================================

Fase 2: Configuración del Webhook con FastAPI.

Este módulo levanta el servidor HTTP que Meta (WhatsApp Cloud API) usa para
conectarse con nuestro bot:

    GET  /webhook  ->  Meta verifica que la URL pertenece a nuestro servidor.
    POST /webhook  ->  Meta entrega los mensajes entrantes de WhatsApp.

Arranque en desarrollo
----------------------
    python -m venv .venv
    .venv\\Scripts\\activate            (Windows)  o  source .venv/bin/activate
    pip install -r requirements.txt
    copy .env.example .env             y completar WHATSAPP_VERIFY_TOKEN
    uvicorn main:app --reload --port 8000

Para exponer el puerto local a Meta (durante el desarrollo):
    ngrok http 8000
    En Meta Developers -> App -> WhatsApp -> Configuration -> Webhook:
        Callback URL : https://<tu-subdominio>.ngrok.io/webhook
        Verify token : el valor de WHATSAPP_VERIFY_TOKEN en .env

Nota de arquitectura: el endpoint POST responde 200 de inmediato y el
procesamiento pesado (clasificación de intención, RAG, lead scoring) se
añadirá en las Fases 3-4, idealmente desacoplado con una cola de tareas
(Redis + RQ/Celery) para no bloquear la respuesta a Meta.
"""

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.agent import router as agent_router
from app.config import get_settings
from app.core.logging import setup_logging
from app.core.ratelimit import RateLimiter, make_rate_limit_dependency
from app.schemas.whatsapp import ChangeValue, Contact, Message, WebhookPayload
from app.services import whatsapp as whatsapp_service
from app.services.runtime import get_tenant_runtime
from app.services.tenants import get_tenant_registry

logger = logging.getLogger("multibot")
settings = get_settings()

# Límite del webhook: 300 req/min por IP (Meta entrega por ráfagas; protege
# contra inundación sin romper el flujo legítimo).
_webhook_limiter = RateLimiter(limit=300, window_seconds=60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Configura el logging, la BD y registra el arranque de la aplicación."""
    setup_logging(settings.log_level)
    if settings.crm_enabled:
        from app.db import init_db

        await init_db()
        logger.info("Base de datos inicializada (CRM/tickets)")
    logger.info("%s iniciado (entorno: %s)", settings.app_name, settings.app_env)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="Agente conversacional para asesores de seguros (WhatsApp Cloud API).",
    lifespan=lifespan,
)

# API de administración (autenticada con X-Admin-Key).
app.include_router(admin_router)

# API del panel de agentes (helpdesk).
app.include_router(agent_router)

# Panel web de administración (estático; los datos requieren la clave).
app.mount("/admin", StaticFiles(directory="static", html=True), name="admin-ui")


def _verify_meta_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Valida la firma HMAC-SHA256 que Meta añade en `X-Hub-Signature-256`.

    Si `WEBHOOK_APP_SECRET` no está configurado, se acepta (desarrollo) pero
    se registra una advertencia: en producción es OBLIGATORIO configurarlo.
    """
    secret = settings.webhook_app_secret
    if not secret:
        logger.warning("WEBHOOK_APP_SECRET sin configurar: webhook SIN verificación de firma.")
        return True
    if not signature_header:
        return False
    try:
        scheme, provided = signature_header.split("=", 1)
    except ValueError:
        return False
    if scheme != "sha256":
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ---------------------------------------------------------------------------
# GET /webhook — Verificación de la URL por parte de Meta
# ---------------------------------------------------------------------------
@app.get("/webhook", response_class=PlainTextResponse, tags=["webhook"])
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode", description="Siempre 'subscribe'"),
    hub_verify_token: str = Query(
        ..., alias="hub.verify_token", description="Token definido en .env"
    ),
    hub_challenge: str = Query(
        ..., alias="hub.challenge", description="Valor que Meta espera recibir de vuelta"
    ),
) -> str:
    """Valida la suscripción del webhook cuando Meta la configura.

    Meta llama a este endpoint con los parámetros `hub.*` y solo considera
    válida la suscripción si respondemos con el `hub.challenge` recibido.
    """
    if hub_mode == "subscribe" and hmac.compare_digest(
        hub_verify_token, settings.whatsapp_verify_token
    ):
        logger.info("Webhook verificado correctamente por Meta.")
        return hub_challenge

    logger.warning("Verificación de webhook rechazada (verify_token inválido).")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


# ---------------------------------------------------------------------------
# POST /webhook — Recepción de mensajes y estados de WhatsApp
# ---------------------------------------------------------------------------
@app.post(
    "/webhook",
    tags=["webhook"],
    dependencies=[Depends(make_rate_limit_dependency(_webhook_limiter))],
)
async def receive_webhook(request: Request, payload: WebhookPayload) -> dict[str, str]:
    """Recibe los eventos que Meta entrega por cada interacción en WhatsApp.

    Verifica la firma HMAC (`X-Hub-Signature-256`) antes de procesar para
    rechazar peticiones falsificadas. Meta envía dos familias de eventos en
    `entry[].changes[].value`:
      - `messages`: mensajes entrantes del cliente (lo que nos interesa).
      - `statuses`: confirmaciones de entrega/lectura (solo se registran).
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not _verify_meta_signature(raw_body, signature):
        logger.warning("Webhook rechazado: firma inválida o ausente.")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if payload.object != "whatsapp_business_account":
        logger.info("Evento ignorado (object=%s)", payload.object)
        return {"status": "ignored"}

    for entry in payload.entry:
        for change in entry.changes:
            value: ChangeValue = change.value

            if value.messages:
                for message in value.messages:
                    await handle_incoming_message(message, value)

            if value.statuses:
                for status in value.statuses:
                    logger.info(
                        "[Estado] msg_id=%s wa_id=%s status=%s",
                        status.id,
                        status.recipient_id,
                        status.status,
                    )

    logger.debug("Webhook procesado: %d entrada(s).", len(payload.entry))
    return {"status": "received"}


# ---------------------------------------------------------------------------
# Procesamiento de mensajes (Fase 4: enrutamiento + respuesta automática)
# ---------------------------------------------------------------------------
async def handle_incoming_message(message: Message, value: ChangeValue) -> None:
    """Enruta el mensaje entrante y responde automáticamente por WhatsApp.

    Multi-tenant (Fase 7): el número que RECIBIÓ el mensaje
    (`metadata.phone_number_id`) determina el agente (tenant) que lo atiende.
    Cada agente usa SU base de conocimiento, SU sesión y SU asesor, y la
    respuesta se envía desde SU número de WhatsApp.
    """
    wa_id = message.from_
    sender_name = _resolve_sender_name(value.contacts, wa_id)

    if message.type != "text" or not message.text:
        logger.info(
            "[Mensaje] de=%s (%s) -> tipo=%s (aún no soportado)",
            wa_id,
            sender_name,
            message.type,
        )
        return

    text = message.text.body
    logger.info("[Mensaje] de=%s (%s) -> %s", wa_id, sender_name, text)

    # 1) Resolver el agente dueño del número que recibió el mensaje.
    tenant = get_tenant_registry().by_phone_number_id(value.metadata.phone_number_id)
    if tenant is None:
        logger.warning(
            "Mensaje para phone_number_id=%s sin agente configurado "
            "(revisa data/tenants.json)",
            value.metadata.phone_number_id,
        )
        return

    if not tenant.enabled:
        logger.info("Agente '%s' deshabilitado; mensaje ignorado", tenant.id)
        return

    # 1.5) Sincronizar con el CRM (crear/actualizar ticket) si está activo.
    if settings.crm_enabled:
        from app.services.tickets import get_ticketing_service

        try:
            ticket = await get_ticketing_service().ensure_ticket(
                tenant.id, wa_id, text, requester=sender_name
            )
            logger.info(
                "Ticket %s para %s/%s (nuevo=%s)",
                ticket["ticket_id"], tenant.id, wa_id, ticket["created"],
            )
        except Exception as exc:  # noqa: BLE001 - el chat sigue aunque el CRM falle
            logger.error("No se pudo sincronizar el ticket CRM: %s", exc)

    # 2) Atender con el runtime del agente (RAG, sesión y asesor propios).
    runtime = get_tenant_runtime(tenant)
    reply = await runtime.handle_message(wa_id, text)

    # 3) Responder DESDE el número del agente.
    try:
        await whatsapp_service.send_text_message(
            wa_id,
            reply,
            phone_number_id=tenant.phone_number_id,
            access_token=tenant.effective_token,
        )
        logger.info("Respuesta enviada a %s desde el agente '%s'", wa_id, tenant.id)
        if settings.crm_enabled:
            from app.services.tickets import get_ticketing_service

            try:
                await get_ticketing_service().record_outbound(tenant.id, wa_id, reply)
            except Exception as exc:  # noqa: BLE001
                logger.error("No se pudo registrar la respuesta en el CRM: %s", exc)
    except Exception as exc:  # noqa: BLE001 - nunca romper el webhook
        logger.error("No se pudo enviar la respuesta a %s: %s", wa_id, exc)


def _resolve_sender_name(contacts: list[Contact], wa_id: str) -> str:
    """Busca el nombre del remitente en el bloque `contacts` del payload."""
    for contact in contacts:
        if contact.wa_id == wa_id and contact.profile:
            return contact.profile.name
    return "desconocido"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/", tags=["health"])
async def health() -> dict[str, str]:
    """Endpoint de salud para verificar que el servicio está vivo."""
    return {"status": "ok", "service": settings.app_name}
