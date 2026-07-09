/** Formateo de fecha/hora para gráficas — fijo a America/Bogota (no la zona horaria del navegador).
 *
 * `t` siempre es o un timestamp ISO completo (con "T", ej. sensores/clima horario) o una fecha pura
 * `YYYY-MM-DD` (sin hora, ej. lecturas diarias de satélite/IDEAM). Una fecha pura se parsea como
 * medianoche UTC y se formatea en UTC — mezclarla con America/Bogota (UTC-5) la retrocedería un día.
 */

export type ChartGranularity = "hour" | "day" | "week";

function isDateOnly(t: string): boolean {
  return !t.includes("T");
}

function toDateAndZone(t: string): { date: Date; timeZone: string } {
  if (isDateOnly(t)) {
    const [y, m, d] = t.split("-").map(Number);
    return { date: new Date(Date.UTC(y, m - 1, d)), timeZone: "UTC" };
  }
  return { date: new Date(t), timeZone: "America/Bogota" };
}

function fmt(date: Date, timeZone: string, opts: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat("es-CO", { ...opts, timeZone }).format(date);
}

/** "08 Jul" */
export function formatDate(t: string): string {
  const { date, timeZone } = toDateAndZone(t);
  const dia = fmt(date, timeZone, { day: "2-digit" });
  const mesRaw = fmt(date, timeZone, { month: "short" }).replace(".", "");
  return `${dia} ${mesRaw.charAt(0).toUpperCase()}${mesRaw.slice(1)}`;
}

function formatHourOnly(t: string): string {
  const { date, timeZone } = toDateAndZone(t);
  return fmt(date, timeZone, { hour: "2-digit", hour12: false });
}

/** Etiqueta del eje X: "08 Jul 14h" en vista hora, "08 Jul" en día/semana. */
export function formatAxisTick(t: string, granularity: ChartGranularity): string {
  if (granularity === "hour") return `${formatDate(t)} ${formatHourOnly(t)}h`;
  return formatDate(t);
}

/** Encabezado del tooltip — honesto sobre si el punto es una muestra real o un promedio agregado. */
export function formatTooltipHeader(t: string, granularity: ChartGranularity, aggregated = false): string {
  if (granularity === "hour") {
    const { date, timeZone } = toDateAndZone(t);
    const hora = fmt(date, timeZone, { hour: "2-digit", minute: "2-digit", hour12: false });
    return `${formatDate(t).toLowerCase()}, ${hora}`;
  }
  if (granularity === "week") {
    const { date } = toDateAndZone(t); // clave de bucket semanal = fecha pura, ya en medianoche UTC
    const end = new Date(date.getTime() + 6 * 86400000);
    const endLabel = formatDate(end.toISOString().slice(0, 10));
    return `Semana del ${formatDate(t)} al ${endLabel}`;
  }
  return aggregated ? `Promedio del ${formatDate(t)}` : formatDate(t);
}
