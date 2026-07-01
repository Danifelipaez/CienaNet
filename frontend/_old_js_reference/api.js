/* api.js — capa de fetch hacia el backend FastAPI (sin build step, ES2017+). */

// ponytail: en dev, FastAPI y el frontend estático corren en el mismo origen
// (StaticFiles montado en app/main.py), así que un path relativo basta. Si se
// separan los deploys, cambiar esta constante por la URL pública del backend.
const API_BASE = "/api/v1";

const ADMIN_KEY_STORAGE = "cienrayas_admin_key";

function getStoredAdminKey() {
  return sessionStorage.getItem(ADMIN_KEY_STORAGE) || "";
}

function promptAdminKey() {
  const key = window.prompt(
    "Esta sección requiere la clave de administrador (X-Admin-Key) del backend."
  );
  if (key) sessionStorage.setItem(ADMIN_KEY_STORAGE, key);
  return key || "";
}

/**
 * Fetch JSON desde el backend. Si `admin` es true, agrega X-Admin-Key —
 * pide la clave por prompt() la primera vez y la reintenta una vez si el
 * backend responde 403 (clave inválida/expirada).
 */
async function apiFetch(path, { admin = false, method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (admin) {
    const key = getStoredAdminKey() || promptAdminKey();
    if (!key) throw new ApiError("Se requiere clave de administrador", 401);
    headers["X-Admin-Key"] = key;
  }

  const doFetch = () =>
    fetch(API_BASE + path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

  let res = await doFetch();
  if (res.status === 403 && admin) {
    sessionStorage.removeItem(ADMIN_KEY_STORAGE);
    const key = promptAdminKey();
    if (!key) throw new ApiError("Se requiere clave de administrador", 401);
    headers["X-Admin-Key"] = key;
    res = await doFetch();
  }

  if (!res.ok) {
    throw new ApiError(`${path} → HTTP ${res.status}`, res.status);
  }
  return res.json();
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

window.CienRayasAPI = {
  getPoints: () => apiFetch("/dashboard/points"),
  getSpecies: () => apiFetch("/dashboard/species"),
  getSedimentation: () => apiFetch("/dashboard/sedimentation"),
  getHistory: (days) => apiFetch(`/data/history?days=${days}`),
  getAlerts: () => apiFetch("/data/alerts"),
  askAI: (pregunta, contexto) =>
    apiFetch("/dashboard/ai/ask", { admin: true, method: "POST", body: { pregunta, contexto } }),
  getAIHistory: (limit) =>
    apiFetch(`/dashboard/ai/history${limit ? `?limit=${limit}` : ""}`, { admin: true }),
  getSystemStatus: () => apiFetch("/dashboard/system-status", { admin: true }),
  ApiError,
};
