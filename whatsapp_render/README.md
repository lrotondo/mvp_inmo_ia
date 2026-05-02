# WhatsApp MVP en Render (FastAPI + Twilio + Groq + CSV)

Servicio minimo que reemplaza n8n+ngrok para el bot de WhatsApp:

- Twilio Sandbox envia `POST` al endpoint publico.
- Se valida firma Twilio.
- Se leen propiedades desde `data/propiedades_vivas.csv`.
- Se filtra con reglas simples (barrio / ambientes / precio maximo).
- Groq redacta la respuesta.
- Se responde con **TwiML** (`<Message>`).

## Endpoints

- `GET /health` — healthcheck para Render
- `POST /twilio/whatsapp` — webhook de Twilio (WhatsApp)

## Variables de entorno (Render)

| Variable | Obligatoria | Descripcion |
|----------|-------------|-------------|
| `GROQ_API_KEY` | si | API key de Groq |
| `GROQ_MODEL` | no | Default: `llama-3.3-70b-versatile` |
| `TWILIO_AUTH_TOKEN` | si (prod) | Para validar `X-Twilio-Signature` |
| `PUBLIC_BASE_URL` | si (prod) | Ej: `https://tu-servicio.onrender.com` **sin** barra final. Debe coincidir con la URL configurada en Twilio. |
| `SKIP_TWILIO_SIGNATURE` | no | Si `1`, desactiva validacion (solo pruebas locales). |

## Twilio Sandbox

En **When a message comes in** (POST):

`https://TU_SERVICIO.onrender.com/twilio/whatsapp`

## Desarrollo local

```powershell
cd "D:\Disco c original\Proyectos\script_scrapping\whatsapp_render"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
$env:GROQ_API_KEY="..."
$env:TWILIO_AUTH_TOKEN="..."
$env:SKIP_TWILIO_SIGNATURE="1"
uvicorn app.main:app --reload --port 8000
```

Probar:

`http://127.0.0.1:8000/health`

## Render (Web Service)

1. New **Web Service** → conectar este repo/carpeta `whatsapp_render`.
2. **Build command:** `pip install -r requirements.txt`
3. **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Cargar variables de entorno (tabla de arriba).
5. Deploy y copiar URL publica `https://....onrender.com`
6. Setear `PUBLIC_BASE_URL` exactamente a esa URL (sin path).
7. Actualizar Twilio con `https://....onrender.com/twilio/whatsapp`

### Actualizar propiedades

Reemplaza `data/propiedades_vivas.csv` en el repo y redeploy (MVP). Mas adelante: Postgres o S3.

### Free tier

El plan free puede dormir el servicio; Twilio puede fallar en cold start. Para produccion conviene plan sin sleep.

## Filtros soportados en el mensaje

- `tandil` / `rauch` en el texto filtra por barrio.
- `2 amb`, `3 amb`, etc.
- `hasta USD 90000`, `hasta 90000`, `menos de 100000`.
