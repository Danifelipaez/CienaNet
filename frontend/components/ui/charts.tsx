"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { formatAxisTick, formatTooltipHeader, type ChartGranularity } from "@/components/charts/time-format";

export type SeriesPoint = { t: string; v: number };
export type MultiSeries = { label: string; color: string; data: SeriesPoint[] };

export function useWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(640);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setW(e.contentRect.width);
    });
    ro.observe(ref.current);
    setW(ref.current.clientWidth);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function fmtAxisValue(v: number): string {
  return Math.abs(v) >= 100 ? String(Math.round(v)) : v.toFixed(1);
}

/** Dominio con 20% de margen sobre el rango real de los datos (para que cambios pequeños se noten). */
function paddedDomain(vals: number[], floor?: number, ceil?: number): [number, number] {
  const dataMin = Math.min(...vals);
  const dataMax = Math.max(...vals);
  const span = dataMax - dataMin;
  const pad = span > 0 ? span * 0.2 : (Math.abs(dataMax) || 1) * 0.2;
  let lo = dataMin - pad;
  let hi = dataMax + pad;
  if (floor != null) lo = Math.max(lo, floor);
  if (ceil != null) hi = Math.min(hi, ceil);
  return [lo, hi];
}

/** Categoría sintética "ahora", en el mismo formato que las categorías reales de esa granularidad
 * (ver time-format.ts) — se agrega como tope del eje X para que la antigüedad del último dato real
 * quede visible como un espacio entre el punto y el borde derecho. */
function nowCategory(granularity: ChartGranularity): string {
  const now = new Date();
  return granularity === "hour" ? now.toISOString() : now.toISOString().slice(0, 10);
}

/**
 * Gráfica de series de tiempo — una o varias series sobre un eje X compartido. Reemplaza los antiguos
 * `LineChart`/`MultiLineChart`: toda gráfica de serie de tiempo pasa por aquí, así que hover, leyenda
 * y convenciones son siempre las mismas sin importar cuántas series traiga.
 */
export function TimeSeriesChart({
  series,
  granularity,
  aggregated = false,
  height = 200,
  yMin,
  yMax,
  area = false,
  dashGrid = true,
  annotations = [],
}: {
  series: MultiSeries[];
  granularity: ChartGranularity;
  aggregated?: boolean;
  height?: number;
  yMin?: number;
  yMax?: number;
  area?: boolean;
  dashGrid?: boolean;
  annotations?: { seriesIndex: number; pointIndex: number; label: string }[];
}) {
  const [ref, w] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const padL = 38,
    padR = 14,
    padT = 18,
    padB = 26;
  const now = useMemo(() => nowCategory(granularity), [granularity]);
  const categories = Array.from(new Set([...series.flatMap((s) => s.data.map((d) => d.t)), now])).sort();
  const vals = series.flatMap((s) => s.data.map((d) => d.v));
  const [mn, mx] = paddedDomain(vals.length ? vals : [0, 1], yMin, yMax);
  const range = mx - mn || 1;
  const iw = Math.max(10, w - padL - padR),
    ih = height - padT - padB;
  const X = (i: number) => padL + (i / Math.max(1, categories.length - 1)) * iw;
  const Y = (v: number) => padT + ih - ((v - mn) / range) * ih;
  const xTickCount = Math.min(5, categories.length);
  const xTicks = Array.from(
    new Set(
      Array.from({ length: xTickCount }, (_, k) =>
        Math.round((k / Math.max(1, xTickCount - 1)) * (categories.length - 1))
      )
    )
  );
  const yTicks = [0, 0.25, 0.5, 0.75, 1];

  function handleMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const idx = Math.round(((px - padL) / iw) * (categories.length - 1));
    setHover(Math.max(0, Math.min(categories.length - 1, idx)));
  }

  const hoverRows =
    hover != null
      ? series
          .map((s) => ({ s, pt: s.data.find((d) => d.t === categories[hover]) }))
          .filter((r): r is { s: MultiSeries; pt: SeriesPoint } => r.pt != null)
      : [];

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg
        width={w}
        height={height}
        style={{ display: "block", overflow: "visible", cursor: "crosshair" }}
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
      >
        {dashGrid &&
          yTicks.map((g, i) => (
            <line
              key={i}
              x1={padL}
              x2={w - padR}
              y1={padT + ih * (1 - g)}
              y2={padT + ih * (1 - g)}
              stroke="var(--border)"
              strokeWidth="1"
              strokeDasharray="2 5"
            />
          ))}
        {yTicks.map((g, i) => (
          <text
            key={i}
            x={padL - 6}
            y={padT + ih * (1 - g) + 3}
            textAnchor="end"
            className="mono"
            fontSize="10"
            fill="var(--ink-faint)"
          >
            {fmtAxisValue(mn + range * g)}
          </text>
        ))}
        {series.map((s, si) => {
          const pts = s.data
            .map((d) => ({ i: categories.indexOf(d.t), v: d.v }))
            .filter((p) => p.i >= 0)
            .sort((a, b) => a.i - b.i);
          if (pts.length < 2) return null;
          const line = pts.map((p, i) => (i ? "L" : "M") + X(p.i).toFixed(1) + " " + Y(p.v).toFixed(1)).join(" ");
          const areaP = area
            ? line + ` L ${X(pts[pts.length - 1].i).toFixed(1)} ${padT + ih} L ${X(pts[0].i).toFixed(1)} ${padT + ih} Z`
            : null;
          return (
            <g key={si}>
              {areaP && <path d={areaP} fill={s.color} fillOpacity="0.1" />}
              <path d={line} fill="none" stroke={s.color} strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" />
            </g>
          );
        })}
        {annotations.map((a, i) => {
          const pt = series[a.seriesIndex]?.data[a.pointIndex];
          const ci = pt ? categories.indexOf(pt.t) : -1;
          if (!pt || ci < 0) return null;
          const x = X(ci),
            y = Y(pt.v);
          return (
            <g key={i}>
              <circle cx={x} cy={y} r="3.5" fill={series[a.seriesIndex].color} stroke="var(--surface)" strokeWidth="1.5" />
              <text x={x} y={y - 10} textAnchor="middle" className="mono" fontSize="10" fill="var(--teal)" fontWeight="600">
                {a.label}
              </text>
            </g>
          );
        })}
        {xTicks.map((ti, i) => (
          <text
            key={i}
            x={X(ti)}
            y={height - 7}
            textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"}
            className="mono"
            fontSize="10.5"
            fill="var(--ink-faint)"
          >
            {formatAxisTick(categories[ti], granularity)}
          </text>
        ))}
        {hover != null && hoverRows.length > 0 && (
          <g>
            <line x1={X(hover)} x2={X(hover)} y1={padT} y2={padT + ih} stroke="var(--ink-faint)" strokeOpacity="0.35" strokeWidth="1" />
            {hoverRows.map(({ s, pt }, i) => (
              <circle key={i} cx={X(hover)} cy={Y(pt.v)} r="4" fill={s.color} stroke="var(--surface)" strokeWidth="1.5" />
            ))}
            {(() => {
              const header = formatTooltipHeader(categories[hover], granularity, aggregated);
              const maxChars = Math.max(header.length, ...hoverRows.map((r) => `${r.s.label} ${fmtAxisValue(r.pt.v)}`.length));
              const tw = Math.max(74, maxChars * 5.6 + 16);
              const th = 18 + hoverRows.length * 14 + 6;
              const topY = Math.min(...hoverRows.map((r) => Y(r.pt.v)));
              const boxX = Math.min(Math.max(X(hover) - tw / 2, padL), w - padR - tw);
              const boxY = Math.max(topY - th - 10, 2);
              return (
                <g>
                  <rect x={boxX} y={boxY} width={tw} height={th} rx="6" fill="var(--surface)" stroke="var(--border)" />
                  <text x={boxX + tw / 2} y={boxY + 14} textAnchor="middle" className="mono" fontSize="10" fontWeight="700" fill="var(--ink)">
                    {header}
                  </text>
                  {hoverRows.map((r, i) => (
                    <g key={i}>
                      <circle cx={boxX + 10} cy={boxY + 14 * (i + 2) - 3} r="3" fill={r.s.color} />
                      <text x={boxX + 18} y={boxY + 14 * (i + 2)} className="mono" fontSize="9.5" fill="var(--ink-soft)">
                        {r.s.label}: {fmtAxisValue(r.pt.v)}
                      </text>
                    </g>
                  ))}
                </g>
              );
            })()}
          </g>
        )}
      </svg>
      <div style={{ display: "flex", gap: 14, marginTop: 4, flexWrap: "wrap" }}>
        {series.map((s, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: s.color, display: "inline-block" }} />
            <span className="mono" style={{ fontSize: 11, color: "var(--ink-soft)" }}>
              {s.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ScatterChart({
  data,
  xKey = "cloro",
  yKey = "captura",
  dateKey,
  height = 220,
  color = "var(--teal)",
  xLabel,
  yLabel,
}: {
  data: Record<string, number | string>[];
  xKey?: string;
  yKey?: string;
  dateKey?: string;
  height?: number;
  color?: string;
  xLabel?: string;
  yLabel?: string;
}) {
  const [ref, w] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const padL = 34,
    padR = 14,
    padT = 14,
    padB = 30;
  const xs = data.map((d) => Number(d[xKey])),
    ys = data.map((d) => Number(d[yKey]));
  const xmn = Math.min(...xs),
    xmx = Math.max(...xs),
    ymn = Math.min(...ys),
    ymx = Math.max(...ys);
  const iw = Math.max(10, w - padL - padR),
    ih = height - padT - padB;
  const X = (v: number) => padL + ((v - xmn) / (xmx - xmn || 1)) * iw;
  const Y = (v: number) => padT + ih - ((v - ymn) / (ymx - ymn || 1)) * ih;
  const n = data.length,
    sx = xs.reduce((a, b) => a + b, 0),
    sy = ys.reduce((a, b) => a + b, 0);
  const sxy = data.reduce((a, d, i) => a + xs[i] * ys[i], 0),
    sxx = xs.reduce((a, b) => a + b * b, 0);
  const slope = (n * sxy - sx * sy) / (n * sxx - sx * sx || 1),
    intc = (sy - slope * sx) / n;

  const HIT_RADIUS = 18;
  function handleMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left,
      py = e.clientY - rect.top;
    let best = -1,
      bestDist = HIT_RADIUS * HIT_RADIUS;
    for (let i = 0; i < data.length; i++) {
      const dx = X(xs[i]) - px,
        dy = Y(ys[i]) - py;
      const dist = dx * dx + dy * dy;
      if (dist < bestDist) {
        bestDist = dist;
        best = i;
      }
    }
    setHover(best >= 0 ? best : null);
  }

  const hoverPt = hover != null ? data[hover] : null;

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg
        width={w}
        height={height}
        style={{ display: "block", overflow: "visible", cursor: "crosshair" }}
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
      >
        {[0, 0.5, 1].map((g, i) => (
          <line key={i} x1={padL} x2={w - padR} y1={padT + ih * g} y2={padT + ih * g} stroke="var(--border)" strokeDasharray="2 5" />
        ))}
        <line
          x1={X(xmn)}
          y1={Y(slope * xmn + intc)}
          x2={X(xmx)}
          y2={Y(slope * xmx + intc)}
          stroke="var(--salmon)"
          strokeWidth="1.6"
          strokeDasharray="5 4"
        />
        {data.map((d, i) => (
          <circle
            key={i}
            cx={X(xs[i])}
            cy={Y(ys[i])}
            r={hover === i ? "5.5" : "4"}
            fill={color}
            fillOpacity={hover === i ? "0.85" : "0.5"}
            stroke={color}
            strokeWidth={hover === i ? "1.6" : "1"}
          />
        ))}
        <text x={padL} y={height - 8} className="mono" fontSize="10.5" fill="var(--ink-faint)">
          {xLabel}
        </text>
        <text
          x={2}
          y={padT + 6}
          className="mono"
          fontSize="10.5"
          fill="var(--ink-faint)"
          transform={`rotate(-90 10 ${padT + ih / 2})`}
        >
          {yLabel}
        </text>
        {hoverPt && hover != null && (
          <g>
            {(() => {
              const rows = [
                `${xLabel ?? xKey}: ${fmtAxisValue(Number(hoverPt[xKey]))}`,
                `${yLabel ?? yKey}: ${fmtAxisValue(Number(hoverPt[yKey]))}`,
              ];
              const dateVal = dateKey ? hoverPt[dateKey] : undefined;
              if (typeof dateVal === "string") rows.unshift(formatTooltipHeader(dateVal, "day"));
              const maxChars = Math.max(...rows.map((r) => r.length));
              const tw = Math.max(90, maxChars * 5.6 + 16);
              const th = 8 + rows.length * 14 + 6;
              const boxX = Math.min(Math.max(X(xs[hover]) - tw / 2, padL), w - padR - tw);
              const boxY = Math.max(Y(ys[hover]) - th - 10, 2);
              return (
                <g>
                  <rect x={boxX} y={boxY} width={tw} height={th} rx="6" fill="var(--surface)" stroke="var(--border)" />
                  {rows.map((r, i) => (
                    <text
                      key={i}
                      x={boxX + tw / 2}
                      y={boxY + 14 * (i + 1)}
                      textAnchor="middle"
                      className="mono"
                      fontSize={i === 0 && dateVal ? "9.5" : "10"}
                      fontWeight={i === 0 && dateVal ? "400" : "700"}
                      fill={i === 0 && dateVal ? "var(--ink-faint)" : "var(--ink)"}
                    >
                      {r}
                    </text>
                  ))}
                </g>
              );
            })()}
          </g>
        )}
      </svg>
    </div>
  );
}

export function MiniBars({ values, peakIndex, height = 56 }: { values: number[]; peakIndex?: number; height?: number }) {
  const mx = Math.max(...values);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 8, height }}>
      {values.map((v, i) => {
        const peak = i === peakIndex;
        return (
          <div key={i} style={{ flex: 1, position: "relative" }}>
            {peak && (
              <span
                className="mono"
                style={{
                  position: "absolute",
                  top: -15,
                  left: "50%",
                  transform: "translateX(-50%)",
                  fontSize: 9,
                  color: "var(--rojo)",
                  fontWeight: 600,
                }}
              >
                Pico
              </span>
            )}
            <div
              style={{
                height: `${(v / mx) * 100}%`,
                borderRadius: "5px 5px 0 0",
                background: peak ? "var(--rojo-soft)" : `color-mix(in oklch, var(--verde-sem) ${30 + i * 12}%, var(--surface-3))`,
                border: peak ? "1px solid var(--rojo)" : "none",
                minHeight: 6,
              }}
            />
          </div>
        );
      })}
    </div>
  );
}

export function MoonGlyph({ phase, size = 22, active }: { phase: "new" | "first" | "full" | "last"; size?: number; active?: boolean }) {
  const c = active ? "var(--teal)" : "var(--ink-faint)";
  if (phase === "full") return <circle cx={size / 2} cy={size / 2} r={size / 2 - 1} fill={c} />;
  if (phase === "new")
    return <circle cx={size / 2} cy={size / 2} r={size / 2 - 1.5} fill="none" stroke={c} strokeWidth="1.6" />;
  const flip = phase === "last";
  return (
    <g>
      <circle cx={size / 2} cy={size / 2} r={size / 2 - 1.5} fill="none" stroke={c} strokeWidth="1.6" />
      <path
        d={`M${size / 2} 1.5 A ${size / 2 - 1.5} ${size / 2 - 1.5} 0 0 ${flip ? 0 : 1} ${size / 2} ${size - 1.5} A ${size / 3.2} ${size / 2 - 1.5} 0 0 ${flip ? 1 : 0} ${size / 2} 1.5 Z`}
        fill={c}
      />
    </g>
  );
}
