# Despliegue

Backend y frontend viven en repos separados. El backend se despliega en dos
destinos con roles distintos (ver "Vercel" más abajo):

| Componente | Destino | Repo |
|---|---|---|
| Backend (FastAPI) — webhook, sensores, scheduler | Servidor universitario | este repo |
| Backend (FastAPI) — API de lectura + cron diario | Vercel (proyecto `ciena-net`) | este repo |
| Frontend (dashboard Next.js) | Vercel | `CienaRed-Frontend` |

Ambos apuntan a la **misma base de datos Supabase**. El frontend habla con el
backend server-to-server vía `BACKEND_URL` (ver `lib/api.ts` en el repo del
frontend) — nunca hay fetches al backend desde el navegador.

## Vercel (segundo destino del backend)

La config vive en el repo: `vercel.json`, `api/index.py`, `api/requirements.txt`
y `.vercelignore`. Antes existía solo el proyecto Vercel `ciena-net` linkeado a
este repo (`.vercel/repo.json`, gitignored), deployando en cada push a `main` sin
ningún archivo versionado — Vercel detectaba la app ASGI por su cuenta. Eso
servía tráfico real, pero dejaba el despliegue sin cron, sin timeout declarado y
sin control de qué se sube.

### Qué sirve cada destino

| | Servidor universitario | Vercel |
|---|---|---|
| API de lectura (`/data/*`, `/dashboard/*`, `/health`) | sí | sí |
| Webhook de WhatsApp (Meta apunta a un solo host) | sí | no |
| Ingesta de sensores ESP32 (el firmware apunta a un solo host) | sí | no |
| Scheduler horario + envío de alertas (`RUN_SCHEDULER`) | sí | **no, nunca** |
| Refresco diario del snapshot (cron de `vercel.json`) | no | sí |

`RUN_SCHEDULER` **debe quedar en `false`** en el proyecto Vercel. No es un
detalle de configuración: `_hourly_refresh` llama a `maybe_send_alert`, que manda
WhatsApp a *todos* los pescadores suscritos ante cualquier cambio de color del
semáforo. Dos deployments corriendo el loop = alertas duplicadas a personas
reales. El advisory lock de `maybe_send_alert` serializa llamadas concurrentes,
pero no impide que dos deployments evalúen el semáforo por turnos y manden dos
veces. (En serverless el loop igual no sobreviviría: la función se congela entre
requests, así que el `asyncio.sleep(3600)` nunca termina de dormir.)

### Archivos

- **`api/index.py`** — re-exporta `app.main:app`. El runtime de Python de Vercel
  sirve ASGI de forma nativa, así que **no** lleva Mangum: el entry point viejo
  (borrado en 90942c0) sí lo usaba, pero Mangum traduce ASGI al protocolo handler
  de AWS Lambda, que no es el que Vercel espera.
- **`vercel.json`** — tres cosas:
  - `rewrites`: todo el tráfico entra por la función `/api/index`; el ruteo real
    (incluido el prefijo `/api/v1`) lo hace FastAPI adentro.
  - `crons`: `GET /api/v1/data/latest` una vez al día (00:00 UTC = 19:00 hora
    Colombia). Ese endpoint refresca y persiste el snapshot ambiental y **nunca**
    manda alertas — es el cron diario que ya asumían los comentarios de
    `app/services/dashboard_service.py` y `.env.example`. El plan Hobby permite
    crons diarios, no más frecuentes.
  - `functions.maxDuration = 60`: el default de 10 s no alcanza, `/data/latest`
    llama a ERDDAP, Open-Meteo, IDEAM y NOAA en el mismo request. 60 s es el
    máximo del plan Hobby.
- **`api/requirements.txt`** — subconjunto de runtime de `requirements.txt`. El
  runtime de Python lo prefiere por estar junto al entry point. Deja afuera
  pytest, ruff, uvicorn, alembic, psycopg2-binary y el SDK de supabase (que no se
  importa en ningún punto de `app/`).
- **`.vercelignore`** — tests, docs, firmware, alembic, scripts y config del
  servidor fuera del bundle.

### Límite de tamaño de la función (250 MB)

Medido con los floors actuales: el set de runtime instala **~215 MB**, de los
cuales ~150 MB son pandas + numpy, que entran solo porque `erddapy` los arrastra.
Margen real: ~35 MB. Consecuencias prácticas:

- Instalar el `requirements.txt` completo (ruff ~30 MB, pytest, supabase,
  alembic) pasa el límite — de ahí que exista `api/requirements.txt`.
- `erddapy.to_xarray()`, que usa `_fetch_sst`, necesita `xarray` + `netCDF4`, y
  **hoy no están en ningún requirements** — o sea que la SST cae al baseline en
  los dos deployments (`get_sst` atrapa la excepción y loggea un warning). Si se
  corrige esa dependencia faltante, hay que volver a medir: xarray + netCDF4 son
  ~40 MB y el margen no da.
- Salida si algún día no entra: sacar `erddapy` de `api/requirements.txt`. La app
  importa igual (el import es tardío, dentro de `_fetch_sst`) y la estrategia
  DB-first de `get_latest_snapshot` lee el satélite que ya persistió el servidor
  universitario.

### Pool de conexiones

`app/core/database.py` elige el pool según la plataforma: con la env var `VERCEL`
presente (la define la propia plataforma) usa `NullPool` — el contenedor se
congela entre invocaciones, así que un pool en proceso guardaría conexiones ya
muertas y cada instancia concurrente multiplicaría su propio pool contra el
límite de Supabase. El pooler (pgBouncer, puerto 6543) es el que hace el pooling
real. En el servidor universitario no cambia nada: pool por defecto con
`pool_pre_ping`.

### Pasos en el dashboard de Vercel (no se pueden versionar)

1. **Settings → Environment Variables**, en los scopes **Production y Preview**:
   `POSTGRES_PRISMA_URL`, `POSTGRES_URL_NON_POOLING`, `SUPABASE_URL`,
   `SUPABASE_SERVICE_ROLE_KEY`, `SENSOR_API_KEY_SECRET`, `ADMIN_API_KEY` (mismo
   valor que el servidor universitario), `ENVIRONMENT=production`,
   `RUN_SCHEDULER=false`. Opcional `AI_API_KEY` si se quiere `/dashboard/ai/ask`
   desde ahí.
   - **Preview importa:** hoy las variables están solo en Production, y por eso
     cualquier deploy de una rama que no sea `main` devuelve 500 en *todas* las
     requests — `Settings()` revienta al importar `app/main.py`
     (`ValidationError`, 4 campos faltantes) y ni `/favicon.ico` responde.
   - Con `ENVIRONMENT != development`, dejar `ADMIN_API_KEY` en `change-me` hace
     fallar el arranque a propósito (fail-fast, ver `config.py`).
2. **Settings → Functions → Region**: la misma región del proyecto Supabase; cada
   request cruzando de región le suma latencia a cada query.
3. Deploy: push a `main` (auto-deploy) o `vercel --prod` desde el repo linkeado.
4. Verificar: `GET /health`, `GET /api/v1/data/latest`, y que el cron diario
   aparezca en **Settings → Cron Jobs**.
5. Confirmar que `BACKEND_URL` del frontend sigue apuntando a donde se quiere
   (hoy: el servidor universitario). Vercel no se auto-promueve a backend del
   dashboard.

### Lo que sigue sin decidir

Dos hosts sirviendo la misma API contra la misma DB sigue siendo una decisión de
producto pendiente. Mientras siga así: cada cambio de endpoint hay que deployarlo
en los dos, y conviene tener presente que el host que conocen Meta (webhook) y el
firmware ESP32 (ingesta) es el servidor universitario, no Vercel.

## `RUN_SCHEDULER`

`app/main.py` tiene un loop en background (`_hourly_refresh`) que refresca el
snapshot ambiental y evalúa/envía alertas de WhatsApp. Necesita un proceso
persistente, así que `RUN_SCHEDULER=true` va solo en el servidor universitario;
en Vercel y en local dev queda en `false` (ponelo en `true` en tu máquina solo
para probar el loop horario). El advisory lock en
`maybe_send_alert` (ver más abajo) protege igual contra duplicados si dos
instancias locales llegaran a correr a la vez.

**Riesgo operativo al habilitar `RUN_SCHEDULER` por primera vez tras un
deploy con cambios de semáforo/clima:** dos cambios recientes hacen más
probable un cambio de color en el primer ciclo, y `maybe_send_alert` manda
WhatsApp a *todos* los suscritos ante cualquier cambio de color:
1. Las ráfagas de Open-Meteo ahora son reales (no un estimado `viento × 1.4`)
   — condiciones antes ocultas (viento moderado + ráfaga fuerte) ahora
   disparan rojo correctamente.
2. Sin datos de viento *ni* lluvia, el semáforo ya no asume verde por
   default — pasa a amarillo explícito ("no puedo confirmar si es seguro
   salir"). Con la red de sensores en fase 1, esto puede ser el caso normal,
   no una excepción.

Recomendado: en el primer arranque tras un deploy así, dejar
`RUN_SCHEDULER=false`, correr `_hourly_refresh` una vez a mano (o inspeccionar
`GET /data/latest`) para confirmar el color/razón antes de habilitar el loop
automático que sí envía alertas.

## Opción A: Docker (recomendado)

Requiere Docker + el plugin Compose (`docker compose version` debe funcionar
en el servidor).

Archivos relevantes: `Dockerfile`, `docker-compose.yml`, `Caddyfile`.

```bash
git clone <repo> && cd cienanet-bot
cp .env.example .env    # completar con credenciales reales
# editar Caddyfile: reemplazar <dominio> por el dominio real
docker compose up -d --build
docker compose ps       # backend debe quedar "healthy"
```

Notas de diseño:
- Solo Caddy publica puertos al host (80/443) — el backend queda accesible
  únicamente dentro de la red interna de Compose.
- Caddy obtiene certificados TLS automáticamente de Let's Encrypt a partir
  del dominio declarado en el `Caddyfile` — no requiere certbot ni config
  manual, pero sí que el DNS ya apunte al servidor y el puerto 80 esté
  abierto (Let's Encrypt lo usa para el challenge HTTP-01).
- Las migraciones de Alembic NO corren automáticamente en el contenedor —
  siguen su flujo actual: correrlas a mano contra `POSTGRES_URL_NON_POOLING`
  desde cualquier máquina con acceso a Supabase.

### Redeploy

```bash
git pull && docker compose up -d --build
```

## Opción B: sin Docker (systemd + venv)

Si el servidor no tiene Docker disponible.

```bash
python3.11 -m venv /opt/cienanet/venv
/opt/cienanet/venv/bin/pip install -r requirements.txt
```

`/etc/systemd/system/cienanet-backend.service`:

```ini
[Unit]
Description=CienaNet Bot - FastAPI backend
After=network.target

[Service]
Type=simple
User=cienanet
WorkingDirectory=/opt/cienanet/app
EnvironmentFile=/opt/cienanet/app/.env
ExecStart=/opt/cienanet/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Bindea solo a `127.0.0.1` — igual que en Docker, solo el reverse proxy debe
ser internet-facing.

Reverse proxy: instalar Caddy nativo (paquete `caddy` en Debian/Ubuntu vía su
repo oficial) y usar el mismo `Caddyfile` del repo, cambiando el destino del
bloque a `reverse_proxy 127.0.0.1:8000`.

```bash
sudo systemctl enable --now cienanet-backend caddy
```

### Redeploy

```bash
git pull
/opt/cienanet/venv/bin/pip install -r requirements.txt
sudo systemctl restart cienanet-backend
```

## Checklist de provisioning

- [ ] Servidor: Docker + Compose plugin instalados — o, si no hay Docker,
      Python 3.11 + Caddy nativo
- [ ] DNS: registro A `api.<dominio>` → IP pública del servidor
- [ ] Firewall: puertos 80 y 443 abiertos entrantes (el 80 es obligatorio
      para el challenge ACME de Let's Encrypt, no solo el 443 final)
- [ ] `.env` completado con credenciales reales — **no copiar el `.env`
      local tal cual**: históricamente ha tenido keys duplicadas
      (`ADMIN_API_KEY`, `SENSOR_API_KEY_SECRET`) donde python-dotenv toma la
      última ocurrencia sin avisar. Reconstruir línea por línea desde
      `.env.example`.
- [ ] `.env`: `RUN_SCHEDULER=true`
- [ ] Meta Business Manager → WhatsApp → Configuration → Webhook URL:
      `https://api.<dominio>/api/v1/webhook/whatsapp`, verify token = el
      mismo `WHATSAPP_VERIFY_TOKEN` del `.env`
- [ ] Firmware ESP32: apunta a `https://api.<dominio>/api/v1/sensors/ingest`
      — vive fuera de este repo, pero es parte del checklist operativo
- [ ] Confirmar que el firmware ESP32 valida el certificado TLS (no usa
      `setInsecure()`) — Caddy sirve TLS válido de Let's Encrypt
      automáticamente, pero el firmware debe validarlo, no ignorarlo (ver
      `docs/IOT_SENSORES.md`)
- [ ] En el proyecto Vercel del frontend (repo `CienaRed-Frontend`):
      `BACKEND_URL=https://api.<dominio>` y `ADMIN_API_KEY` (mismo valor que
      el del backend — ver `lib/api.ts` en ese repo)

## Verificación del advisory lock de alertas

`app/services/alert_service.py::maybe_send_alert()` usa
`pg_advisory_xact_lock` para que dos llamadas concurrentes no dupliquen el
envío de una alerta. `tests/test_alert_service.py` prueba la lógica con
mocks; para confirmar la serialización real entre conexiones, usar
`scripts/verify_alert_lock.py` contra una Postgres descartable (instrucciones
en el propio script — nunca apuntarlo a Supabase real).
