"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { Botanical, SealLogo } from "@/components/ui/botanical";
import { StatusDot } from "@/components/ui/primitives";
import type { ApiStatus } from "@/lib/api";

const NAV = [
  { id: "mapa", icon: "map", label: "Mapa" },
  { id: "graficas", icon: "chart", label: "Gráficas" },
  { id: "ia", icon: "bot", label: "Pregunta IA" },
  { id: "sistema", icon: "system", label: "Sistema" },
] as const;

const VIEW_TITLE: Record<string, string> = {
  mapa: "Mapa interactivo",
  graficas: "Gráficas e históricos",
  ia: "Pregunta a la IA",
  sistema: "Estado del sistema",
};

function apiTone(estado: ApiStatus["estado"]) {
  return estado === "ok" ? "verde" : estado === "degradado" ? "amarillo" : "rojo";
}

function toggleTheme() {
  const root = document.documentElement;
  const isDark = root.getAttribute("data-palette") === "nocturno";
  if (isDark) {
    root.removeAttribute("data-palette");
    localStorage.removeItem("cr-palette");
  } else {
    root.setAttribute("data-palette", "nocturno");
    localStorage.setItem("cr-palette", "nocturno");
  }
}

export function DashboardShell({
  apis,
  children,
}: {
  apis: ApiStatus[];
  children: React.ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const view = pathname.split("/")[2] || "mapa";

  useEffect(() => setMobileOpen(false), [pathname]);

  return (
    <div className="cr-app">
      {mobileOpen && <div className="cr-sidebar-overlay" onClick={() => setMobileOpen(false)} />}
      <nav className={"cr-sidebar" + (collapsed ? " collapsed" : "") + (mobileOpen ? " mobile-open" : "")}>
        <div className="cr-sb-top">
          <SealLogo size={collapsed ? 40 : 42} />
          <div className="cr-sb-titlewrap">
            <div className="cr-sb-title">CienRayas</div>
            <div className="cr-sb-sub">Ciénaga Grande · Santa Marta</div>
          </div>
        </div>
        <button className="cr-newbtn" onClick={() => router.push("/dashboard/ia")}>
          <Icon name="plus" size={15} />
          <span className="cr-label">Nueva consulta</span>
        </button>
        <div className="cr-nav">
          {NAV.map((n) => (
            <Link key={n.id} href={`/dashboard/${n.id}`} className={"cr-nav-item" + (view === n.id ? " active" : "")} title={n.label}>
              <Icon name={n.icon} size={19} />
              <span className="cr-label">{n.label}</span>
            </Link>
          ))}
        </div>
        <div className="cr-sb-bottom">
          <Botanical kind="raya" w={150} h={150} opacity={0.05} className="cr-sb-watermark" style={{ position: "absolute", right: -10, bottom: 36 }} />
          <button className="cr-nav-item cr-theme-toggle" onClick={toggleTheme}>
            <Icon name="moon" size={19} />
            <span className="cr-label">Modo noche</span>
          </button>
          <button className="cr-nav-item">
            <Icon name="settings" size={19} />
            <span className="cr-label">Ajustes</span>
          </button>
          <button className="cr-nav-item">
            <Icon name="help" size={19} />
            <span className="cr-label">Soporte</span>
          </button>
        </div>
      </nav>

      <div className="cr-main">
        <header className="cr-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button className="cr-hamburger" onClick={() => setMobileOpen((o) => !o)} aria-label="Abrir menú">
              <Icon name="menu" size={18} />
            </button>
            <button className="cr-collapse" onClick={() => setCollapsed((c) => !c)} aria-label="Plegar menú">
              <Icon name="sliders" size={18} />
            </button>
            <div className="cr-bread">
              CienRayas <Icon name="chevron" size={13} style={{ opacity: 0.4 }} /> <b>{VIEW_TITLE[view]}</b>
            </div>
          </div>
          <div className="cr-sys">
            {apis.map((a) => (
              <span key={a.id} className="cr-sys-item" title={`${a.nombre} · ${a.actualizado}`}>
                <StatusDot tone={apiTone(a.estado)} size={8} pulse={a.estado !== "ok"} />
                {a.nombre}
              </span>
            ))}
          </div>
        </header>

        <div className="cr-view">{children}</div>
      </div>
    </div>
  );
}
