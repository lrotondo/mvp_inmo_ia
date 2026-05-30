# WhatsApp MVP en Render (FastAPI + Meta Cloud API + DeepSeek + multicliente)

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
| `DEEPSEEK_API_KEY` | si (chat) | API key DeepSeek — respuestas al cliente (`deepseek-chat`) |
| `DEEPSEEK_MODEL` | no | Default: `deepseek-chat` |
| `LLM_CHAT_PROVIDER` | no | Default: `deepseek` |
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
| `MINIMAL_SYSTEM_PROMPT` | no | Reemplaza el system prompt corto de chat (captación / preguntas post-listado) |
| `SESSION_RESET_TIMEZONE` | no | Zona IANA para reinicio diario de conversación (default `America/Argentina/Buenos_Aires`) |
| `SESSION_IDLE_RESTART_HOURS` | no | Horas de inactividad para reinicio con saludo (default `24`) |
| `META_APP_ID` | onboarding | App ID de Meta (panel Embedded Signup) |
| `META_EMBEDDED_SIGNUP_CONFIG_ID` | onboarding | Configuration ID de Facebook Login for Business |
| `ONBOARDING_API_SECRET` | onboarding | Bearer para panel → `POST /api/onboarding/*` |
| `ONBOARDING_CORS_ORIGINS` | onboarding | Orígenes del panel separado, separados por coma (HTTPS) |
| `ONBOARDING_DEFAULT_CATALOG_SALE_PATH` | no | Catálogo venta por defecto tras conectar |
| `ONBOARDING_DEFAULT_CATALOG_RENT_PATH` | no | Catálogo alquiler por defecto tras conectar |
| `META_SYSTEM_USER_ACCESS_TOKEN` | onboarding | System User con `whatsapp_business_management` (Advanced); resuelve `phone_number_id` en webhook `PARTNER_APP_INSTALLED` vía `GET /{waba_id}/phone_numbers` |

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
2. Meta devuelve `code` (30 s) + `waba_id` (y a veces `phone_number_id` en `WA_EMBEDDED_SIGNUP`; en `PARTNER_APP_INSTALLED` el webhook suele traer solo `waba_info`).
3. Backend: si falta `phone_number_id`, lo obtiene con Graph `GET /{waba_id}/phone_numbers` (webhook con System User; `/complete` con el token del cliente). Luego intercambia código → token, suscribe webhooks, registra número, guarda fila en `tenants`.
4. Paso 2 en panel: URLs de catálogo venta/alquiler.

**Desarrollo / un solo cliente:** seguir usando [`seed_tenant`](app/seed_tenant.py) (`onboarding_status=manual`).

### Endpoints API (panel)

- `GET /api/onboarding/config` — público (`app_id`, `config_id`)
- `POST /api/onboarding/session-event` — Bearer `ONBOARDING_API_SECRET` (`phone_number_id` opcional)
- `GET /api/onboarding/session?waba_id=` — Bearer (sesión por WABA)
- `GET /api/onboarding/session/pending?platform_tenant_id=` — Bearer (sesión `assets_received` del webhook; usa si el popup no envió WABA)
- `POST /api/onboarding/complete` — Bearer (`waba_id` y `phone_number_id` opcionales; resuelve desde sesión pendiente + `code`)

Panel: abrir con `?platform_tenant_id=N` (ID inmobiliaria en Espacios360). `onboarding_sessions.tenant_id` es FK al `tenants.id` del **bot** (se llena al completar `/complete`); `platform_tenant_id` es el ID externo Espacios360.

Migración MySQL existente: [`migrations/mysql/002_platform_tenant_id.sql`](migrations/mysql/002_platform_tenant_id.sql).
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
- `system_prompt` — opcional; reemplaza el prompt mínimo por defecto (conviene dejarlo corto o vacío)
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

1. Crear **dos** planillas por inmobiliaria (venta y alquiler). Fila 1, encabezados (orden flexible; aliases aceptados). **No mezclar columnas entre ramas**: el bot formatea y filtra distinto según compra vs alquiler.

   **Venta** (`catalog_csv_path`):

   `ID | Titulo | Tipo | Direccion | Lugar | Zona | Precio | Disponible | Dormitorios | Ambientes | Caracteristicas | Foto_principal | url_link_fotos | url_link_video`

   | Columna | Obligatoria | Uso |
   |---------|-------------|-----|
   | `ID` | sí | Identificador único |
   | `Titulo`, `Tipo` | recomendadas | Nombre comercial y tipo (Departamento, Casa, …) |
   | `Direccion`, `Lugar`, `Zona` | sí | Ubicación en venta (no usar `Barrio` en venta; usar `Zona`) |
   | `Precio` | sí | **USD** (ej. `US$120.000`) |
   | `Disponible` | sí para publicar | Solo `si` / afirmativos entran al bot |
   | `Dormitorios`, `Ambientes`, `Caracteristicas` | recomendadas | Filtro y ficha |
   | `Foto_principal`, `url_link_fotos`, `url_link_video` | recomendadas | Media en WhatsApp (sin `Tour_360` en venta) |

   **Alquiler** (`catalog_rent_csv_path`):

   `ID | Titulo | Tipo | Direccion | Barrio | Precio | Disponible | Dormitorios | Ambientes | Caracteristicas | Foto_principal | Tour_360 | url_link_fotos | url_link_video`

   Opcionales en alquiler: `Expensas`, `Garantia_Propietaria`, `Seguro_Caucion`, `Admite_mascotas`, `Ajuste_IPC`.

   | Columna | Obligatoria | Uso |
   |---------|-------------|-----|
   | `Barrio` | sí (alquiler) | Zona/barrio del inmueble |
   | `Precio` | sí | **Alquiler mensual en ARS** |
   | `Expensas`, garantías, caución, mascotas, IPC | opcionales | Condiciones operativas del contrato |
   | `Tour_360` | opcional | Botón CTA en detalle de alquiler |
   | Resto | igual que venta | `Disponible`, media, etc. |

   **Compatibilidad:** `Link_Fotos` → `foto_principal`; aliases `lugar`, `zona`, `expensas`, `garantia`, `caucion`, `mascotas`, `ipc` en ingestión.

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

## Flujo conversacional (mínimo, backend-first)

Lógica en [`app/conversation_flow.py`](app/conversation_flow.py) (fachada: [`app/turn_handler.py`](app/turn_handler.py)) y [`app/prompts/templates.py`](app/prompts/templates.py).

| Fase | Comportamiento | LLM |
|------|----------------|-----|
| Triage (`nuevo`) | Mensaje fijo: comprar / alquilar / vender | No |
| Intake (`compra`/`alquiler`) | **Una sola pregunta** (tipo, zona, dormitorios, presupuesto en compra); la respuesta libre se parsea con LLM | Sí (extracción) |
| Listado | LLM elige hasta 3 IDs del catálogo + intro fija + `[LISTADO:ids]` + fotos | Sí (picker) |
| Más opciones | LLM elige otros IDs excluyendo los ya mostrados | Sí (picker) |
| Ninguna sirve (waitlist) | 1) Re-listado con IDs no mostrados; 2) Si no hay más en catálogo → consentimiento; 3) `si` → bundle requisitos; 4) LLM resume → `client_waitlist` → confirmación | Sí (paso 4) |
| Preguntas sobre opciones ya mostradas | Respuesta con datos compactos de las 3 opciones | DeepSeek (prompt mínimo) |
| Detalle (`opción N`, fotos, elección) | Intro fija + ficha/media | No |
| Visita / asesor | 1) Pregunta fija por días y horarios; 2) LLM resume conversación → lead + confirmación al cliente | Sí (paso 2) |
| Captación | Chat con prompt mínimo; cierre fijo al completar captura | DeepSeek opcional |

Estado por chat en `chat_sessions` (`last_listing` en `capture_data` para elegir opción 1/2/3). Alertas `ALERTA_CAPTACION_PROPIETARIO` las detecta el backend en `conversation_flow`; visita/compra/alquiler registran lead en fase `visit_confirm` con resumen LLM.

**Catálogo alquiler:** si `catalog_rent_csv_path` está vacío y **venta es CSV local**, el backend busca `{nombre_venta}_alquiler.csv` en la misma carpeta. Si **venta es Google Sheet**, configurá explícitamente el Sheet de alquiler en `catalog_rent_csv_path`.

Si el bot sigue mostrando propiedades de compra, el chat puede tener `flow_path=compra` guardado: el usuario debe decir "quiero alquilar" o borrar la fila en `chat_sessions` para ese `wa_id`.

## Catálogo y relevancia

- Solo propiedades con **`Disponible=si`** (u otro valor afirmativo) entran al catálogo del bot.
- Selección de listado: [`app/llm/listing_picker.py`](app/llm/listing_picker.py) (LLM + validación de IDs); fallback relajado en [`catalog_search.py`](app/catalog_search.py). Precio «consultar» no excluye por presupuesto.
- Preguntas post-listado: bloque compacto `Opción 1/2/3` solo en turnos de chat, no en el envío de fotos.
- Planillas Google: editar en Drive; el bot ve cambios tras el TTL (`CATALOG_CACHE_TTL_SECONDS`).

### Enlaces de fotos y video (WhatsApp)

- En **detalle**, el backend envía botones CTA con etiquetas cortas (`📸 Fotos`, `🎥 Video`, etc.); la URL no se muestra en el texto.
- En **listados** (hasta 3 opciones): el backend arma `[LISTADO:id1,id2,id3]` ([`app/listing_delivery.py`](app/listing_delivery.py)) envía:
  1. Texto de introducción
  2. Hasta 3 **mensajes de imagen** (`foto_principal` por ID) con caption (dirección, precio, ambientes, tour 360 si aplica)
  3. Pregunta de cierre
- `LISTING_IMAGE_DELIVERY=false` desactiva el envío multi-imagen y vuelve a un solo mensaje de texto.
- En **detalle / más info**: el backend envía primero **imagen** con `foto_principal` (miniatura de la propiedad) y luego texto con enlaces a galería/video. Si `url_link_fotos` es Instagram, no define el preview: va como enlace secundario «Ver galería en Instagram».
- En **listados** con `[LISTADO:ids]`, cada imagen lleva caption con características completas.
- Si el cliente **pide solo fotos o solo video**, el backend inyecta los links; el LLM no debe pegar URLs crudas.
- `foto_principal` debe ser URL **HTTPS pública** directa a JPG/PNG (Meta descarga la imagen). Perfiles de Instagram u otras páginas no sirven como imagen embebida.

## Estado de sesión (sin historial de chat)

- No se persiste historial de mensajes en `chat_messages` ni en memoria.
- El contexto vive en `chat_sessions.capture_data`: `search_profile`, `last_listing`, `user_flow_messages` (mensajes del cliente por rama), flags de bot (`bot_asked_visit_time`), `last_inbound_at`, `advisor_handoff_completed_at`.
- DeepSeek (chat mínimo) recibe: system corto + **solo el mensaje actual**.

### Reinicio automático de conversación

Al recibir un mensaje, el bot puede reiniciar el flujo desde triage (`flow_path=nuevo`) y limpiar `capture_data` (historial, perfil de búsqueda, listados, flags de visita, etc.):

| Condición | Ejemplo |
|-----------|---------|
| El mensaje llega en un **día calendario posterior** al último mensaje del cliente (zona `SESSION_RESET_TIMEZONE`, default `America/Argentina/Buenos_Aires`) | Escribió ayer a las 23:00 y vuelve hoy con «quiero alquilar» o cualquier texto |
| Saludo inicial **y** pasaron más de `SESSION_IDLE_RESTART_HOURS` (default **24**) desde el último mensaje | Mismo día calendario pero tras 24 h escribe «hola» |
| Saludo inicial **y** la última interacción cerró con handoff a asesor (visita confirmada, lista de espera registrada o captación completa) | Tras la confirmación de visita, escribe «hola» al rato |

El reinicio por día calendario aplica con **cualquier** mensaje (no solo saludos). No borra `client_leads` ni `client_waitlist`.

No aplica al reinicio por saludo+24h/handoff si el mensaje trae intención de flujo en el mismo texto (ej. «hola quiero alquilar» o «opción 2»): en ese caso sigue el flujo normal salvo que ya sea un día calendario posterior. Frases explícitas tipo «empecemos de nuevo» siguen usando `user_wants_fresh_start` (cambian `flow_path` sin la lógica de saludo+24h).

| Variable | Descripción |
|----------|-------------|
| `SESSION_RESET_TIMEZONE` | Zona IANA para el corte de día del reinicio automático (default `America/Argentina/Buenos_Aires`) |
| `SESSION_IDLE_RESTART_HOURS` | Horas de inactividad para reinicio con saludo (default `24`) |

## Leads (`client_leads`)

Requiere `DATABASE_URL`. El registro ocurre cuando el backend dispara una alerta (visita compra/alquiler o captación completa) en el mismo turno.

- Desactivado automáticamente si `APP_ENV` / `ENVIRONMENT` es `development`, `dev` o `local`.
- `LEAD_DETECTION_ENABLED=false` también lo apaga en producción.
- Campos: `wa_id`, `contact_name`, `property_ref`, `interest_summary`, `conversation_summary`, `conversation_at`
- `conversation_summary`: resumen en prosa (2–4 oraciones) generado por LLM en visita y waitlist; no es transcripción línea a línea del chat
- Mismo cliente + propiedad en 24 h → **actualiza** la fila (sin reenviar aviso).

### Aviso por WhatsApp al equipo

Si `LEAD_WHATSAPP_NOTIFY_TO` está definido (número en formato internacional **solo dígitos**, ej. `5492494123456`), al **crear** un lead con interés real el bot envía un mensaje de texto al asesor con:

- Nombre del contacto (perfil WhatsApp)
- `wa_id` del cliente
- Propiedad de referencia (si se detectó en el mensaje o listado)
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

Si el cliente indica que **ninguna opción le sirve** tras ver el listado, el bot primero intenta **mostrar otras propiedades del catálogo** (sin repetir IDs ya enviados). Cuando **no quedan más opciones**, pide consentimiento para tomar datos, luego el **bundle de requisitos** en un mensaje; con esa respuesta el LLM arma el resumen, registra en `client_waitlist` (requiere `DATABASE_URL`) y confirma la lista de espera. Aplica a compra y alquiler.

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
