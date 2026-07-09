# Despliegue

Este proyecto corre en dos destinos a la vez:

| Deployment | Rol | Recibe webhook de Meta | Corre el scheduler |
|---|---|---|---|
| Servidor universitario | Principal / producción | Sí | Sí (`RUN_SCHEDULER=true`) |
| Vercel | Respaldo / staging | No (a menos que se promueva) | No |

Ambos apuntan a la **misma base de datos Supabase** — no hay nada que
sincronizar entre despliegues, solo cuál de los dos está activo de cara al
usuario.

## Por qué `RUN_SCHEDULER`

`app/main.py` tiene un loop en background (`_hourly_refresh`) que refresca el
snapshot ambiental y evalúa/envía alertas de WhatsApp. Si dos deployments lo
corrieran a la vez sin coordinación, el resultado es trabajo duplicado contra
APIs externas y, en el peor caso, alertas de WhatsApp duplicadas a pescadores
reales (mitigado además por un advisory lock en `maybe_send_alert`, ver más
abajo — pero el gate evita el desperdicio de raíz). Por eso `RUN_SCHEDULER`
debe estar en `true` en un único deployment: hoy, el universitario. Vercel
sigue refrescando el snapshot vía su cron diario existente (`vercel.json`),
que nunca envía alertas.

## Variables de entorno por deployment

Todas las variables de `.env.example` son idénticas entre ambos deployments
(mismo Supabase, mismo número de WhatsApp, mismas claves). La única que
cambia es `RUN_SCHEDULER`:

| Deployment | RUN_SCHEDULER |
|---|---|
| Servidor universitario (producción) | `true` |
| Vercel (respaldo/staging) | `false` (default, no hace falta declararla) |
| Local dev | `false` (default; ponla en `true` solo para probar el loop horario en tu máquina) |

## Opción A: Docker (recomendado)

Requiere Docker + el plugin Compose (`docker compose version` debe funcionar
en el servidor).

Archivos relevantes: `Dockerfile` (backend), `frontend/Dockerfile`,
`docker-compose.yml`, `Caddyfile`.

```bash
git clone <repo> && cd cienanet-bot
cp .env.example .env                              # completar con credenciales reales
cp frontend/.env.local.example frontend/.env.local # completar ADMIN_API_KEY
# editar Caddyfile: reemplazar <dominio> por el dominio real
docker compose up -d --build
docker compose ps        # backend y frontend deben quedar "healthy"
```

Notas de diseño:
- Solo Caddy publica puertos al host (80/443) — backend y frontend quedan
  accesibles únicamente dentro de la red interna de Compose.
- `BACKEND_URL` dentro de `docker-compose.yml` apunta al DNS interno de
  Docker (`http://backend:8000`), no al dominio público — las llamadas del
  frontend al backend son siempre server-to-server (ver `frontend/lib/api.ts`,
  no hay fetches al backend desde el navegador).
- Caddy obtiene certificados TLS automáticamente de Let's Encrypt a partir
  del dominio declarado en el `Caddyfile` — no requiere certbot ni config
  manual, pero sí que el DNS ya apunte al servidor y el puerto 80 esté
  abierto (Let's Encrypt lo usa para el challenge HTTP-01).
- Las migraciones de Alembic NO corren automáticamente en el contenedor —
  siguen su flujo actual: correrlas a mano contra `POSTGRES_URL_NON_POOLING`
  desde cualquier máquina con acceso a Supabase, sin importar qué host sirve
  tráfico (hay una sola base de datos compartida).

### Redeploy

```bash
git pull && docker compose up -d --build
```

## Opción B: sin Docker (systemd + venv)

Si el servidor no tiene Docker disponible.

```bash
# Backend
python3.11 -m venv /opt/cienanet/venv
/opt/cienanet/venv/bin/pip install -r requirements.txt

# Frontend (Node 20+, requerido por Next.js 16)
cd /opt/cienanet/app/frontend && npm ci && npm run build
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

`/etc/systemd/system/cienanet-frontend.service`:

```ini
[Unit]
Description=CienaNet Bot - Next.js dashboard
After=network.target

[Service]
Type=simple
User=cienanet
WorkingDirectory=/opt/cienanet/app/frontend
EnvironmentFile=/opt/cienanet/app/frontend/.env.local
Environment=PORT=3000
ExecStart=/usr/bin/npm run start
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Ambos bindean solo a `127.0.0.1` — igual que en Docker, solo el reverse
proxy debe ser internet-facing. `output: "standalone"` en `next.config.ts` es
irrelevante en este camino (solo importa para la imagen Docker).

Reverse proxy: instalar Caddy nativo (paquete `caddy` en Debian/Ubuntu vía su
repo oficial) y usar el mismo `Caddyfile` del repo, cambiando el destino de
cada bloque a `reverse_proxy 127.0.0.1:8000` / `127.0.0.1:3000`.

```bash
sudo systemctl enable --now cienanet-backend cienanet-frontend caddy
```

### Redeploy

```bash
git pull
/opt/cienanet/venv/bin/pip install -r requirements.txt
cd frontend && npm ci && npm run build && cd ..
sudo systemctl restart cienanet-backend cienanet-frontend
```

## Checklist de provisioning

- [ ] Servidor: Docker + Compose plugin instalados — o, si no hay Docker,
      Python 3.11 + Node 20+ + Caddy nativo
- [ ] DNS: registro A `api.<dominio>` → IP pública del servidor
- [ ] DNS: registro A `dashboard.<dominio>` → misma IP pública
- [ ] Firewall: puertos 80 y 443 abiertos entrantes (el 80 es obligatorio
      para el challenge ACME de Let's Encrypt, no solo el 443 final)
- [ ] `.env` completado con credenciales reales — **no copiar el `.env`
      local tal cual**: históricamente ha tenido keys duplicadas
      (`ADMIN_API_KEY`, `SENSOR_API_KEY_SECRET`) donde python-dotenv toma la
      última ocurrencia sin avisar. Reconstruir línea por línea desde
      `.env.example`.
- [ ] `.env`: `RUN_SCHEDULER=true` — únicamente en este servidor
- [ ] `frontend/.env.local` completado con `ADMIN_API_KEY` (mismo valor que
      el del backend — es el mismo secreto en ambos lados, ver
      `frontend/lib/api.ts`). No definir `BACKEND_URL` ahí si se usa
      docker-compose (ya está fijado en `docker-compose.yml`).
- [ ] Meta Business Manager → WhatsApp → Configuration → Webhook URL:
      cambiar a `https://api.<dominio>/api/v1/webhook/whatsapp`, verify
      token = el mismo `WHATSAPP_VERIFY_TOKEN` del `.env`
- [ ] Firmware ESP32 ya desplegado en campo (si apunta a la URL de Vercel):
      actualizar a `https://api.<dominio>/api/v1/sensors/ingest` — vive
      fuera de este repo, pero es parte del checklist operativo de este
      cambio
- [ ] Confirmar que el firmware ESP32 valida el certificado TLS (no usa
      `setInsecure()`) — Caddy sirve TLS válido de Let's Encrypt
      automáticamente, pero el firmware debe validarlo, no ignorarlo (ver
      `docs/IOT_SENSORES.md`)

## Verificación del advisory lock de alertas

`app/services/alert_service.py::maybe_send_alert()` usa
`pg_advisory_xact_lock` para que dos llamadas concurrentes (dos workers, o
los dos deployments corriendo el scheduler por error) no dupliquen el envío
de una alerta. `tests/test_alert_service.py` prueba la lógica con mocks; para
confirmar la serialización real entre conexiones, usar
`scripts/verify_alert_lock.py` contra una Postgres descartable (instrucciones
en el propio script — nunca apuntarlo a Supabase real).
