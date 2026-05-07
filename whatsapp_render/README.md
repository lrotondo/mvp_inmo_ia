# WhatsApp MVP en Render (FastAPI + Meta Cloud API + Groq + CSV)

Servicio minimo para responder WhatsApp sin n8n ni Twilio:

- Meta WhatsApp Cloud API envia `POST` al webhook publico.
- Se valida verify token (`GET`) y firma `X-Hub-Signature-256` (`POST`).
- Se leen propiedades desde `data/propiedades_vivas.csv`.
- Se filtra con reglas simples (barrio / ambientes / precio maximo).
- Groq redacta la respuesta.
- Se responde al usuario por Graph API.

## Endpoints

- `GET /health` — healthcheck para Render
- `GET /meta/whatsapp` — verificacion del webhook (challenge)
- `POST /meta/whatsapp` — recepcion de mensajes de WhatsApp

## Variables de entorno (Render)

| Variable | Obligatoria | Descripcion |
|----------|-------------|-------------|
| `GROQ_API_KEY` | si | API key de Groq |
| `GROQ_MODEL` | no | Default: `llama-3.3-70b-versatile` |
| `META_VERIFY_TOKEN` | si | Token que configuras en Meta para verificar webhook |
| `META_ACCESS_TOKEN` | si | Token de acceso de WhatsApp Cloud API |
| `META_PHONE_NUMBER_ID` | si | Phone Number ID de tu numero de WhatsApp en Meta |
| `META_APP_SECRET` | si | App Secret para validar firma del webhook |
| `META_GRAPH_VERSION` | no | Default: `v22.0` |

## Configuracion en Meta

1. En tu app de Meta, habilitar **WhatsApp**.
2. En Webhooks, usar URL:
   - `https://TU_SERVICIO.onrender.com/meta/whatsapp`
3. En verify token, usar el mismo valor que `META_VERIFY_TOKEN`.
4. Suscribir evento `messages`.
5. Copiar `Access Token`, `Phone Number ID` y `App Secret` a Render.

## Desarrollo local

```powershell
cd "D:\Disco c original\Proyectos\script_scrapping\whatsapp_render"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
$env:GROQ_API_KEY="..."
$env:META_VERIFY_TOKEN="..."
$env:META_ACCESS_TOKEN="..."
$env:META_PHONE_NUMBER_ID="..."
$env:META_APP_SECRET="..."
uvicorn app.main:app --reload --port 8000
```

Probar:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/meta/whatsapp?hub.mode=subscribe&hub.verify_token=TU_TOKEN&hub.challenge=1234`

## Render (Web Service)

1. New **Web Service** -> conectar repo/carpeta `whatsapp_render`.
2. **Build command:** `pip install -r requirements.txt`
3. **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Cargar variables de entorno (tabla de arriba).
5. Deploy y copiar URL publica `https://....onrender.com`
6. Configurar webhook de Meta: `https://....onrender.com/meta/whatsapp`

### Actualizar propiedades

Reemplaza `data/propiedades_vivas.csv` en el repo y redeploy (MVP). Mas adelante: Postgres o S3.

### Costo (modo gratis)

- Render free puede dormir el servicio (cold start).
- Meta puede ofrecer tramo gratuito, pero fuera de ese tramo aplica cobro por conversacion segun pais/categoria.
- Para mantener costos bajos: limitar pruebas, controlar volumen y revisar consumo en Meta diariamente.

## Filtros soportados en el mensaje

- `tandil` / `rauch` en el texto filtra por barrio.
- `2 amb`, `3 amb`, etc.
- `hasta USD 90000`, `hasta 90000`, `menos de 100000`.
