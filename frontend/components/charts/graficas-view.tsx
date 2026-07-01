"use client";

import { useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/ui/icon";
import { Card, CardGrid } from "@/components/ui/card";
import { MonoChip, Pill, StatusDot } from "@/components/ui/primitives";
import { LineChart, ScatterChart, MoonGlyph } from "@/components/ui/charts";
import type { HistoryResponse } from "@/lib/api";
import {
  weatherToVientoSeries,
  satelliteToTempSeries,
  satelliteToChloroSeries,
  catchToSeries,
  toCorrelacion,
  semaphoreToEventos,
} from "./adapters";
import { moonPhaseGlyph, moonPhaseLabel } from "@/lib/moon";

const RANGOS = ["7", "30", "90"] as const;

function fasesLuna(days: number) {
  const now = new Date();
  const offsets = [days - 1, Math.floor(days * 0.75), Math.floor(days * 0.5), Math.floor(days * 0.25), 0];
  return offsets.map((offsetDaysAgo, idx) => {
    const d = new Date(now);
    d.setDate(d.getDate() - offsetDaysAgo);
    const glyph = moonPhaseGlyph(d);
    return { i: days - 1 - offsetDaysAgo, glyph, label: moonPhaseLabel(glyph), activa: idx === offsets.length - 1 };
  });
}

export function GraficasView({ initialHistory }: { initialHistory: HistoryResponse }) {
  const [rango, setRango] = useState<(typeof RANGOS)[number]>("30");
  const [history, setHistory] = useState(initialHistory);

  useEffect(() => {
    if (rango === "30" && history === initialHistory) return;
    let cancelled = false;
    fetch(`/api/data/history?days=${rango}`)
      .then((r) => r.json())
      .then((data: HistoryResponse) => {
        if (!cancelled) setHistory(data);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rango]);

  const vientoSerie = useMemo(() => weatherToVientoSeries(history.weather), [history]);
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
          <p className="mono cr-page-sub">Registro de los últimos {rango} días</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div className="cr-segment">
            {RANGOS.map((r) => (
              <button key={r} className={"cr-seg-btn" + (rango === r ? " active" : "")} onClick={() => setRango(r)}>
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
            <span className="mono" style={{ fontSize: 12, color: "var(--ink-soft)" }}>
              km/h
            </span>
          }
        >
          {vientoSerie.length > 1 ? (
            <LineChart data={vientoSerie} height={200} color="var(--verde)" area yMin={0} yMax={48} />
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
          {tempSerie.length > 1 ? <LineChart data={tempSerie} height={190} color="var(--teal)" area yMin={27.5} yMax={34.5} /> : <EmptySeries />}
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
                <span
                  className="mono"
                  style={{ fontSize: 11, marginTop: 6, color: f.activa ? "var(--teal)" : "var(--ink-soft)", fontWeight: f.activa ? 700 : 400 }}
                >
                  {f.label}
                </span>
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
