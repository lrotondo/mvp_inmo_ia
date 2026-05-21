# WhatsApp MVP en Render (FastAPI + Meta Cloud API + Groq + multicliente)

Servicio para responder WhatsApp con un solo backend:

- Meta envia `POST` al webhook publico.
- Se valida verify token (`GET`) y firma `X-Hub-Signature-256` (`POST`).
- Se identifica la inmobiliaria por `metadata.phone_number_id` del JSON y se busca en la base (`tenants`).
- Cada tenant tiene su `access_token`, `phone_number_id`, prompt opcional y catálogo de **venta** + **alquiler** (CSV local o Google Sheets).
- DeepSeek redacta la respuesta con flujo **Espacios360** (3 caminos: compra, alquiler, captación); Graph API envía el mensaje.

## Endpoints

- `GET /health` — `status` y `db` (`on` si hay `DATABASE_URL`, si no `off`)
- `GET /meta/whatsapp` — verificacion del webhook (challenge)
- `POST /meta/whatsapp` — recepcion de mensajes de WhatsApp

## Variables de entorno (Render)

| Variable | Obligatoria | Descripcion |
|----------|-------------|-------------|
| `DATABASE_URL` | recomendada (multicliente) | **MySQL** (`mysql+pymysql://...?charset=utf8mb4`). Ver [`docs/MYSQL_SETUP.md`](docs/MYSQL_SETUP.md) |
| `GROQ_API_KEY` | si | API key de Groq |
| `GROQ_MODEL` | no | Default: `llama-3.3-70b-versatile` (respuestas al cliente) |
| `GROQ_LEAD_MODEL` | no | Default: `llama-3.1-8b-instant` (clasificador de leads) |
| `APP_ENV` | no | `development` / `dev` / `local` desactiva leads |
| `LEAD_DETECTION_ENABLED` | no | Default `true`; `false` apaga leads en producción |
| `LEAD_WHATSAPP_NOTIFY_TO` | no | Número del asesor (solo dígitos, ej. `5492494123456`) para avisar leads por WhatsApp |
| `LEAD_WHATSAPP_NOTIFY_ENABLED` | no | Default `true`; `false` desactiva solo el aviso al asesor |
| `WAITLIST_EXPORT_SECRET` | no | Secreto para `GET /admin/waitlist/export.csv` (header `X-Admin-Secret`) |
| `WAITLIST_EXPORT_DEFAULT_DAYS` | no | Default `7` — ventana del CSV de lista de espera |
| `META_VERIFY_TOKEN` | si | Token que configuras en Meta para verificar webhook |
| `META_APP_SECRET` | si | **App Secret** (Basica de la app), no el Client Secret de Login |
| `META_SKIP_SIGNATURE` | no | Si `1`, omite validacion de firma (solo depuracion) |
| `META_GRAPH_VERSION` | no | Default: `v22.0` |
| `META_ACCESS_TOKEN` | no | Fallback si no hay fila en `tenants` o falta `phone_number_id` |
| `META_PHONE_NUMBER_ID` | no | Debe coincidir con el `phone_number_id` del webhook para usar fallback |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | opcional | Solo planillas privadas; con enlace público (Lector) no hace falta |
| `GOOGLE_APPLICATION_CREDENTIALS` | alternativa | Ruta a archivo JSON (desarrollo local) |
| `CATALOG_CACHE_TTL_SECONDS` | no | Cache en memoria de planillas Google (default `300`) |
| `LISTING_IMAGE_DELIVERY` | no | Default `true`; `false` = listados en un solo mensaje de texto |
| `META_APP_ID` | onboarding | App ID de Meta (panel Embedded Signup) |
| `META_EMBEDDED_SIGNUP_CONFIG_ID` | onboarding | Configuration ID de Facebook Login for Business |
| `ONBOARDING_API_SECRET` | onboarding | Bearer para panel → `POST /api/onboarding/*` |
| `ONBOARDING_CORS_ORIGINS` | onboarding | Orígenes del panel separado, separados por coma (HTTPS) |
| `ONBOARDING_DEFAULT_CATALOG_SALE_PATH` | no | Catálogo venta por defecto tras conectar |
| `ONBOARDING_DEFAULT_CATALOG_RENT_PATH` | no | Catálogo alquiler por defecto tras conectar |

## Embedded Signup (Tech Provider)

Onboarding **self-service** para inmobiliarias: popup oficial de Meta, sin compartir contraseñas. Requiere alta como **Tech Provider** en Meta (checklist: [`docs/META_TECH_PROVIDER.md`](docs/META_TECH_PROVIDER.md)).

### Componentes

| Pieza | Ubicación |
|-------|-----------|
| API onboarding | `app/onboarding/` — `GET /api/onboarding/config`, `POST /complete`, `PATCH /tenants/{id}` |
| Panel frontend | [`onboarding_panel/`](onboarding_panel/) (Vite, desplegar en HTTPS) |
| Migración SQL MySQL | [`migrations/mysql/001_full_schema.sql`](migrations/mysql/001_full_schema.sql) |
| Webhook respaldo | `account_update` en `POST /meta/whatsapp` |

### Flujo

1. Inmobiliaria abre el panel → **Conectar con Facebook/WhatsApp** (`FB.login` + Embedded Signup v4).
2. Meta devuelve `code` (30 s) + `waba_id` / `phone_number_id` (evento `WA_EMBEDDED_SIGNUP`).
3. Backend: intercambia código → token, suscribe webhooks al WABA, registra número, guarda fila en `tenants`.
4. Paso 2 en panel: URLs de catálogo venta/alquiler.

**Desarrollo / un solo cliente:** seguir usando [`seed_tenant`](app/seed_tenant.py) (`onboarding_status=manual`).

### Endpoints API (panel)

- `GET /api/onboarding/config` — público (`app_id`, `config_id`)
- `POST /api/onboarding/session-event` — Bearer `ONBOARDING_API_SECRET`
- `POST /api/onboarding/complete` — Bearer
- `GET /api/onboarding/status/{tenant_id}` — Bearer
- `PATCH /api/onboarding/tenants/{tenant_id}` — Bearer (catálogo, nombre, prompt)

En Meta, suscribir también el webhook **`account_update`** (respaldo si el navegador cierra el popup antes de `complete`).

## Base de datos (MySQL)

Motor recomendado: **MySQL 8** externo (utf8mb4). Setup: [`docs/MYSQL_SETUP.md`](docs/MYSQL_SETUP.md).

Migrar solo **tenants** desde Postgres:

```powershell
$env:OLD_DATABASE_URL="postgresql://..."
$env:DATABASE_URL="mysql+pymysql://..."
pip install "psycopg[binary]"   # solo para leer Postgres una vez
python scripts/migrate_tenants_to_mysql.py
```

Esquema completo: `python -m app.sync_db` o `migrations/mysql/001_full_schema.sql`.

### Modelo `tenants`

Columnas principales:

- `phone_number_id` (unico) — coincide con `value.metadata.phone_number_id` del webhook
- `access_token` — token de WhatsApp Cloud API de ese cliente (Fase 1 en texto plano; rotar si se filtra)
- `name` — opcional
- `system_prompt` — opcional; si vacío se usa el prompt **Espacios360 Flow** del código
- `catalog_csv_path` — **Venta**: ruta CSV (`data/tenants/foo.csv`) o URL/ID de Google Sheet
- `catalog_rent_csv_path` — **Alquiler**: ruta CSV o URL/ID de Google Sheet (obligatorio si venta es Sheet)
- `waba_id`, `business_portfolio_id` — Embedded Signup
- `onboarding_status` — `manual` | `connected` | `failed` | `pending_token`
- `connected_at`, `onboarding_error`, `token_expires_at` — opcionales

Tabla `onboarding_sessions`: respaldo de assets del popup antes del intercambio de token.

En el primer deploy con `DATABASE_URL`, las tablas se crean con `create_all` al arrancar.

### Migración en Postgres existente (si ya tenías tablas)

Ejecutar también [`migrations/embedded_signup.sql`](migrations/embedded_signup.sql) para columnas de onboarding.

```sql
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS catalog_rent_csv_path VARCHAR(512);

ALTER TABLE client_leads ADD COLUMN IF NOT EXISTS lead_type VARCHAR(32) NOT NULL DEFAULT 'venta';
ALTER TABLE client_leads ADD COLUMN IF NOT EXISTS capture_summary TEXT;

CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    phone_number_id VARCHAR(64) NOT NULL,
    wa_id VARCHAR(32) NOT NULL,
    flow_path VARCHAR(32) NOT NULL DEFAULT 'nuevo',
    bot_paused BOOLEAN NOT NULL DEFAULT FALSE,
    capture_data TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_chat_session UNIQUE (phone_number_id, wa_id)
);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_phone_number_id ON chat_sessions (phone_number_id);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_wa_id ON chat_sessions (wa_id);
```

## Alta manual del primer cliente (desarrollo)

Usar cuando **aún no** tenés Tech Provider aprobado o para pruebas locales.

Desde la carpeta `whatsapp_render` con `DATABASE_URL` exportada:

```powershell
# CSV local
python -m app.seed_tenant --phone-number-id "TU_PHONE_NUMBER_ID" --access-token "TU_TOKEN" --name "Inmobiliaria Demo" --catalog-csv-path "data/tenants/inmobiliaria_cowork.csv" --catalog-rent-csv-path "data/tenants/inmobiliaria_cowork_alquiler.csv"

# Google Sheets (venta + alquiler en archivos distintos)
python -m app.seed_tenant --phone-number-id "TU_PHONE_NUMBER_ID" --access-token "TU_TOKEN" --name "Inmobiliaria Demo" --catalog-sheet-url "https://docs.google.com/spreadsheets/d/ID_VENTA/edit" --catalog-rent-sheet-url "https://docs.google.com/spreadsheets/d/ID_ALQUILER/edit"
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
4. Suscribir eventos `messages` y `account_update`
5. `META_APP_SECRET` desde la app (para firma webhook)
6. Dominios OAuth: panel en HTTPS (`onboarding_panel`) — ver [`docs/META_TECH_PROVIDER.md`](docs/META_TECH_PROVIDER.md)

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

## Render (Web Service + MySQL externo)

1. **No** hace falta Postgres en Render. Crear MySQL en tu host gratuito y pegar `DATABASE_URL` en el Web Service (ver [`docs/MYSQL_SETUP.md`](docs/MYSQL_SETUP.md)).
2. New **Web Service** → carpeta `whatsapp_render`.
3. Version de Python: usar **3.12.x** (no 3.14). El repo trae [`runtime.txt`](runtime.txt) con `3.12.8` y [`render.yaml`](render.yaml) define `PYTHON_VERSION=3.12.8`. Si el servicio no usa Blueprint, en el dashboard de Render agrega env var **`PYTHON_VERSION`** = `3.12.8` (o desactiva override a 3.14).
4. **Build command:** `pip install -r requirements.txt`
5. **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Cargar variables de entorno (tabla de arriba).
7. Deploy; configurar webhook en Meta.

### Catálogo con Google Sheets (recomendado en producción)

1. Crear **dos** planillas por inmobiliaria (venta y alquiler). Fila 1, encabezados (orden flexible; aliases aceptados):

   `ID | Direccion | Barrio | Precio | Ambientes | Caracteristicas | Disponible | foto_principal | Tour_360 | url_link_fotos | url_link_video`

   | Columna | Obligatoria | Uso |
   |---------|-------------|-----|
   | `ID` | sí | Identificador único de la fila |
   | `Direccion`, `Barrio`, `Precio`, `Ambientes`, `Caracteristicas` | sí | Datos mostrados al cliente |
   | `Disponible` | sí para publicar | Solo filas con `si`, `sí`, `1`, `true`, etc. aparecen en el bot. **Vacío u otro valor = oculta** |
   | `foto_principal` | recomendada | Foto del resumen en listados (`[📸 Ver fotos]`) |
   | `Tour_360` | opcional | Tour en listados (`[🔄 Tour 360°]`) si está cargado |
   | `url_link_fotos` | opcional | Carrusel / galería en detalle o si piden fotos (`[📸 Ver galería de fotos]`) |
   | `url_link_video` | opcional | Video externo cuando piden video (`[🎥 Ver video]`) |

   **Compatibilidad:** el encabezado antiguo `Link_Fotos` se normaliza a `foto_principal`.

   **Migración:** si agregás la columna `Disponible` a una planilla existente, marcá `si` en **cada** fila que quieras que el agente ofrezca. Sin `disponible=si` la propiedad no entra al catálogo del prompt ni a búsqueda por ID.

2. En cada planilla: **Compartir** → acceso general **Cualquiera con el enlace** → rol **Lector** (así el backend puede leer vía export CSV sin cuenta de servicio).

3. En `tenants`, guardar URL o ID del spreadsheet:

```sql
UPDATE tenants SET
  catalog_csv_path = 'https://docs.google.com/spreadsheets/d/SPREADSHEET_ID_VENTA/edit',
  catalog_rent_csv_path = 'https://docs.google.com/spreadsheets/d/SPREADSHEET_ID_ALQUILER/edit'
WHERE phone_number_id = 'TU_PHONE_NUMBER_ID';
```

El backend refresca la planilla cada `CATALOG_CACHE_TTL_SECONDS` (default 5 min) sin redeploy.

**Opcional:** si las planillas son privadas (solo usuarios invitados), configurá `GOOGLE_SERVICE_ACCOUNT_JSON` en Render y compartí cada planilla con el email de la cuenta de servicio; el backend usará la API como respaldo si el export público no alcanza.

### Actualizar propiedades por tenant (CSV local)

Subir CSV bajo `data/tenants/` y setear `catalog_csv_path`. Los cambios en disco se ven al modificar el archivo (cache por fecha de modificación). Para Google Sheets, editar la planilla alcanza; esperar el TTL de cache.

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

## Flujo Espacios360 (3 caminos)

1. **Triage** (`flow_path=nuevo`): saludo y pregunta si compra, alquila o vende su propiedad.
2. **Compra** (`compra`): catálogo de venta; perfil (zona, ambientes, presupuesto); sin preguntar financiación antes de listar; bandera `[ALERTA_VENTA]` si hay interés alto.
3. **Alquiler** (`alquiler`): al entrar a la rama pregunta perfil (ambientes/dormitorios, zona, casa o depto); luego hasta 3 opciones del catálogo; bandera `[ALERTA_ALQUILER]` tras visita + preferencia horaria.
4. **Captación** (`captacion`): recopila tipo, ubicación y m²/ambientes; cierre fijo y `[ALERTA_CAPTACION_PROPIETARIO]`; **pausa el bot** para ese chat (`bot_paused`).

Estado por chat en `chat_sessions`. Las banderas se eliminan del texto enviado al cliente. En **compra/alquiler**, el lead en `client_leads` y el WhatsApp al asesor se disparan **solo en el turno** en que el bot le dice al cliente que un asesor se comunicará para coordinar la visita (no al pedir preferencia horaria ni al listar opciones). Captación sigue registrando con `[ALERTA_CAPTACION_PROPIETARIO]`.

**Catálogo alquiler:** si `catalog_rent_csv_path` está vacío y **venta es CSV local**, el backend busca `{nombre_venta}_alquiler.csv` en la misma carpeta. Si **venta es Google Sheet**, configurá explícitamente el Sheet de alquiler en `catalog_rent_csv_path`.

Si el bot sigue mostrando propiedades de compra, el chat puede tener `flow_path=compra` guardado: el usuario debe decir "quiero alquilar" o borrar la fila en `chat_sessions` para ese `wa_id`.

## Catálogo y relevancia

- Solo propiedades con **`Disponible=si`** (u otro valor afirmativo) entran al catálogo del bot.
- El bloque del **system prompt** usa formato **compacto** por fila: ID, dirección, barrio, precio, ambientes, características y URLs de media (`foto_principal`, `url_link_fotos`, `url_link_video`, `Tour_360` cuando existan), **cacheado en memoria** (TTL para Sheets, mtime para CSV).
- Planillas Google: editar en Drive; el bot ve cambios tras el TTL (`CATALOG_CACHE_TTL_SECONDS`).
- El LLM elige cuáles mencionar según la consulta (entre las filas ya filtradas por disponibilidad).

### Enlaces de fotos y video (WhatsApp)

- El prompt ([`app/prompts/flow_master.py`](app/prompts/flow_master.py)) usa enlaces markdown con emoji en **detalle** y pedidos puntuales: `[📸 Ver galería de fotos]`, `[🎥 Ver video]`, `[🔄 Tour 360°]`.
- En **listados** (hasta 3 opciones): el LLM incluye el tag `[LISTADO:id1,id2,id3]` (IDs del catálogo). El backend ([`app/listing_delivery.py`](app/listing_delivery.py)) envía:
  1. Texto de introducción
  2. Hasta 3 **mensajes de imagen** (`foto_principal` por ID) con caption (dirección, precio, ambientes, tour 360 si aplica)
  3. Pregunta de cierre
- `LISTING_IMAGE_DELIVERY=false` desactiva el envío multi-imagen y vuelve a un solo mensaje de texto.
- En **detalle / más info**: el backend arma una ficha con *Características* del catálogo + galería + video (mismo mensaje). En **listados** con `[LISTADO:ids]`, cada imagen lleva caption con características completas.
- Si el cliente **pide solo fotos o solo video**, seguir las plantillas puntuales del prompt.
- `foto_principal` debe ser URL **HTTPS pública** directa a JPG/PNG (Meta descarga la imagen). Drive o páginas web no sirven como imagen embebida.

## Historial de conversación

- Se guardan los últimos **10 mensajes** (≈5 turnos user/assistant) por `phone_number_id` + `wa_id` en `chat_messages`, o en memoria si no hay `DATABASE_URL`.
- Groq recibe: `system` (reglas + catálogo) + historial + mensaje actual.
- Variable opcional: `CHAT_HISTORY_MAX_MESSAGES` (default `10`).

## Leads (`client_leads`)

Requiere `DATABASE_URL`. En **compra** y **alquiler**, el registro usa los datos ya recompilados (clasificador, referencia de propiedad, preferencia horaria en alquiler) **en el mismo turno** en que el mensaje saliente avisa contacto del asesor. No hay registro paralelo por clasificador en esas ramas. Captación y otros flujos pueden seguir usando el clasificador según corresponda.

- Desactivado automáticamente si `APP_ENV` / `ENVIRONMENT` es `development`, `dev` o `local`.
- `LEAD_DETECTION_ENABLED=false` también lo apaga en producción.
- Campos: `wa_id`, `contact_name`, `property_ref`, `interest_summary`, `conversation_summary`, `conversation_at`
- `conversation_summary`: resumen en prosa (2–4 oraciones) generado por LLM; no es transcripción línea a línea del chat
- Mismo cliente + propiedad en 24 h → **actualiza** la fila (sin reenviar aviso).

### Alquiler: visita y preferencia horaria

En la rama **alquiler**, la bandera `[ALERTA_ALQUILER]` se habilita cuando el cliente ya dio **preferencia horaria** (mañana/tarde/fin de semana) tras pedir visita, no en el primer “¿cuándo puedo verlos?”. La fila en `client_leads` se crea **en el turno siguiente** en que el bot confirma que un asesor lo contactará (mismo mensaje que ve el cliente). Ese registro incluye texto del tipo `Preferencia horaria: tarde` e interés en dos opciones si aplica.

### Aviso por WhatsApp al equipo

Si `LEAD_WHATSAPP_NOTIFY_TO` está definido (número en formato internacional **solo dígitos**, ej. `5492494123456`), al **crear** un lead con interés real el bot envía un mensaje de texto al asesor con:

- Nombre del contacto (perfil WhatsApp)
- `wa_id` del cliente
- Propiedad de referencia (si la detectó el clasificador)
- Resumen del interés y de la conversación

Usa el mismo `access_token` y `phone_number_id` del tenant (número de la inmobiliaria en Meta). El destinatario debe haber iniciado chat con ese número de WhatsApp Business al menos una vez (ventana de 24 h) o estar en la lista de permitidos de la app.

| Variable | Descripción |
|----------|-------------|
| `LEAD_WHATSAPP_NOTIFY_TO` | Número del asesor/equipo |
| `LEAD_WHATSAPP_NOTIFY_ENABLED` | Default `true`; `false` desactiva solo el aviso |

```sql
SELECT contact_name, wa_id, property_ref, interest_summary, conversation_at
FROM client_leads
WHERE phone_number_id = 'TU_PHONE_NUMBER_ID'
ORDER BY conversation_at DESC;
```

## Lista de espera (`client_waitlist`)

Flujo en **compra** y **alquiler** cuando el cliente vio opciones del catálogo y **ninguna le encaja**:

1. El bot resume necesidades (zona, presupuesto, ambientes, etc.) de la rama actual.
2. Confirma con el cliente y pregunta si quiere agregar algo.
3. Ofrece avisarlo cuando aparezca algo acorde.
4. Si acepta, el LLM incluye `[LISTA_ESPERA]` y se guarda en Postgres.

Tabla `client_waitlist`: `seek_type` (`venta` / `alquiler`), `requirements_json`, `requirements_summary`, `conversation_summary`, `status` (default `active`). Un registro activo por cliente y tipo se **actualiza** al re-registrar.

### Export CSV (informe semanal manual)

Requiere `WAITLIST_EXPORT_SECRET` y `DATABASE_URL`.

```bash
curl -H "X-Admin-Secret: TU_SECRETO" \
  "https://TU_SERVICIO/admin/waitlist/export.csv?phone_number_id=TU_PHONE_NUMBER_ID&days=7" \
  -o waitlist_semana.csv
```

| Parámetro | Descripción |
|-----------|-------------|
| `phone_number_id` | Obligatorio — tenant Meta |
| `days` | Últimos N días (default `WAITLIST_EXPORT_DEFAULT_DAYS`, 7) |
| `include_all=1` | Incluir estados distintos de `active` |

```sql
SELECT created_at, seek_type, contact_name, wa_id, requirements_summary, status
FROM client_waitlist
WHERE phone_number_id = 'TU_PHONE_NUMBER_ID'
ORDER BY created_at DESC;
```
