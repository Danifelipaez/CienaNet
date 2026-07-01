/**
 * Fase lunar aproximada (fórmula de mes sinódico) — no hay endpoint de backend
 * para esto, es puramente astronómico/computable en cliente.
 */

export type MoonPhaseGlyph = "new" | "first" | "full" | "last";

const SYNODIC_MONTH = 29.530588853;
const KNOWN_NEW_MOON_DAYS = Date.UTC(2000, 0, 6, 18, 14) / 86400000;

function moonAge(date: Date): number {
  const age = date.getTime() / 86400000 - KNOWN_NEW_MOON_DAYS;
  const mod = age % SYNODIC_MONTH;
  return mod < 0 ? mod + SYNODIC_MONTH : mod;
}

export function moonPhaseGlyph(date: Date): MoonPhaseGlyph {
  const frac = moonAge(date) / SYNODIC_MONTH;
  if (frac < 0.0625 || frac >= 0.9375) return "new";
  if (frac < 0.4375) return "first";
  if (frac < 0.5625) return "full";
  return "last";
}

export function moonPhaseLabel(glyph: MoonPhaseGlyph): string {
  return { new: "Nueva", first: "Creciente", full: "Llena", last: "Menguante" }[glyph];
}
