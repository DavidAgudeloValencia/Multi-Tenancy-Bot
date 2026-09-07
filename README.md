# MultiBot — Asistente WhatsApp Multi-Tenant (Multi-Tenancy Dinámico)

> Plataforma de agentes conversacionales en **WhatsApp** con arquitectura
> **multi-tenant**: un solo despliegue atiende a muchos agentes/asesores, cada
> uno con su número, su base de conocimiento (RAG) y su asesor humano.
> **100% en la nube** — sin instalar software en los equipos de los agentes.

## Funcionalidades

| Capacidad | Descripción |
|---|---|
| **Atención y soporte (RAG)** | Responde dudas operativas leyendo una base de conocimiento en PDF (condicionados, directorios, FAQs) con **cero alucinaciones** (temperature 0 + umbral de relevancia + fallback controlado + fuentes trazables). |
| **Filtro de ventas (Lead Scoring)** | Detecta intención de compra, captura el perfil con 3-4 preguntas, y notifica al asesor humano para cerrar la venta (handoff con pausa de la IA). |
| **Multi-tenant aislado** | Cada agente tiene su número, su colección vectorial, sus sesiones (prefijadas en Redis) y su asesor, sin colisiones entre sí. |
| **Panel de administración web** | Crear/configurar agentes, editar el perfil de cada bot (saludo, preguntas, modelo IA), subir PDFs y re-ingestar sin tocar código. |
| **Seguridad** | Webhook con firma HMAC, API admin autenticada (tiempo constante), rate limiting, subida validada de PDFs, secretos nunca expuestos, escritura atómica. |

## Arquitectura

```text
WhatsApp (Meta Cloud API) ── POST /webhook (firma HMAC) ──► FastAPI
                                                            │ enruta por phone_number_id
                                                            ▼
                                                  Runtime del agente (tenant)
                                                      ├─ Router de intención (LLM)
                                                      ├─ Motor RAG (ChromaDB)
                                                      ├─ Flujo de venta (lead scoring)
                                                      └─ Notificador al asesor
                                                            │
                                      Respuesta enviada DESDE el número del agente
```

**Persistencia:** ChromaDB (vectores del conocimiento por agente) · Redis
(sesiones de conversación, TTL 24 h) · `data/tenants.json` (registro de
agentes). Sin base relacional: solo estado temporal y conocimiento.

## Stack

Python 3.11 · FastAPI (async) · Meta WhatsApp Cloud API · LangChain · OpenAI
(`gpt-4o-mini`, `text-embedding-3-small`) · ChromaDB · Redis · httpx ·
Docker / Docker Compose · pytest.

## Empezar

### 1. Configuración

```bash
cp .env.example .env      # y completar (ver tabla de variables abajo)
```

### 2. Ejecución local

```bash
python -m venv .venv && source .venv/bin/activate   # o .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Con Docker

```bash
docker compose up -d --build
# Ingestar la base de conocimiento de un agente:
docker compose run --rm api python -m scripts.ingest --tenant <id> --reset
```

### 4. Pruebas

```bash
pytest -q      # 44 tests (webhook, RAG, conversación, envío, multi-tenant, seguridad)
```

## Variables de entorno (`.env`)

| Variable | Descripción |
|---|---|
| `WHATSAPP_VERIFY_TOKEN` | Token de verificación del webhook |
| `WHATSAPP_ACCESS_TOKEN` | System User Token permanente (envío de mensajes) |
| `WHATSAPP_PHONE_NUMBER_ID` | ID del número en la Graph API (por defecto) |
| `WHATSAPP_API_VERSION` | Versión de la Graph API (p. ej. `v21.0`) |
| `OPENAI_API_KEY` | Clave de OpenAI (embeddings + respuestas) |
| `OPENAI_MODEL` / `OPENAI_EMBEDDING_MODEL` | Modelos de chat y vectores |
| `RAG_TEMPERATURE` / `RAG_TOP_K` / `RAG_SCORE_THRESHOLD` | Parámetros del RAG |
| `KNOWLEDGE_DIR` / `CHROMA_PERSIST_DIR` / `CHROMA_COLLECTION` | Conocimiento y vectores |
| `SESSION_STORE` (`memory`\|`redis`) / `REDIS_URL` / `SESSION_TTL_SECONDS` | Sesiones |
| `ADVISOR_NOTIFY_WHATSAPP` | Asesor por defecto para notificar leads |
| `TENANTS_FILE` | Ruta del registro de agentes (JSON) |
| `ADMIN_API_KEY` | Clave del panel de administración |
| `WEBHOOK_APP_SECRET` | App Secret de Meta (firma del webhook) |
| `DATABASE_URL` | Base relacional (SQLite dev · PostgreSQL prod) |
| `CRM_PROVIDER` | `native` (helpdesk propio) \| `mock` (demo) |
| `CRM_ENABLED` | `true` para sincronizar webhook → tickets |

> `.env` contiene secretos y **no se versiona**.

## Estructura

```text
main.py                 # Entry point FastAPI (uvicorn main:app)
app/
  config.py             # Configuración (pydantic-settings)
  db.py                 # SQLAlchemy async (engine/sesiones)
  models.py             # TicketMapping, ConversationMessage
  api/admin.py          # API del panel (autenticada)
  core/                 # logging, session (Memory/Redis), ratelimit
  crm/                  # ICrmAdapter (base) + native (helpdesk propio) + mock (demo)
  schemas/              # Pydantic: payload de Meta, datos del panel
  services/             # whatsapp, ingestion, rag, router, conversation,
                        # notifier, tenants, runtime, tickets
scripts/                # generate_sample_kb, ingest, ask, diagnose_meta
static/index.html       # Panel web de administración
knowledge/              # PDFs de la base de conocimiento (por agente)
tests/                  # Suite pytest
Dockerfile · docker-compose.yml · railway.json · .github/workflows/ci.yml
DESIGN.md               # Sistema de diseño (tokens, modo oscuro)
```

## Multi-tenant: agregar un agente

Cada agente se define en `data/tenants.json` (o desde el panel web):

```json
{
  "id": "agente-ejemplo",
  "name": "Agente de Ejemplo",
  "phone_number_id": "123456789012345",
  "advisor_notify_whatsapp": "573001234567"
}
```

- `phone_number_id`: identifica al agente en el webhook (`metadata.phone_number_id`).
- `access_token` vacío → usa el token global del `.env`.
- `collection`/`knowledge_dir` vacíos → derivados (`multibot_kb_{id}` y `knowledge/{id}`).

Luego cargar sus PDFs en `knowledge/{id}/` y ejecutar:

```bash
python -m scripts.ingest --tenant agente-ejemplo --reset
```

El enrutamiento, las sesiones, el conocimiento y las notificaciones quedan
aislados por agente automáticamente.

## API de administración (`/api/admin`, header `X-Admin-Key`)

| Método / ruta | Acción |
|---|---|
| `GET/POST /api/admin/tenants` | Listar / crear agentes |
| `GET/PUT/DELETE /api/admin/tenants/{id}` | Consultar / actualizar / eliminar |
| `POST /api/admin/tenants/{id}/documents` | Subir PDFs (validados) |
| `POST /api/admin/tenants/{id}/ingest` | Re-ingestar el conocimiento |
| `POST /api/admin/reload` | Recargar el registro desde disco |

Panel web: `GET /admin/`.

### API del panel de agentes (`/api/agent`, header `X-Admin-Key`)

| Método / ruta | Acción |
|---|---|
| `GET /api/agent/tenants/{id}/tickets` | Listar tickets (filtro `?status=`) |
| `GET /api/agent/tenants/{id}/tickets/{ticket_id}` | Detalle: ticket + historial + notas |
| `POST .../tickets/{ticket_id}/claim` | Reclamar (lock con `CLAIM_TTL_SECONDS`) |
| `POST .../tickets/{ticket_id}/release` | Liberar (solo el dueño) |
| `POST .../tickets/{ticket_id}/transfer` | Transferir a otro agente con nota |
| `POST .../tickets/{ticket_id}/notes` | Añadir nota interna |
| `POST .../tickets/{ticket_id}/reply` | Responder al cliente por WhatsApp |

## Plataforma de atención (helpdesk propio)

Sprint 0 disponible: **helpdesk nativo** (sin CRMs externos) con tickets,
notas internas, asignación y estados propios, sincronizado con WhatsApp.

- `CRM_PROVIDER=native` → tickets en nuestras tablas (`tickets`, `ticket_notes`,
  `ticket_mappings`, `conversation_messages`).
- `CRM_ENABLED=true` → el webhook crea el ticket al primer mensaje, lo
  actualiza en los siguientes y guarda el histórico (entrada/salida).
- El contrato `ICrmAdapter` define la funcionalidad (referencia de lo que hacen
  Zendesk/Freshdesk: assignee, estado, prioridad, notas), implementada por
  `NativeCrmAdapter` sobre nuestro propio backend.
- **En camino:** panel de agentes (claim/transfer/notas), login con Google,
  reglas de enrutamiento y métricas por tenant.

## Seguridad

- Webhook: firma `X-Hub-Signature-256` (HMAC-SHA256) — obligatoria en producción (`WEBHOOK_APP_SECRET`).
- Panel/API admin: `ADMIN_API_KEY` comparada en tiempo constante + rate limiting (30 req/min).
- Secretos enmascarados en las respuestas (`access_token_configured`).
- Subida de PDFs con validación de magic bytes, tamaño y nombre (anti path-traversal).
- Escritura atómica de `tenants.json`; sin CORS abierto; rate limiting del webhook (300 req/min).

Ver `DESIGN.md` para el sistema de diseño (tema oscuro, tokens, componentes).

## Despliegue en Railway

El repo ya incluye `railway.json` y el `Dockerfile` escucha en `$PORT`
(Railway lo inyecta). Pasos en [Railway.app](https://railway.app):

1. **New Project → Deploy from GitHub repo** y selecciona este repositorio.
   Railway detecta el `Dockerfile` automáticamente.
2. **Añade un plugin Redis** (New → Database → Redis). Su URL se expone como
   `${{Redis.REDIS_URL}}`.
3. **Añade un volumen** (New → Volume) montado en **`/app/data`** (persiste
   ChromaDB, `tenants.json` y los PDFs subidos).
4. **Variables de entorno** (en el servicio API):

   | Variable | Valor |
   |---|---|
   | `REDIS_URL` | `${{Redis.REDIS_URL}}` (Referencia al plugin) |
   | `SESSION_STORE` | `redis` |
   | `CHROMA_PERSIST_DIR` | `/app/data/chroma` |
   | `KNOWLEDGE_DIR` | `/app/data/knowledge` |
   | `TENANTS_FILE` | `/app/data/tenants.json` |
   | `OPENAI_API_KEY` | tu clave |
   | `WHATSAPP_*` | token/número de Meta |
   | `WEBHOOK_APP_SECRET` | App Secret de Meta |
   | `ADMIN_API_KEY` | clave del panel (genera una larga) |

5. **Network → Generate Domain** → te da una URL pública
   `https://<servicio>.railway.app`. Usa
   `https://<servicio>.railway.app/webhook` como **Callback URL** en Meta.
6. **Configuración inicial de agentes y conocimiento:**
   - Crea los agentes desde el panel (`/admin`) o con `tenants.json`.
   - Sube sus PDFs por el panel y ejecuta **Re-ingestar** (o en la consola de
     Railway: `python -m scripts.ingest --tenant <id> --reset`).

> El webhook se sirve en la raíz de la app (`/webhook`); el healthcheck usa `/`.

## Puesta en producción

1. Número de WhatsApp **real y dedicado** (o vía BSP) + *Go Live* en Meta (verificación de negocio).
2. Callback URL real con **HTTPS** (`https://tu-dominio/webhook`) — sin túneles.
3. Plantillas aprobadas en el Template Manager para mensajes iniciados por el bot.
4. `SESSION_STORE=redis`; `WEBHOOK_APP_SECRET` y `ADMIN_API_KEY` definidos.
5. Cargar los PDFs reales de cada agente y re-ingestar.
6. Cumplimiento (Colombia): Ley 1581 de 2012 (habeas data); políticas de Meta (opt-in, ventana de 24 h).

## Licencia

Proyecto de **uso interno con licencia propietaria** (todos los derechos
reservados). No se permite copiar, modificar, distribuir ni usar con fines
comerciales sin autorización escrita del titular. Ver [LICENSE](LICENSE).
