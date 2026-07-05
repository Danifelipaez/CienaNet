"use client";

import { useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/ui/icon";
import { Card, CardGrid } from "@/components/ui/card";
import { MonoChip, Pill, StatusDot } from "@/components/ui/primitives";
import { LineChart, ScatterChart, MoonGlyph } from "@/components/ui/charts";
import type { HistoryResponse } from "@/lib/api";
import {
  weatherToVientoSeries,
  weatherToVientoDiario,
  weatherToVientoSemanal,
  satelliteToTempSeries,
  satelliteToChloroSeries,
  catchToSeries,
  toCorrelacion,
  semaphoreToEventos,
} from "./adapters";
import { moonPhaseGlyph, moonPhaseLabel } from "@/lib/moon";

const RANGOS = ["7", "30", "90"] as const;
const VISTAS_VIENTO = ["hora", "dia", "7dias"] as const;
const VISTA_VIENTO_LABEL: Record<(typeof VISTAS_VIENTO)[number], string> = {
  hora: "Hora",
  dia: "Día",
  "7dias": "7 días",
};

/** Nodos en los puntos donde la fase realmente cambia (evita repetir la misma fase en nodos consecutivos). */
function fasesLuna(days: number) {
  const now = new Date();
  const start = new Date(now);
  start.setDate(start.getDate() - (days - 1));
  const nodos: { i: number; glyph: ReturnType<typeof moonPhaseGlyph> }[] = [];
  for (let i = 0; i < days; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    const glyph = moonPhaseGlyph(d);
    if (!nodos.length || nodos[nodos.length - 1].glyph !== glyph) nodos.push({ i, glyph });
  }
  return nodos.map((n, idx) => ({
    i: n.i,
    glyph: n.glyph,
    label: moonPhaseLabel(n.glyph),
    activa: idx === nodos.length - 1,
  }));
}

export function GraficasView({ initialHistory }: { initialHistory: HistoryResponse }) {
  const [rango, setRango] = useState<(typeof RANGOS)[number]>("30");
  const [history, setHistory] = useState(initialHistory);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState(false);
  const [vientoVista, setVientoVista] = useState<(typeof VISTAS_VIENTO)[number]>("hora");

  useEffect(() => {
    if (rango === "30" && history === initialHistory) return;
    let cancelled = false;
    setLoading(true);
    setFetchError(false);
    fetch(`/api/data/history?days=${rango}`)
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data: HistoryResponse) => {
        if (!cancelled) setHistory(data);
      })
      .catch(() => {
        if (!cancelled) setFetchError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rango]);

  const vientoSerie = useMemo(() => {
    if (vientoVista === "dia") return weatherToVientoDiario(history.weather);
    if (vientoVista === "7dias") return weatherToVientoSemanal(history.weather);
    return weatherToVientoSeries(history.weather);
  }, [history, vientoVista]);
  const tempSerie = useMemo(() => satelliteToTempSeries(history.satellite), [history]);
  const cloroSerie = useMemo(() => satelliteToChloroSeries(history.satellite), [history]);
  const capturaSerie = useMemo(() => catchToSeries(history.captura), [history]);

  function exportCSV() {
    const n = Math.max(vientoSerie.length, tempSerie.length, cloroSerie.length, capturaSerie.length);
    const rows = [["fecha", "temp_c", "viento_kmh", "clorofila_mgm3", "captura_idx"]];
    for (let i = 0; i < n; i++) {
      const fecha = tempSerie[i]?.x ?? vientoSerie[i]?.x ?? cloroSerie[i]?.x ?? capturaSerie[i]?.x ?? "";
      rows.push([fecha, tempSerie[i]?.v ?? "", vientoSerie[i]?.v ?? "", cloroSerie[i]?.v ?? "", capturaSerie[i]?.v ?? ""].map(String));
    }
    const csv = rows.map((r) => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `cienrayas_series_${rango}d.csv`;
    a.click();
  }
  const correlacion = useMemo(() => toCorrelacion(history.satellite, history.captura), [history]);
  const eventos = useMemo(() => semaphoreToEventos(history.semaphore), [history]);
  const luna = useMemo(() => fasesLuna(Number(rango)), [rango]);

  const cloroPeak = cloroSerie.length ? cloroSerie.reduce((mi, d, i, arr) => (d.v > arr[mi].v ? i : mi), 0) : 0;

  return (
    <div className="cr-content-scroll">
      <header className="cr-page-head">
        <div>
          <h1 className="serif cr-page-title">Gráficas e históricos</h1>
          <p className="mono cr-page-sub">
            {loading ? "Actualizando…" : `Registro de los últimos ${rango} días`}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {fetchError && <Pill tone="rojo">No se pudo actualizar</Pill>}
          <div className="cr-segment">
            {RANGOS.map((r) => (
              <button
                key={r}
                className={"cr-seg-btn" + (rango === r ? " active" : "")}
                disabled={loading}
                onClick={() => setRango(r)}
              >
                {r}d
              </button>
            ))}
          </div>
          <button className="cr-btn-ghost" onClick={exportCSV}>
            <Icon name="download" size={15} /> Exportar CSV
          </button>
        </div>
      </header>

      <CardGrid>
        <Card
          title="Velocidad del viento"
          label="Open-Meteo"
          span={12}
          motif="cana"
          actions={
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div className="cr-segment">
                {VISTAS_VIENTO.map((v) => (
                  <button
                    key={v}
                    className={"cr-seg-btn" + (vientoVista === v ? " active" : "")}
                    onClick={() => setVientoVista(v)}
                  >
                    {VISTA_VIENTO_LABEL[v]}
                  </button>
                ))}
              </div>
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-soft)" }}>
                km/h
              </span>
            </div>
          }
        >
          {vientoSerie.length > 1 ? (
            <LineChart data={vientoSerie} height={200} color="var(--verde)" area yMin={0} />
          ) : (
            <EmptySeries />
          )}
        </Card>

        <Card
          title="Temp. superficial del agua"
          label="NASA MODIS"
          span={6}
          motif="lirio"
          actions={
            <span className="mono" style={{ fontSize: 12, color: "var(--ink-soft)" }}>
              °C
            </span>
          }
        >
          {tempSerie.length > 1 ? <LineChart data={tempSerie} height={190} color="var(--teal)" area /> : <EmptySeries />}
        </Card>
        <Card
          title="Clorofila-a"
          label="Copernicus Marine"
          span={6}
          motif="mangle"
          actions={
            <span className="mono" style={{ fontSize: 12, color: "var(--ink-soft)" }}>
              mg/m³
            </span>
          }
        >
          {cloroSerie.length > 1 ? (
            <LineChart data={cloroSerie} height={190} color="var(--verde-sem)" area yMin={0} annotations={[{ i: cloroPeak, label: "Pico" }]} />
          ) : (
            <EmptySeries />
          )}
        </Card>

        <Card label="Ciclo lunar — ventana de observación" span={12} pad={24}>
          <div className="cr-luna">
            <div className="cr-luna-track" />
            {luna.map((f, i) => (
              <div key={i} className="cr-luna-node" style={{ left: `${(f.i / Math.max(1, Number(rango) - 1)) * 100}%` }}>
                <svg width="26" height="26" viewBox="0 0 22 22" style={{ background: "var(--surface)", borderRadius: "50%" }}>
                  <MoonGlyph phase={f.glyph} size={22} active={f.activa} />
                </svg>
                {/* con muchos nodos (ventanas largas) los textos chocan; solo el activo se rotula siempre */}
                {(luna.length <= 6 || f.activa) && (
                  <span
                    className="mono"
                    style={{ fontSize: 11, marginTop: 6, color: f.activa ? "var(--teal)" : "var(--ink-soft)", fontWeight: f.activa ? 700 : 400 }}
                  >
                    {f.label}
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>

        <Card title="Correlación" label="Clorofila-a vs. captura reportada" span={6} icon="gauge">
          {correlacion.length > 1 ? (
            <ScatterChart data={correlacion} xKey="cloro" yKey="captura" height={210} xLabel="Clorofila mg/m³ →" yLabel="Captura (índice) →" />
          ) : (
            <EmptySeries note="Sin reportes de captura en esta ventana" />
          )}
        </Card>

        <Card title="Eventos históricos" label="Frentes · vientos · sedimentación" span={6} icon="history">
          {eventos.length ? (
            <div className="cr-events">
              {eventos.map((e, i) => (
                <div key={i} className="cr-event-row">
                  <span style={{ marginTop: 3 }}>
                    <StatusDot tone={e.sem} pulse={e.sem === "rojo"} />
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
                      <span style={{ fontSize: 13.5, fontWeight: 600, color: "var(--ink)" }}>{e.tipo}</span>
                      <span className="mono" style={{ fontSize: 11, color: "var(--ink-faint)", flexShrink: 0 }}>
                        {e.fecha}
                      </span>
                    </div>
                    {e.variable && (
                      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "3px 0 3px" }}>
                        <MonoChip>{e.variable}</MonoChip>
                      </div>
                    )}
                    <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.45, color: "var(--ink-soft)" }}>{e.nota}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptySeries note="Sin eventos amarillo/rojo en esta ventana" />
          )}
        </Card>
      </CardGrid>
    </div>
  );
}

function EmptySeries({ note = "Sin datos suficientes en esta ventana" }: { note?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "24px 0" }}>
      <Pill tone="neutral">{note}</Pill>
    </div>
  );
}
