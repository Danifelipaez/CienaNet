---
name: run-cienanet-bot
description: End-to-end verification for CienaNet Bot — launches the FastAPI backend and the Next.js dashboard together and proves a WhatsApp message flows through the real signed webhook into Supabase and shows up live in the dashboard. Use only for end-to-end/e2e checks — "does the whole system actually work", a full-stack smoke test, verifying WhatsApp-to-dashboard end to end. Not for single-file edits, unit tests, or generic "run the backend" asks.
---

CienaNet Bot is two independent local processes — a FastAPI backend
(`app/`, real Supabase Postgres, no local/sqlite fallback) and a Next.js
dashboard (`frontend/`) that calls it. "Running it end-to-end" means both
processes up, then proving data actually flows: webhook in -> DB write ->
dashboard read. Drive it via `.claude/launch.json` + the Claude Code Preview
tool (`preview_start`/`preview_snapshot`/`preview_console_logs`/...) — this
project's equivalent of `chromium-cli` — plus
`.claude/skills/run-cienanet-bot/simulate_whatsapp_message.py`, the HMAC-signing
driver for the webhook half. All paths below are relative to the repo root.

## Prerequisites

Nothing to install in this repo — `.venv/` (Python 3.11) and
`frontend/node_modules/` already exist with everything `requirements.txt` /
`frontend/package.json` ask for. Verified this session:

```bash
.venv/Scripts/python.exe -c "import fastapi, uvicorn, mangum, sqlalchemy, asyncpg, httpx; print('backend deps OK')"
```

From a genuinely clean clone, you'd instead run:

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
npm --prefix frontend install
```

## Setup

Both `.env` (repo root) and `frontend/.env.local` already exist locally with
real Supabase/Vercel-linked credentials (the root one looks like a
`vercel env pull` dump merged with a hand-maintained block — see Gotchas).
Nothing to configure if they're present. If either is missing, copy
`.env.example` / `frontend/.env.local.example` and fill in real values — the
backend has no offline/mock DB mode, so a real reachable `POSTGRES_PRISMA_URL`
is required even for local dev.

## Run (agent path)

**Check before you launch — see Gotcha #1.** A dev server for this project
may already be running (yours or a previous session's):

```bash
curl -sf http://localhost:8000/health && echo "backend already up"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000  # 307 = frontend already up
```

If either answers, reuse it as-is (skip straight to the verification steps
below) rather than launching a duplicate.

Otherwise, launch whichever isn't up yet via the configs in
`.claude/launch.json`:

- `preview_start({name: "backend"})` -> `.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000`
- `preview_start({name: "frontend"})` -> `npm --prefix frontend run dev` on port 3000 (auto-falls-back to a free port only when 3000 is held by something `preview_start` didn't launch itself)

Verify the backend is actually DB-connected, not just "up":

```bash
curl http://localhost:8000/api/v1/dashboard/points
```

A real response is a JSON list of named fishing points (`Boca del Pájaro`,
`Tasajera`, ...). `{"puntos": []}` or a 500 means the DB isn't reachable —
check `POSTGRES_PRISMA_URL` in `.env`.

Drive the frontend with the Preview tool against the `serverId` from
`preview_start`: `preview_snapshot` / `preview_screenshot` /
`preview_console_logs`. `/` redirects to `/dashboard/mapa` (public, no auth —
confirms the map and fishing points render for real). `preview_snapshot`
(accessibility tree) is the reliable check in this environment — see Gotcha
#5 about `preview_screenshot`.

**Prove the actual product flow — a signed inbound WhatsApp message all the
way to a database write:**

```bash
.venv/Scripts/python.exe .claude/skills/run-cienanet-bot/simulate_whatsapp_message.py
# -> 200 {"status":"ok"}
```

This builds a Meta-shaped webhook payload, signs it with `WHATSAPP_APP_SECRET`
from `.env` (same key `app/core/security.py:verify_hmac_meta` checks against),
and POSTs it to `/api/v1/webhook/whatsapp`. Optional args: `[text] [wa_id]
[backend_url]` — default text `"hola"` hits the deterministic greeting branch
(no AI provider call, no external WhatsApp send). Confirm the effect:

```bash
curl -H "X-Admin-Key: <settings.admin_api_key>" http://localhost:8000/api/v1/dashboard/system-status
```

`bot_metricas` -> the `msgs` entry (`"Mensajes enviados"`) should read one
higher than before the call. That number is computed from a real row in the
`conversations` table the webhook call just wrote — this is the end-to-end
proof, not a mock.

Stop when done: `preview_stop({serverId})` for each server you started.

## Run (human path)

```bash
.venv/Scripts/uvicorn app.main:app --reload --port 8000   # terminal 1
npm --prefix frontend run dev                              # terminal 2
```

Open `http://localhost:3000` (redirects to the map). Ctrl-C each terminal to
stop.

## Test

```bash
.venv/Scripts/python.exe -m pytest
```

Unit-level only (dashboard endpoints + AI service) — DB and `httpx` are
mocked, so this needs no running server and no real credentials. It does not
exercise the webhook/HMAC path; that's what the driver script above is for.

## Gotchas

- **Next.js 16 refuses a second dev server for the same project — even on a
  different port.** If one's already running anywhere for `frontend/`, a new
  `next dev` prints `Another next dev server is already running` with the
  PID to kill, and exits (confirmed: it does pass its own "Ready in Nms"
  check first, then self-terminates once it notices the sibling lock file
  under `frontend/.next/dev/`). Always curl port 3000 first and reuse it;
  don't rely on `autoPort` to save you here.
- **`.env` (repo root) has duplicate keys from repeated `vercel env pull` +
  manual edits, and the LAST occurrence in the file wins** (python-dotenv /
  pydantic-settings semantics) — not the first, and not "whichever looks more
  official." `ADMIN_API_KEY` and `SENSOR_API_KEY_SECRET` each currently
  appear twice with different values. Don't trust a value near the top of the
  file (from the Vercel-pulled block); grep for every occurrence of the key,
  or just ask the running process (curl an endpoint gated on it) to find out
  which one is actually effective.
- **`frontend/.env.local`'s `ADMIN_API_KEY` and the backend's resolved
  `settings.admin_api_key` are two independently-maintained copies of "the
  same" secret, and they can silently drift** (confirmed they currently do,
  in this repo, per the note above). When they mismatch, `/dashboard/sistema`
  and `/dashboard/ia` don't error loudly — `getSystemStatus()` /
  `getApiStatuses()` in the Next.js pages catch the fetch failure and render
  a `BackendError`/empty-pills fallback. A blank admin dashboard page means
  "check the two keys match," not "the backend is down." Confirm which key
  the backend actually expects with a direct curl (see Run steps above)
  before assuming anything is broken server-side.
- **WhatsApp send failures are swallowed on purpose, not a bug.** With
  `WHATSAPP_TOKEN` unset (true for local dev), `whatsapp_service.send_text_message`
  logs a warning and returns `None` instead of raising.
  `message_router.handle_incoming_text` still logs the bot's reply to
  `conversations` regardless of whether the real WhatsApp API call
  succeeded. So the `msgs` metric counts "replies the bot generated," not
  "messages Meta actually delivered" — expect it to increment in local dev
  even though no real WhatsApp message goes anywhere.
- **`preview_screenshot` timed out repeatedly against the frontend in this
  environment** (Turbopack HMR was mid-rebuild) even though the page was
  fully interactive and correct. `preview_snapshot` (accessibility tree)
  worked reliably every time and is the dependable way to confirm rendered
  content here — treat `preview_screenshot` as best-effort, not required for
  verification.
- **No offline DB mode.** `tests/conftest.py`'s dummy env values only satisfy
  `Settings()` for pytest, which mocks `get_db` entirely — they will NOT make
  a live `uvicorn` instance usable. A live run always needs a real reachable
  `POSTGRES_PRISMA_URL`.

## Troubleshooting

- **`Another next dev server is already running... Run taskkill /PID <pid> /F
  to stop it`** — a dev server for this project is already up somewhere.
  `curl -s -o /dev/null -w "%{http_code}" http://localhost:3000` first; if it
  answers, use it, don't relaunch.
- **`preview_start` error `Port 8000 is in use by ... (not a preview
  server)`** — same idea for the backend. Don't blindly set `autoPort` on the
  backend config: `frontend/.env.local`'s `BACKEND_URL` is hardcoded to
  `http://localhost:8000`, so an auto-ported backend on another port becomes
  invisible to the frontend.
- **`/api/v1/webhook/whatsapp` returns 403** — signature mismatch. Confirm
  `simulate_whatsapp_message.py` is reading the SAME `.env` the running
  backend loaded (repo root, not `frontend/.env.local`), and that
  `WHATSAPP_APP_SECRET` wasn't edited after the backend process started (it's
  read once at import time via `Settings()` — restart the backend after
  changing it).
- **Dashboard admin pages (Sistema, Pregunta IA) render an empty/error state
  with nothing in the backend terminal** — key mismatch, see the
  `ADMIN_API_KEY` Gotcha above, not a crash.
