# Alta como Tech Provider en Meta (checklist)

Pasos de negocio **antes** de usar Embedded Signup en producción. El código del repo ya soporta el flujo técnico; Meta debe aprobar tu app como proveedor.

## 1. App en Meta Developers

1. Crear o usar la app existente de WhatsApp Cloud API.
2. Agregar producto **WhatsApp**.
3. Agregar **Facebook Login for Business** (no confundir con Login with Facebook para consumidores).

## 2. Facebook Login for Business

En **Facebook Login for Business > Settings > Client OAuth settings**:

- Client OAuth login: **Yes**
- Web OAuth login: **Yes**
- Enforce HTTPS: **Yes**
- Embedded Browser OAuth Login: **Yes**
- Strict Mode for redirect URIs: **Yes**
- Login with the JavaScript SDK: **Yes**
- **Allowed domains**: dominio del panel (`onboarding_panel`, ej. `https://panel.tudominio.com`)
- **Valid OAuth redirect URIs**: mismas URLs del panel

## 3. Embedded Signup v4

1. **Facebook Login for Business > Configurations** → Create from template **WhatsApp Embedded Signup Configuration With 60 Expiration Token** (o custom con variación WhatsApp Embedded Signup).
2. Copiar **Configuration ID** → variable `META_EMBEDDED_SIGNUP_CONFIG_ID` en Render.
3. Copiar **App ID** → `META_APP_ID`.
4. **App Secret** (Basic) → `META_APP_SECRET` (ya usado para firma webhook).

Documentación: [Embedded Signup Implementation](https://developers.facebook.com/docs/whatsapp/embedded-signup/implementation).

## 4. Programa Tech Provider

Seguir [Become a Tech Provider](https://developers.facebook.com/docs/whatsapp/solution-providers/get-started-for-tech-providers):

- Verificación del negocio de tu empresa.
- Vincular la app a tu plataforma (Partner Solution).
- Tiempos habituales: varias semanas.

Hasta estar aprobado, usar **`seed_tenant`** y tokens de prueba del dashboard de Developers.

## 5. Webhooks de la app

En la app de Meta:

| Campo | Valor |
|-------|--------|
| Callback URL | `https://TU_SERVICIO.onrender.com/meta/whatsapp` |
| Verify token | `META_VERIFY_TOKEN` |
| Suscripciones | `messages`, **`account_update`** |

`account_update` permite recuperar eventos si el navegador del cliente cierra el popup antes de que el panel llame a `/api/onboarding/complete`.

## 6. Variables en Render (backend)

```
META_APP_ID=
META_EMBEDDED_SIGNUP_CONFIG_ID=
META_APP_SECRET=          # ya existente
META_VERIFY_TOKEN=        # ya existente
ONBOARDING_API_SECRET=    # secreto panel → API (Bearer)
ONBOARDING_CORS_ORIGINS=https://panel.tudominio.com
```

## 7. Panel frontend

Desplegar `whatsapp_render/onboarding_panel` en HTTPS. Variables:

```
VITE_API_BASE_URL=https://TU_SERVICIO.onrender.com
VITE_ONBOARDING_API_SECRET=   # solo dev local; en prod usar login propio al panel
```

## 8. Facturación

Como **Tech Provider**, cada inmobiliaria paga conversaciones de WhatsApp en su **Meta Business Suite**. Tu plataforma no centraliza la facturación de Meta (distinto de Solution Partner con línea de crédito).

## 9. Prueba E2E

1. Inmobiliaria abre el panel → **Conectar con WhatsApp**.
2. Completa popup Meta (Business Manager, número, SMS).
3. Panel llama `POST /api/onboarding/complete`.
4. Enviar mensaje de prueba al número → webhook debe resolver tenant por `phone_number_id`.
5. Configurar catálogo en el paso 2 del panel (`PATCH /api/onboarding/tenants/{id}`).
