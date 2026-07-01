"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type * as LeafletType from "leaflet";
import "leaflet/dist/leaflet.css";
import { Icon } from "@/components/ui/icon";
import { StatusDot, SectionLabel, MonoChip, Toggle } from "@/components/ui/primitives";
import { MoonGlyph } from "@/components/ui/charts";
import type { PuntoPesca, Especie } from "@/lib/api";

const CR_CENTER: [number, number] = [10.86, -74.43];

function semColor(c: string) {
  return c === "rojo" ? "#C05746" : c === "amarillo" ? "#C9981E" : "#4A7C59";
}
function semLabel(c: string) {
  return c === "rojo" ? "Crítica" : c === "amarillo" ? "Precaución" : "Estable";
}

function markerIcon(L: typeof import("leaflet"), cond: string, selected: boolean) {
  const col = semColor(cond);
  const s = selected ? 40 : 32;
  return L.divIcon({
    className: "cr-marker",
    iconSize: [s, s * 1.3],
    iconAnchor: [s / 2, s * 1.3 - 2],
    html: `<svg width="${s}" height="${s * 1.3}" viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg">
      <path d="M16 41 C16 41 29 25 29 14 A13 13 0 1 0 3 14 C3 25 16 41 16 41Z"
        fill="${col}" stroke="#fff" stroke-width="2.2"/>
      <circle cx="16" cy="14" r="5" fill="#fff" fill-opacity="${selected ? 1 : 0.92}"/>
      ${selected ? `<circle cx="16" cy="14" r="2.4" fill="${col}"/>` : ""}
    </svg>`,
  });
}

function popupHTML(p: PuntoPesca) {
  return `<div style="padding:14px 16px;font-family:var(--font-body)">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px">
      <span class="serif" style="font-size:18px;font-weight:600;color:var(--verde)">${p.nombre}</span>
      <span class="mono" style="font-size:10px;font-weight:600;letter-spacing:.04em;padding:3px 8px;border-radius:999px;background:${semColor(p.condicion)}22;color:${semColor(p.condicion)}">${semLabel(p.condicion).toUpperCase()}</span>
    </div>
    <div style="display:flex;gap:14px;margin-bottom:10px">
      <div><div class="mono" style="font-size:10px;color:var(--ink-faint);text-transform:uppercase;letter-spacing:.1em">Temp. sup.</div><div class="serif" style="font-size:17px;color:var(--ink)">${(p.temp ?? 0).toFixed(1)}<span class="mono" style="font-size:11px;color:var(--ink-soft)"> °C</span></div></div>
      <div><div class="mono" style="font-size:10px;color:var(--ink-faint);text-transform:uppercase;letter-spacing:.1em">Clorofila-a</div><div class="serif" style="font-size:17px;color:var(--ink)">${(p.clorofila ?? 0).toFixed(1)}<span class="mono" style="font-size:11px;color:var(--ink-soft)"> mg/m³</span></div></div>
    </div>
    <div style="font-size:12.5px;line-height:1.45;color:var(--ink-soft);border-top:1px solid var(--border);padding-top:9px">
      <div class="mono" style="font-size:9.5px;color:var(--ink-faint);text-transform:uppercase;letter-spacing:.1em;margin-bottom:3px">Observación comunitaria</div>
      ${p.observacion ?? ""}
    </div>
  </div>`;
}

export default function MapaView({
  puntos,
  especies,
  sedimentacion,
}: {
  puntos: PuntoPesca[];
  especies: Especie[];
  sedimentacion: [number, number][][];
}) {
  const mapRef = useRef<LeafletType.Map | null>(null);
  const elRef = useRef<HTMLDivElement | null>(null);
  const markerRef = useRef<Record<string, LeafletType.Marker>>({});
  const [center, setCenter] = useState<[number, number]>(CR_CENTER);
  const [selected, setSelected] = useState<PuntoPesca | undefined>(() =>
    puntos.find((p) => p.condicion === "rojo") ?? puntos[0]
  );
  const [layers, setLayers] = useState({
    puntos: true,
    semaforo: true,
    sst: false,
    clorofila: false,
    sedimentacion: false,
  });
  const [query, setQuery] = useState("");
  const [showSug, setShowSug] = useState(false);
  const [variable, setVariable] = useState("temp");
  const [especie, setEspecie] = useState("all");
  const [faseLuna, setFaseLuna] = useState(false);

  useEffect(() => {
    if (!elRef.current || mapRef.current) return;
    let disposed = false;

    import("leaflet").then((mod) => {
      if (disposed || !elRef.current || mapRef.current) return;
      const L = mod.default;
      const map = L.map(elRef.current, {
        center: CR_CENTER,
        zoom: 11,
        zoomControl: false,
        attributionControl: true,
        minZoom: 9,
        maxZoom: 15,
      });
      L.control.zoom({ position: "topright" }).addTo(map);
      L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
        attribution: "© OpenStreetMap · © CARTO",
        subdomains: "abcd",
        maxZoom: 19,
      }).addTo(map);

      ["sst", "clorofila", "sedimentacion", "semaforo", "puntos"].forEach((p, i) => {
        map.createPane("pane-" + p);
        const pane = map.getPane("pane-" + p)!;
        pane.style.transition = "opacity .3s ease";
        pane.style.zIndex = String(400 + i * 10);
      });

      const sstG = L.layerGroup();
      puntos.forEach((p) => {
        const t = p.temp ?? 29;
        const k = Math.min(1, Math.max(0, (t - 29) / 5));
        const col = `rgb(${Math.round(180 + k * 70)}, ${Math.round(190 - k * 120)}, ${Math.round(120 - k * 70)})`;
        L.circle([p.lat, p.lng], { radius: 3400, color: col, weight: 0, fillColor: col, fillOpacity: 0.32, pane: "pane-sst" }).addTo(sstG);
      });
      const chlG = L.layerGroup();
      puntos.forEach((p) => {
        const k = Math.min(1, (p.clorofila ?? 0) / 9);
        const col = `rgb(${Math.round(120 - k * 60)}, ${Math.round(160 - k * 30)}, ${Math.round(90 - k * 30)})`;
        L.circle([p.lat, p.lng], { radius: 2600 + k * 1500, color: col, weight: 0, fillColor: col, fillOpacity: 0.3, pane: "pane-clorofila" }).addTo(chlG);
      });
      const sedG = L.layerGroup();
      sedimentacion.forEach((poly) => {
        L.polygon(poly, { color: "#C4A882", weight: 1, fillColor: "#C4A882", fillOpacity: 0.4, dashArray: "4 4", pane: "pane-sedimentacion" }).addTo(sedG);
      });
      const semG = L.layerGroup();
      puntos.forEach((p) => {
        L.circleMarker([p.lat, p.lng], {
          radius: 16,
          color: semColor(p.condicion),
          weight: 2,
          fillOpacity: 0.1,
          fillColor: semColor(p.condicion),
          pane: "pane-semaforo",
        }).addTo(semG);
      });
      const ptsG = L.layerGroup();
      puntos.forEach((p) => {
        const m = L.marker([p.lat, p.lng], { icon: markerIcon(L, p.condicion, false), pane: "pane-puntos" });
        m.bindPopup(popupHTML(p), { className: "cr-popup", closeButton: true, offset: [0, -30] });
        m.on("click", () => setSelected(p));
        m.addTo(ptsG);
        markerRef.current[p.id] = m;
      });

      sstG.addTo(map);
      chlG.addTo(map);
      sedG.addTo(map);
      semG.addTo(map);
      ptsG.addTo(map);

      map.on("move", () => {
        const c = map.getCenter();
        setCenter([c.lat, c.lng]);
      });
      mapRef.current = map;
      setTimeout(() => map.invalidateSize(), 60);
    });

    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    Object.entries(layers).forEach(([k, on]) => {
      const pane = map.getPane("pane-" + k);
      if (pane) {
        pane.style.opacity = on ? "1" : "0";
        pane.style.pointerEvents = on ? "auto" : "none";
      }
    });
  }, [layers]);

  useEffect(() => {
    Object.entries(markerRef.current).forEach(([id, m]) => {
      const p = puntos.find((x) => x.id === id);
      if (!p) return;
      import("leaflet").then((mod) => m.setIcon(markerIcon(mod.default, p.condicion, selected?.id === id)));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const sugerencias = useMemo(() => {
    if (!query.trim()) return [];
    const q = query.toLowerCase();
    return puntos.filter((p) => p.nombre.toLowerCase().includes(q)).slice(0, 6);
  }, [query, puntos]);

  function goTo(p: PuntoPesca) {
    setSelected(p);
    setQuery(p.nombre);
    setShowSug(false);
    const map = mapRef.current;
    if (map) {
      map.flyTo([p.lat, p.lng], 12.5, { duration: 0.8 });
      setTimeout(() => markerRef.current[p.id]?.openPopup(), 850);
    }
  }

  const especiesFiltradas = especie === "all" ? puntos : puntos.filter((p) => p.especies.includes(especie));

  const capas = [
    { id: "sst", icon: "thermometer", nombre: "Temp. superficial", sub: "NASA MODIS", tone: "rojo" },
    { id: "clorofila", icon: "leaf", nombre: "Clorofila-a", sub: "Copernicus Marine", tone: "teal" },
    { id: "puntos", icon: "pin", nombre: "Puntos de pesca", sub: `${puntos.length} puntos · comunidad`, tone: "verde" },
    { id: "sedimentacion", icon: "waves", nombre: "Sedimentación", sub: "Zonas críticas", tone: "sediment" },
    { id: "semaforo", icon: "dot", nombre: "Semáforo", sub: "Condición por zona", tone: "amarillo" },
  ] as const;

  return (
    <div className="cr-mapa">
      <div className="cr-mapa-canvas">
        <div ref={elRef} style={{ position: "absolute", inset: 0 }} />
        <div className="cr-map-search">
          <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "0 12px", height: 44 }}>
            <span style={{ color: "var(--ink-soft)", display: "flex" }}>
              <Icon name="search" size={17} />
            </span>
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setShowSug(true);
              }}
              onFocus={() => setShowSug(true)}
              placeholder="Buscar punto de pesca…"
              style={{ border: "none", outline: "none", background: "transparent", flex: 1, fontSize: 14, color: "var(--ink)", fontFamily: "var(--font-body)" }}
            />
            {query && (
              <button
                onClick={() => {
                  setQuery("");
                  setShowSug(false);
                }}
                style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--ink-faint)", display: "flex" }}
              >
                <Icon name="x" size={15} />
              </button>
            )}
          </div>
          {showSug && sugerencias.length > 0 && (
            <div className="cr-sug">
              {sugerencias.map((p) => (
                <button key={p.id} onClick={() => goTo(p)} className="cr-sug-item">
                  <span style={{ display: "flex" }}>
                    <StatusDot tone={p.condicion} />
                  </span>
                  <span style={{ flex: 1, textAlign: "left" }}>{p.nombre}</span>
                  <span className="mono" style={{ fontSize: 11, color: "var(--ink-faint)" }}>
                    {p.especies[0]}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="cr-coord mono">
          <Icon name="target" size={13} />
          {Math.abs(center[0]).toFixed(3)}°N, {Math.abs(center[1]).toFixed(3)}°W
        </div>
      </div>

      <aside className="cr-map-panel">
        <div className="cr-map-panel-head">
          <h2 className="serif" style={{ margin: 0, fontSize: 23, fontWeight: 600, color: "var(--verde)" }}>
            Capas y filtros
          </h2>
          <span style={{ color: "var(--ink-soft)", display: "flex" }}>
            <Icon name="sliders" size={19} />
          </span>
        </div>

        <div className="cr-map-panel-body">
          <div className="cr-mini-card">
            <SectionLabel>Ventana de observación</SectionLabel>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 7 }}>
              <span style={{ color: "var(--verde)", display: "flex" }}>
                <Icon name="calendar" size={16} />
              </span>
              <span className="mono" style={{ fontSize: 13, color: "var(--ink)" }}>
                Últimos 30 días
              </span>
            </div>
          </div>

          <SectionLabel style={{ margin: "4px 0 2px" }}>Capas de datos</SectionLabel>
          {capas.map((c) => (
            <div key={c.id} className="cr-layer-row">
              <span
                className="cr-layer-ic"
                style={{
                  background: `var(--${c.tone === "sediment" ? "sedimento" : c.tone}-soft, var(--surface-3))`,
                  color: `var(--${c.tone === "sediment" ? "sedimento" : c.tone === "verde" ? "verde-sem" : c.tone})`,
                }}
              >
                <Icon name={c.icon} size={16} />
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--ink)" }}>{c.nombre}</div>
                <div className="mono" style={{ fontSize: 10.5, color: "var(--ink-faint)" }}>
                  {c.sub}
                </div>
              </div>
              <Toggle on={layers[c.id]} onChange={(v) => setLayers((s) => ({ ...s, [c.id]: v }))} label={c.nombre} />
            </div>
          ))}

          <SectionLabel style={{ margin: "8px 0 2px" }}>Filtros</SectionLabel>
          <div className="cr-mini-card" style={{ display: "grid", gap: 12 }}>
            <label className="cr-field">
              <span className="mono cr-field-lbl">Variable ambiental</span>
              <select value={variable} onChange={(e) => setVariable(e.target.value)} className="cr-select">
                <option value="temp">Temperatura superficial</option>
                <option value="clorofila">Clorofila-a</option>
                <option value="viento">Viento</option>
              </select>
            </label>
            <label className="cr-field">
              <span className="mono cr-field-lbl">Especie objetivo</span>
              <select value={especie} onChange={(e) => setEspecie(e.target.value)} className="cr-select">
                <option value="all">Todas</option>
                {especies.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.label}
                  </option>
                ))}
              </select>
            </label>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ color: "var(--teal)", display: "flex" }}>
                  <Icon name="moon" size={16} />
                </span>
                <span style={{ fontSize: 13, color: "var(--ink)" }}>Fase lunar actual</span>
              </div>
              <Toggle on={faseLuna} onChange={setFaseLuna} label="Fase lunar" />
            </div>
            {faseLuna && (
              <div
                className="mono"
                style={{ fontSize: 11.5, color: "var(--ink-soft)", display: "flex", alignItems: "center", gap: 8, background: "var(--surface-3)", padding: "7px 10px", borderRadius: 8 }}
              >
                <svg width="18" height="18" viewBox="0 0 22 22">
                  <MoonGlyph phase="full" size={18} active />
                </svg>
                Luna llena · mareas vivas
              </div>
            )}
            {especie !== "all" && (
              <div className="mono" style={{ fontSize: 11, color: "var(--teal)" }}>
                {especiesFiltradas.length} puntos con {especies.find((e) => e.id === especie)?.label.toLowerCase()}
              </div>
            )}
          </div>

          {selected && (
            <div className="cr-notes" style={{ animation: "cr-fade-up .3s ease" }}>
              <SectionLabel>Notas del punto seleccionado</SectionLabel>
              <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "7px 0 4px" }}>
                <StatusDot tone={selected.condicion} pulse={selected.condicion === "rojo"} />
                <span className="serif" style={{ fontSize: 19, fontStyle: "italic", color: "var(--verde)" }}>
                  {selected.nombre}
                </span>
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "2px 0 9px" }}>
                <MonoChip tone="teal">{(selected.temp ?? 0).toFixed(1)} °C</MonoChip>
                <MonoChip>{(selected.clorofila ?? 0).toFixed(1)} mg/m³</MonoChip>
                <MonoChip tone="sediment">{selected.especies.join(" · ")}</MonoChip>
              </div>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: "var(--ink-soft)" }}>{selected.observacion}</p>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
