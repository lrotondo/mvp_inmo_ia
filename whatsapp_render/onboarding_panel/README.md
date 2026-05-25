# Panel de onboarding (Embedded Signup)

Frontend separado para que cada inmobiliaria conecte su WhatsApp Business sin compartir contraseñas.

## Desarrollo local

```bash
cd onboarding_panel
npm install
cp .env.example .env
npm run dev
```

Abrí `http://localhost:5173`. En Meta Developers, agregá `localhost` a dominios permitidos solo para pruebas (producción requiere HTTPS en dominio real).

## Variables

| Variable | Descripción |
|----------|-------------|
| `VITE_API_BASE_URL` | URL del backend (`whatsapp_render` en Render o local) |
| `VITE_ONBOARDING_API_SECRET` | Mismo valor que `ONBOARDING_API_SECRET` en el backend |

## Build producción

```bash
npm run build
```

Servir `dist/` en HTTPS (Vercel, Netlify, S3+CloudFront, etc.). Agregar ese dominio en Meta → Facebook Login for Business → Allowed domains.

## Flujo

1. Abrir el panel con el ID de inmobiliaria en la URL, por ejemplo:  
   `https://panel.tudominio.com/?platform_tenant_id=1`
2. Botón abre Embedded Signup (popup Meta).
3. Listener `WA_EMBEDDED_SIGNUP` (si llega) + webhook `account_update` en el backend guardan la sesión.
4. Callback `FB.login` envía el `code` a `POST /api/onboarding/complete`. Si el popup no trajo WABA, el panel consulta `GET /api/onboarding/session/pending?platform_tenant_id=...`.
5. Paso 2: formulario de catálogo → `PATCH /api/onboarding/tenants/{id}` (`tenant_id` en la respuesta es el ID del bot en MySQL, no el de la URL).

Ver también [`docs/META_TECH_PROVIDER.md`](../docs/META_TECH_PROVIDER.md).
