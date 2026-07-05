"use client";

import { useLayoutEffect, useRef, useState } from "react";

export type SeriesPoint = { x: string; v: number };

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

export function LineChart({
  data,
  height = 200,
  color = "var(--verde)",
  fill = false,
  annotations = [],
  yMin,
  yMax,
  area = false,
  dashGrid = true,
}: {
  data: SeriesPoint[];
  height?: number;
  color?: string;
  fill?: boolean;
  unit?: string;
  annotations?: { i: number; label: string }[];
  /** Piso/techo físico opcional (p.ej. 0 para valores que no pueden ser negativos) — no es el límite exacto del eje, el eje siempre añade el margen del 20%. */
  yMin?: number;
  yMax?: number;
  area?: boolean;
  dashGrid?: boolean;
}) {
  const [ref, w] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const padL = 38,
    padR = 14,
    padT = 18,
    padB = 26;
  const vals = data.map((d) => d.v);
  const [mn, mx] = paddedDomain(vals, yMin, yMax);
  const range = mx - mn || 1;
  const iw = Math.max(10, w - padL - padR),
    ih = height - padT - padB;
  const X = (i: number) => padL + (i / Math.max(1, data.length - 1)) * iw;
  const Y = (v: number) => padT + ih - ((v - mn) / range) * ih;
  const pts = data.map((d, i) => [X(i), Y(d.v)]);
  const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const areaP = line + ` L ${X(data.length - 1).toFixed(1)} ${padT + ih} L ${padL} ${padT + ih} Z`;
  const xTickCount = Math.min(5, data.length);
  const xTicks = Array.from(
    new Set(
      Array.from({ length: xTickCount }, (_, k) =>
        Math.round((k / Math.max(1, xTickCount - 1)) * (data.length - 1))
      )
    )
  );
  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const gid = "g" + Math.abs(color.length * 7 + data.length).toString(36);
  const hoverPt = hover != null ? data[hover] : null;

  function handleMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const idx = Math.round(((px - padL) / iw) * (data.length - 1));
    setHover(Math.max(0, Math.min(data.length - 1, idx)));
  }

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg
        width={w}
        height={height}
        style={{ display: "block", overflow: "visible", cursor: "crosshair" }}
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.16" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
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
        {(area || fill) && <path d={areaP} fill={`url(#${gid})`} />}
        <path d={line} fill="none" stroke={color} strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" />
        {annotations.map((a, i) => {
          const x = X(a.i),
            y = Y(data[a.i].v);
          return (
            <g key={i}>
              <circle cx={x} cy={y} r="3.5" fill={color} stroke="var(--surface)" strokeWidth="1.5" />
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
            {data[ti].x}
          </text>
        ))}
        {hoverPt && (
          <g>
            <line x1={X(hover!)} x2={X(hover!)} y1={padT} y2={padT + ih} stroke={color} strokeOpacity="0.35" strokeWidth="1" />
            <circle cx={X(hover!)} cy={Y(hoverPt.v)} r="4" fill={color} stroke="var(--surface)" strokeWidth="1.5" />
            {(() => {
              const tw = 60,
                th = 34;
              const boxX = Math.min(Math.max(X(hover!) - tw / 2, padL), w - padR - tw);
              const boxY = Math.max(Y(hoverPt.v) - th - 10, 2);
              return (
                <g>
                  <rect x={boxX} y={boxY} width={tw} height={th} rx="6" fill="var(--surface)" stroke="var(--border)" />
                  <text x={boxX + tw / 2} y={boxY + 15} textAnchor="middle" className="mono" fontSize="11" fontWeight="700" fill="var(--ink)">
                    {fmtAxisValue(hoverPt.v)}
                  </text>
                  <text x={boxX + tw / 2} y={boxY + 27} textAnchor="middle" className="mono" fontSize="9" fill="var(--ink-faint)">
                    {hoverPt.x}
                  </text>
                </g>
              );
            })()}
          </g>
        )}
      </svg>
    </div>
  );
}

export function ScatterChart({
  data,
  xKey = "cloro",
  yKey = "captura",
  height = 220,
  color = "var(--teal)",
  xLabel,
  yLabel,
}: {
  data: Record<string, number>[];
  xKey?: string;
  yKey?: string;
  height?: number;
  color?: string;
  xLabel?: string;
  yLabel?: string;
}) {
  const [ref, w] = useWidth();
  const padL = 34,
    padR = 14,
    padT = 14,
    padB = 30;
  const xs = data.map((d) => d[xKey]),
    ys = data.map((d) => d[yKey]);
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
  const sxy = data.reduce((a, d) => a + d[xKey] * d[yKey], 0),
    sxx = xs.reduce((a, b) => a + b * b, 0);
  const slope = (n * sxy - sx * sy) / (n * sxx - sx * sx || 1),
    intc = (sy - slope * sx) / n;
  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width={w} height={height} style={{ display: "block", overflow: "visible" }}>
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
          <circle key={i} cx={X(d[xKey])} cy={Y(d[yKey])} r="4" fill={color} fillOpacity="0.5" stroke={color} strokeWidth="1" />
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
