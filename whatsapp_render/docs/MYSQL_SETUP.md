# MySQL (hosting gratuito / externo)

Guía de infra para reemplazar Postgres en Render. La app usa SQLAlchemy + PyMySQL.

## Requisitos del servidor

- MySQL **8.0+**
- Base de datos con charset **`utf8mb4`** y collation **`utf8mb4_unicode_ci`**
- Usuario con permisos `CREATE`, `ALTER`, `INSERT`, `SELECT`, `UPDATE`, `DELETE` en esa base
- Host accesible desde Render (IP pública o allowlist `0.0.0.0/0` con contraseña fuerte)
- SSL: si el proveedor lo exige, agregar parámetros en la URL (ver proveedor)

## Crear base (ejemplo en consola MySQL)

```sql
CREATE DATABASE inmo_chat CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'inmo_app'@'%' IDENTIFIED BY 'TU_PASSWORD_FUERTE';
GRANT ALL PRIVILEGES ON inmo_chat.* TO 'inmo_app'@'%';
FLUSH PRIVILEGES;
```

## URL en Render (`DATABASE_URL`)

Formato:

```text
mysql+pymysql://inmo_app:TU_PASSWORD@HOST:3306/inmo_chat?charset=utf8mb4
```

Si la contraseña tiene `@`, `#`, `%`, etc., codificala (URL encode).

Opcional SSL (según host):

```text
mysql+pymysql://USER:PASS@HOST:3306/DB?charset=utf8mb4&ssl_ca=/etc/ssl/certs/ca.pem
```

También acepta `mysql://...` (el backend lo normaliza a `mysql+pymysql://`).

## Esquema

Opción A — SQL versionado:

```bash
mysql -h HOST -u USER -p inmo_chat < migrations/mysql/001_full_schema.sql
```

Opción B — desde el repo con `DATABASE_URL` apuntando a MySQL:

```bash
cd whatsapp_render
python -m app.sync_db
```

## Migrar solo `tenants` desde Postgres

```bash
set OLD_DATABASE_URL=postgresql://...
set DATABASE_URL=mysql+pymysql://...
python scripts/migrate_tenants_to_mysql.py
```

O desde CSV:

```bash
python scripts/migrate_tenants_to_mysql.py --csv tenants_export.csv
```

## Cutover Render

1. Crear esquema + migrar tenants.
2. Web Service → `DATABASE_URL` = URL MySQL → redeploy.
3. `GET /health` → `"db": "on"`.
4. Probar WhatsApp y panel onboarding.
5. Eliminar el add-on **PostgreSQL** en Render para dejar de pagar.

## Límites típicos (planes gratis)

- Conexiones simultáneas bajas: el backend usa pool reducido (`pool_size=5`).
- Latencia mayor que Postgres interno en Render: aceptable para MVP.
- Historial de chat/leads no se migra (solo `tenants`).
