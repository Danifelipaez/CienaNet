/**
 * Identidad blanda del usuario del dashboard. No hay login todavía: cada navegador
 * genera un UUID una sola vez y lo guarda en localStorage. Se envía como X-User-Id
 * para aislar el hilo y el historial de "Pregunta a la IA" por usuario (varios
 * miembros del equipo pueden consultar en paralelo sin mezclar conversaciones).
 *
 * Solo cliente — localStorage no existe en el servidor. El control de acceso real
 * sigue siendo la ADMIN_API_KEY del backend; esto es únicamente para scoping.
 */
const KEY = "cr_user_id";

export function getUserId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(KEY, id);
  }
  return id;
}
