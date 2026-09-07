# Planning Document: Agente IA para Asesores de Seguros en WhatsApp

## 1. Perfil y Mapeo del Asesor de Seguros

Para que el agente sea verdaderamente útil, debe entender el día a día de un asesor de seguros (ej. seguros de vida, salud, autos, pólizas empresariales) en el contexto local (EPS, SOAT, ARL, medicina prepagada, seguros todo riesgo).

### 1.1. Objetivos Principales del Asesor
*   **Ventas (Adquisición):** Prospectar, cotizar y cerrar nuevas pólizas.
*   **Mantenimiento (Fidelización):** Recordar renovaciones, procesar pagos, actualizar datos.
*   **Servicio (Soporte Operativo):** Guiar en caso de siniestros, solicitar asistencias, emitir certificados. Aquí es donde se pierde la mayor parte del tiempo productivo.

### 1.2. Mapeo de Casos de Uso (Flujos del Bot)

**A. Flujo de Soporte y Asistencia (100% Automatizable)**
*   *Siniestros de Auto:* "Me choqué", "Necesito grúa", "Me robaron el carro". El bot debe pedir ubicación, fotos básicas y entregar el número de siniestros de la aseguradora (ej. Salud, SegurosGo).
*   *Asistencia en Salud:* "Cómo pido médico a domicilio", "Dónde descargo el carné", "Directorio médico". El bot consulta la base de conocimiento (RAG) y entrega links exactos o teléfonos.
*   *Gestión Administrativa:* "Cómo pago mi cuota", "Necesito copia de la póliza". 

**B. Flujo de Ventas y Cotizaciones (Lead Scoring & Calificación)**
*   *Prospecto:* "Quiero cotizar un seguro para mi moto o carro".
*   *Acción del Bot:* Captura marca, modelo, año, placa, edad del conductor, ciudad.
*   *Handoff (Transferencia):* Envía el resumen estructurado al asesor para que este solo tenga que generar la cotización y cerrar la venta.

---

## 2. Arquitectura de la Solución (Stack Python)

Al utilizar Python, ganamos acceso al ecosistema más robusto de IA y manejo de datos.

*   **API / Webhook:** FastAPI (Asíncrono, rápido, excelente para manejar miles de mensajes entrantes).
*   **Orquestación IA:** LangChain o LlamaIndex.
*   **Motor LLM:** OpenAI API (GPT-4o-mini para velocidad/costo, o GPT-4o para razonamiento complejo).
*   **Base de Conocimiento (Vector Store):** ChromaDB (local/rápido) o PostgreSQL + pgvector (escalable, ideal si se integra con bases de datos relacionales).
*   **Comunicación:** Meta Cloud API (WhatsApp Business oficial).
*   **Despliegue:** Contenedores Docker (Docker Compose para levantar API + Redis + Postgres).

---

## 3. Plan de Implementación Paso a Paso (Guía del Desarrollador)

### Fase 1: Pre-requisitos Fuera del Código (Configuración de Cuentas)
Esta fase requiere intervención manual en plataformas de terceros.

1.  **Meta Developer Portal:**
    *   Crear una cuenta en [Facebook for Developers].
    *   Crear una App tipo "Negocios" (Business).
    *   Añadir el producto "WhatsApp".
    *   Vincular un número de teléfono (debe ser un número dedicado, no el personal del asesor).
    *   Generar un Token de Acceso Permanente (System User Token) en el Business Manager.
2.  **OpenAI:**
    *   Crear cuenta en OpenAI Platform, añadir saldo y generar una API Key.
3.  **Infraestructura Local:**
    *   Instalar `ngrok` para exponer el puerto local de FastAPI y poder verificar el Webhook de Meta durante el desarrollo.

### Fase 2: Configuración del Webhook con FastAPI
El bot necesita "escuchar" los mensajes que llegan a WhatsApp.

1.  **Crear el proyecto:**
    *   `mkdir seguro-bot && cd seguro-bot`
    *   `python -m venv venv && source venv/bin/activate`
    *   `pip install fastapi uvicorn requests python-dotenv`
2.  **Endpoints Core (`main.py`):**
    *   `GET /webhook`: Endpoint para que Meta verifique la URL (Meta enviará un `hub.challenge` y un `hub.verify_token`).
    *   `POST /webhook`: Endpoint donde Meta enviará los payloads JSON cada vez que alguien escriba al WhatsApp.
3.  **Prueba local:** Ejecutar `uvicorn main:app --reload` y usar `ngrok http 8000` para configurar la URL en Meta.

### Fase 3: Motor RAG (Retrieval-Augmented Generation)
Aquí es donde el bot aprende sobre seguros para no alucinar.

1.  **Recolección de Datos:** Reunir PDFs de condicionados generales, manuales de asistencia y preguntas frecuentes.
2.  **Pipeline de Ingesta (LangChain):**
    *   Cargar los documentos (PyPDFLoader).
    *   Dividirlos en fragmentos (RecursiveCharacterTextSplitter).
    *   Convertirlos a vectores (OpenAIEmbeddings) y guardarlos en ChromaDB.
3.  **Prompt Engineering (El System Prompt):**
    *   *Rol:* "Eres un asistente virtual de un asesor de seguros experto. Tu objetivo es resolver dudas operativas (siniestros, certificados) basándote SOLO en la base de datos provista. Si un cliente quiere comprar, haz 3 preguntas clave y transfiérelo a un humano. No inventes coberturas ni teléfonos."

### Fase 4: Enrutamiento y Lógica Conversacional
El flujo del `POST /webhook` debe seguir esta lógica:

1.  **Parsear el Mensaje:** Extraer el número de teléfono del usuario y el texto.
2.  **Clasificación de Intención (Router LLM):** El mensaje entra a un prompt inicial muy rápido. ¿Es Ventas, Siniestro, o Duda General?
3.  **Ejecución de Intención:**
    *   *Si es Siniestro/Duda:* Ejecutar el pipeline RAG, buscar en ChromaDB, formular respuesta, enviar a Meta API.
    *   *Si es Ventas:* Verificar el estado de la conversación (Redis o base de datos ligera para mantener estado de la sesión). Hacer preguntas secuenciales (¿Qué vehículo es? ¿Modelo?).
4.  **Handoff a Humano:** Cuando el lead está calificado o el usuario pide hablar con un humano, el bot pausa la IA para ese número de teléfono y envía una notificación (vía Telegram o email) al asesor con el resumen del caso.

### Fase 5: Enviar Mensajes a Meta API
Se debe construir una función utilitaria en Python para enviar la respuesta:

```python
import requests

def send_whatsapp_message(to_number, message_text, token):
    url = f"https://graph.facebook.com/v17.0/{{PHONE_NUMBER_ID}}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message_text}
    }
    requests.post(url, headers=headers, json=payload)
```

### Fase 6: Despliegue en Producción (Docker)
Para asegurar que todo funcione en cualquier servidor (ej. un VPS básico en DigitalOcean o AWS EC2).

1.  **Dockerfile:** Empaquetar la app FastAPI.
2.  **docker-compose.yml:** Levantar la API, un contenedor de Redis (para gestionar el estado y memoria de las conversaciones de cada cliente) y opcionalmente PostgreSQL.
3.  **CI/CD:** Configurar un pipeline básico para que cada push al repositorio actualice el servidor.

---

## 4. Consideraciones Finales y Mejores Prácticas

*   **Evitar Alucinaciones (Crítico en Seguros):** Establecer el parámetro `temperature=0` en las respuestas basadas en documentos y configurar un "Fallback" que diga: "Para esa duda específica sobre tu cobertura, prefiero que hables con tu asesor. ¿Te agendo una llamada?".
*   **Gestión de Estados:** WhatsApp es asíncrono. Un cliente puede escribir hoy y luego en 3 días. Usar Redis con un TTL (Time To Live) de 24 horas para recordar el contexto de la conversación reciente.
*   **Aprobaciones de Plantillas (Templates):** Si el bot necesita iniciar la conversación (ej. enviar un recordatorio de renovación), Meta exige usar plantillas pre-aprobadas. El código debe contemplar el envío de `template` en vez de `text`.
