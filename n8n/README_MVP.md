# MVP WhatsApp (Twilio + CSV + Groq)

Flujo sin Pinecone ni Hugging Face: lee `propiedades_vivas.csv`, filtra con reglas simples y responde con Groq.

## Archivo a importar

- [workflow_whatsapp_mvp.json](workflow_whatsapp_mvp.json)

En n8n: **Workflows** → **Import from file**.

## Credenciales (solo 2)

1. **Groq API** (`HTTP Header Auth`)  
   - Header: `Authorization`  
   - Value: `Bearer TU_GROQ_API_KEY`

2. **Twilio Sandbox** (`Twilio API`)  
   - Account SID + Auth Token

## Variables de entorno en n8n

Ver [n8n_mvp.env.example](n8n_mvp.env.example).

Mínimo:

- `GROQ_MODEL` (ej. `llama-3.3-70b-versatile`)
- `TWILIO_WHATSAPP_FROM` (ej. `whatsapp:+14155238886`)

## Ruta del CSV

En el nodo **Read Properties CSV** ajustá `filePath` si tu carpeta no es:

`D:\Disco c original\Proyectos\script_scrapping\propiedades_vivas.csv`

Si n8n corre en **Docker**, montá esa carpeta como volumen o copiá el CSV dentro del contenedor y usá la ruta interna.

## Webhook Twilio

1. Activá el workflow y copiá la URL del nodo **Webhook Twilio MVP** (POST).
2. Exponé n8n con Ngrok: `ngrok http 5678`
3. En Twilio Sandbox → **When a message comes in** → `POST https://TU_DOMINIO/webhook/whatsapp-mvp`

## Cadena de nodos

`Webhook` → `Save Last Twilio Message` → `Read Properties CSV` → `Filter and Build Prompt` (run once for all items) → `Groq Chat Completion` → `Extract Reply for Twilio` → `Twilio Send WhatsApp`

## Filtros soportados en el mensaje (ejemplos)

- Ciudad: palabras `tandil` o `rauch` en el texto.
- Ambientes: `2 amb` o `3 amb`.
- Precio máximo: `hasta USD 90000`, `hasta 90000`, `menos de 100000`.

Si no matchea nada, el catálogo va vacío y el prompt pide no inventar.
