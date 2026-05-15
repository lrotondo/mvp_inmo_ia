# WhatsApp MVP en Render (FastAPI + Meta Cloud API + Groq + multicliente)

Servicio para responder WhatsApp con un solo backend:

- Meta envia `POST` al webhook publico.
- Se valida verify token (`GET`) y firma `X-Hub-Signature-256` (`POST`).
- Se identifica la inmobiliaria por `metadata.phone_number_id` del JSON y se busca en Postgres (`tenants`).
- Cada tenant tiene su `access_token`, `phone_number_id`, prompt opcional y CSV de catalogo.
- Groq redacta la respuesta; Graph API envia el mensaje con el token de ese tenant.

## Endpoints

- `GET /health` — `status` y `db` (`on` si hay `DATABASE_URL`, si no `off`)
- `GET /meta/whatsapp` — verificacion del webhook (challenge)
- `POST /meta/whatsapp` — recepcion de mensajes de WhatsApp

## Variables de entorno (Render)

| Variable | Obligatoria | Descripcion |
|----------|-------------|-------------|
| `DATABASE_URL` | recomendada (multicliente) | Postgres (Render: crear Postgres y pegar URL interna) |
| `GROQ_API_KEY` | si | API key de Groq |
| `GROQ_MODEL` | no | Default: `llama-3.3-70b-versatile` |
| `META_VERIFY_TOKEN` | si | Token que configuras en Meta para verificar webhook |
| `META_APP_SECRET` | si | **App Secret** (Basica de la app), no el Client Secret de Login |
| `META_SKIP_SIGNATURE` | no | Si `1`, omite validacion de firma (solo depuracion) |
| `META_GRAPH_VERSION` | no | Default: `v22.0` |
| `META_ACCESS_TOKEN` | no | Fallback si no hay fila en `tenants` o falta `phone_number_id` |
| `META_PHONE_NUMBER_ID` | no | Debe coincidir con el `phone_number_id` del webhook para usar fallback |

## Modelo `tenants` (Postgres)

Columnas principales:

- `phone_number_id` (unico) — coincide con `value.metadata.phone_number_id` del webhook
- `access_token` — token de WhatsApp Cloud API de ese cliente (Fase 1 en texto plano; rotar si se filtra)
- `name` — opcional
- `system_prompt` — opcional; si vacio se usa el prompt por defecto del codigo
- `catalog_csv_path` — opcional; ruta relativa al proyecto, ej. `data/propiedades_vivas.csv` o `data/tenants/cliente.csv`

En el primer deploy con `DATABASE_URL`, las tablas se crean con `create_all` al arrancar.

## Alta manual del primer cliente

Desde la carpeta `whatsapp_render` con `DATABASE_URL` exportada:

```powershell
python -m app.seed_tenant --phone-number-id "TU_PHONE_NUMBER_ID" --access-token "TU_TOKEN" --name "Inmobiliaria Demo" --catalog-csv-path "data/propiedades_vivas.csv"
```

Equivalente en SQL (ajusta valores):

```sql
INSERT INTO tenants (phone_number_id, access_token, name, system_prompt, catalog_csv_path)
VALUES (
  'TU_PHONE_NUMBER_ID',
  'TU_ACCESS_TOKEN',
  'Inmobiliaria Demo',
  NULL,
  'data/propiedades_vivas.csv'
);
```

## Comportamiento si no hay tenant

Si llega un `phone_number_id` sin fila en `tenants`, se intenta el **fallback** `META_ACCESS_TOKEN` + `META_PHONE_NUMBER_ID` solo cuando el id del webhook coincide (o viene vacio y el fallback esta configurado).

Si no hay match, se responde `200` con `{"ok": true}` y se registra un warning en logs (Meta no debe recibir 5xx por mensajes desconocidos).

## Configuracion en Meta

1. En tu app de Meta, habilitar **WhatsApp**.
2. Webhook URL: `https://TU_SERVICIO.onrender.com/meta/whatsapp`
3. Verify token = `META_VERIFY_TOKEN`
4. Suscribir evento `messages`
5. `META_APP_SECRET` desde la app (para firma webhook)

## Desarrollo local

```powershell
cd "D:\Disco c original\Proyectos\script_scrapping\whatsapp_render"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
$env:DATABASE_URL="postgresql://..."
$env:GROQ_API_KEY="..."
$env:META_VERIFY_TOKEN="..."
$env:META_APP_SECRET="..."
uvicorn app.main:app --reload --port 8000
```

Probar:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/meta/whatsapp?hub.mode=subscribe&hub.verify_token=TU_TOKEN&hub.challenge=1234`

## Render (Web Service + Postgres)

1. Crear **PostgreSQL** en Render y copiar **Internal Database URL** a `DATABASE_URL` del Web Service.
2. New **Web Service** → carpeta `whatsapp_render`.
3. Version de Python: usar **3.12.x** (no 3.14). El repo trae [`runtime.txt`](runtime.txt) con `3.12.8` y [`render.yaml`](render.yaml) define `PYTHON_VERSION=3.12.8`. Si el servicio no usa Blueprint, en el dashboard de Render agrega env var **`PYTHON_VERSION`** = `3.12.8` (o desactiva override a 3.14).
4. **Build command:** `pip install -r requirements.txt`
5. **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Cargar variables de entorno (tabla de arriba).
7. Deploy; configurar webhook en Meta.

### Actualizar propiedades por tenant

Subir CSV bajo `data/` o `data/tenants/` y setear `catalog_csv_path` en la fila del tenant. Tras cambiar un archivo, reiniciar el servicio si necesitas limpiar cache en memoria (`lru_cache` por ruta).

### Costo y control

- Revisar conversaciones y limites en Meta por WABA.
- `META_ACCESS_TOKEN` en DB es sensible: rotacion y acceso minimo.
- Render free puede dormir el servicio (cold start).

### Error `Firma Meta invalida` (403)

La firma se calcula con el **cuerpo crudo** del `POST` y el **secreto de la aplicacion** (no otro valor).

1. En Meta Developers: **Tu app** → **Configuracion** → **Basica** → **Secreto de la aplicacion** (App Secret).  
   No uses el **Secreto del cliente** de *Inicio de sesion con Facebook* / OAuth; es otro valor.
2. En Render, variable **`META_APP_SECRET`**: pegar el secreto **sin comillas**; si al copiar quedaron comillas o un salto de linea al final, borralos y redeploy.
3. Revisa logs: si `cabecera_X-Hub-Signature-256_longitud=0`, Meta no esta enviando la cabecera (proxy o ruta incorrecta).
4. Solo para aislar el problema (nunca en produccion): `META_SKIP_SIGNATURE=1` confirma que el resto del flujo funciona; luego volve a validar firma con el App Secret correcto.

## Catálogo y relevancia

- **Todas** las propiedades del CSV del tenant se envían en el **system prompt**; el LLM elige cuáles mencionar según la consulta (sin pre-filtro en Python).

## Historial de conversación

- Se guardan los últimos **10 mensajes** (≈5 turnos user/assistant) por `phone_number_id` + `wa_id` en Postgres (`chat_messages`), o en memoria si no hay `DATABASE_URL`.
- Groq recibe: `system` (reglas + catálogo) + historial + mensaje actual.
- Variable opcional: `CHAT_HISTORY_MAX_MESSAGES` (default `10`).

## Leads (`client_leads`)

Requiere `DATABASE_URL`. Tras cada respuesta, Groq clasifica si hay **interés real**; si sí, se guarda en `client_leads`:

- `wa_id`, `contact_name`, `property_ref`, `interest_summary`, `conversation_summary`, `conversation_at`
- Si el mismo cliente y propiedad repiten en 24 h, se **actualiza** la fila.

Variable: `LEAD_DETECTION_ENABLED` (default `true`; `0` / `false` para desactivar).

```sql
SELECT contact_name, wa_id, property_ref, interest_summary, conversation_at
FROM client_leads
WHERE phone_number_id = 'TU_PHONE_NUMBER_ID'
ORDER BY conversation_at DESC;
```
