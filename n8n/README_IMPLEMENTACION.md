# n8n + Groq + Pinecone + Twilio Sandbox

Este directorio contiene todo lo necesario para implementar:

- Ingesta de propiedades CSV hacia Pinecone.
- Bot de WhatsApp con Twilio Sandbox.
- Respuesta con Groq y recuperacion RAG.

## Archivos incluidos

- `workflow_ingesta_pinecone.json`
- `workflow_whatsapp_rag.json`
- `workflow_whatsapp_mvp.json` (MVP sin Pinecone/HF; ver `README_MVP.md`)
- `n8n.env.example`
- `n8n_mvp.env.example` (variables mínimas para el MVP)

## 1) Credenciales y prerequisitos

### Groq
- Crear API key en Groq Cloud.
- Guardarla como credencial en n8n:
  - Tipo: `HTTP Header Auth` o credencial equivalente de Groq.
  - Header: `Authorization`
  - Value: `Bearer {{GROQ_API_KEY}}`

### Pinecone
- Crear proyecto e indice.
- Sugerido:
  - Index: `tandil-props`
  - Metric: `cosine`
  - Dimension: `384` (si usas `sentence-transformers/all-MiniLM-L6-v2` en HF Inference)
- Crear API key y guardarla en n8n.

### Twilio Sandbox (WhatsApp)
- Activar Sandbox en Twilio -> Messaging -> Try it out -> Send a WhatsApp message.
- Unir tu numero enviando el codigo al numero de sandbox.
- Guardar credenciales en n8n:
  - Account SID
  - Auth Token
  - From: numero sandbox `whatsapp:+14155238886` (o el que Twilio muestre)

## 2) Variables recomendadas en n8n

Podras cargarlas con `n8n.env.example`:

- `GROQ_API_KEY`
- `GROQ_MODEL` (ej: `llama-3.3-70b-versatile`)
- `PINECONE_API_KEY`
- `PINECONE_INDEX_HOST` (host completo del indice)
- `PINECONE_NAMESPACE` (ej: `tandil-props`)
- `HF_EMBEDDING_MODEL` (ej: `sentence-transformers/all-MiniLM-L6-v2`)
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_FROM`

## 3) Flujo de ingesta (CSV -> Embeddings -> Pinecone)

Importar `workflow_ingesta_pinecone.json` y configurar:

1. `Read CSV`:
   - Ruta default: `D:\\Disco c original\\Proyectos\\script_scrapping\\propiedades_vivas.csv`
2. `Normalize Property Document`:
   - Crea campo `content` y metadata (`property_id`, `barrio`, `precio`).
3. `Get HF Embeddings`:
   - Llama HF Inference API para convertir `content` a vector.
4. `Upsert Pinecone`:
   - Inserta vector + metadata en namespace definido.

Resultado esperado:
- Registros insertados en Pinecone con ID de propiedad.

## 4) Flujo WhatsApp RAG (Twilio -> Retrieval -> Groq -> Twilio)

Importar `workflow_whatsapp_rag.json` y configurar:

1. `Webhook Twilio Incoming` (POST)
2. `Normalize Incoming`
   - Usa `Body` y `From` del payload Twilio.
3. `Get Query Embedding` (HF)
4. `Pinecone Query TopK`
   - TopK: 5
   - score threshold recomendado: 0.75
5. `Build Context + Prompt`
   - Prompt base:
     - "Sos un asesor inmobiliario experto en Tandil. Respondes cordial. Si no sabes algo, no inventes."
6. `Groq Chat Completion`
7. `Twilio Send Message`

## 5) Memoria de 2 mensajes (Window Buffer)

Hay dos caminos:

- Recomendado: usar nodo `Window Buffer Memory` de n8n AI (si lo tenes disponible).
- Alternativa incluida en el flujo: guardar ultimos mensajes por `From` en `staticData` y truncar a 2 pares (usuario/asistente).

## 6) Exponer n8n local y conectar webhook

### Opcion Ngrok
1. `ngrok http 5678`
2. Copiar URL HTTPS publica (ej: `https://abc123.ngrok-free.app`)
3. Configurar en Twilio Sandbox:
   - `When a message comes in` -> `POST https://abc123.ngrok-free.app/webhook/twilio-whatsapp`

### Opcion Localtunnel
1. `npx localtunnel --port 5678`
2. Configurar misma URL en Twilio.

## 7) Pruebas E2E recomendadas

1. "Busco depto 2 ambientes en Tandil hasta USD 90.000"
2. "Tenes algo en Rauch?"
3. "Mostrame opciones similares a la anterior"
4. Caso sin resultados: "Busco castillo frente al mar en Tandil por USD 30.000"

Validar:
- No inventa propiedades.
- Cita ID y datos del contexto recuperado.
- Mantiene contexto corto de conversacion.

## 8) Troubleshooting rapido

- `401 Groq`: revisar API key.
- `400 Pinecone dimension mismatch`: la dimension del indice no coincide con embedding model.
- `Twilio no entrega`: revisar webhook URL publica y metodo POST.
- `Respuestas vagas`: aumentar topK a 7 o mejorar prompt con formato de salida.
