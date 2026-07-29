# Despliegue

Backend y frontend viven en repos separados y cada uno se despliega en un
único destino:

| Componente | Destino | Repo |
|---|---|---|
| Backend (FastAPI) | Servidor universitario | este repo |
| Frontend (dashboard Next.js) | Vercel | `CienaRed-Frontend` |

Ambos apuntan a la **misma base de datos Supabase**. El frontend habla con el
backend server-to-server vía `BACKEND_URL` (ver `lib/api.ts` en el repo del
frontend) — nunca hay fetches al backend desde el navegador.

## Deuda: doble despliegue del backend (Vercel sigue vivo)

**Confirmado 2026-07-29:** aunque la tabla de arriba dice que el backend
tiene un único destino, el proyecto Vercel de este mismo repo (`ciena-net`,
linkeado vía `.vercel/repo.json`, gitignored) nunca se desvinculó. Cada push
a `main` sigue disparando un build+deploy real, y `ciena-net.vercel.app`
sirve tráfico en producción en paralelo al servidor universitario — no es un
artefacto muerto, se verificó con `vercel logs` y pegándole a los endpoints
reales (`/api/v1/data/latest`, `/api/v1/dashboard/points`, etc. — todos 200).

`api/index.py` y `vercel.json` (el entry point Mangum) se borraron hace
tiempo del repo (ver STACK.md), pero Vercel sigue sirviendo el ASGI app de
todos modos vía detección propia — no depende de esos archivos como se
pensaba.

Dos riesgos concretos de dejarlo así:
1. **Preview deployments crashean con 500 en cada request.** Cualquier
   branch que no sea `main` (p.ej. `Developing`) hace deploy en el entorno
   "Preview" de Vercel, y las variables de entorno de Supabase/Postgres
   (`POSTGRES_PRISMA_URL`, `POSTGRES_URL_NON_POOLING`, `SUPABASE_URL`,
   `SUPABASE_SERVICE_ROLE_KEY`) solo están configuradas para el entorno
   "Production" en el dashboard de Vercel. `Settings()` revienta al importar
   `app/main.py` (`ValidationError`, 4 campos faltantes) y **todas** las
   requests devuelven 500, incluso `/favicon.ico`.
2. **Posible duplicación del scheduler.** Si el proyecto Vercel tiene
   `RUN_SCHEDULER=true` configurado (no verificado desde aquí — requiere
   revisar el dashboard de Vercel), habría dos procesos evaluando alertas y
   mandando WhatsApp a los mismos pescadores. El advisory lock de
   `maybe_send_alert` protege contra llamadas concurrentes, pero no contra
   dos deployments corriendo el loop horario de forma independiente.

**Acción recomendada:** decidir explícitamente entre (a) desvincular/borrar
el proyecto Vercel del backend ya que el servidor universitario es el
destino real, o (b) si se quiere mantener como respaldo caliente, completar
las variables de entorno también en el scope "Preview" y confirmar
`RUN_SCHEDULER=false` ahí. Ninguna de las dos requiere cambios de código.

## `RUN_SCHEDULER`

`app/main.py` tiene un loop en background (`_hourly_refresh`) que refresca el
snapshot ambiental y evalúa/envía alertas de WhatsApp. Como el backend corre
en un único proceso persistente, `RUN_SCHEDULER=true` en producción (servidor
universitario) y `false` por defecto en local dev (ponelo en `true` solo para
probar el loop horario en tu máquina). El advisory lock en
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
