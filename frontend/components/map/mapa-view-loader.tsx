"use client";

import dynamic from "next/dynamic";
import type { PuntoPesca, Especie } from "@/lib/api";
import type { EstacionSnapshot } from "@/lib/stations";

const MapaView = dynamic(() => import("./mapa-view"), {
  ssr: false,
  loading: () => <div className="cr-mapa" style={{ alignItems: "center", justifyContent: "center", display: "flex" }}>Cargando mapa…</div>,
});

export function MapaViewLoader(props: {
  puntos: PuntoPesca[];
  especies: Especie[];
  sedimentacion: [number, number][][];
  estaciones: EstacionSnapshot[];
}) {
  return <MapaView {...props} />;
}
