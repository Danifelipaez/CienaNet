import { Icon } from "@/components/ui/icon";
import { Card, CardGrid } from "@/components/ui/card";
import { MonoChip, Pill, StatusDot } from "@/components/ui/primitives";
import { BackendError } from "@/components/ui/backend-error";
import { backendFetchAdmin, type ApiStatus, type SystemStatusResponse } from "@/lib/api";

function estTone(e: ApiStatus["estado"]) {
  return e === "ok" ? "verde" : e === "degradado" ? "amarillo" : "rojo";
}
function estLabel(e: ApiStatus["estado"]) {
  return e === "ok" ? "Operativo" : e === "degradado" ? "Degradado" : "Caído";
}

async function getSystemStatus(): Promise<SystemStatusResponse | null> {
  try {
    return await backendFetchAdmin<SystemStatusResponse>("/dashboard/system-status");
  } catch {
    return null;
  }
}

export default async function SistemaPage() {
  const status = await getSystemStatus();

  if (!status) {
    return <BackendError title="Estado del sistema" />;
  }

  return (
    <div className="cr-content-scroll">
      <header className="cr-page-head">
        <div>
          <h1 className="serif cr-page-title">Estado del sistema</h1>
          <p className="mono cr-page-sub">Fuentes conectadas · bot comunitario · alertas</p>
        </div>
        <Pill tone="verde" dot>
          Sistema operativo
        </Pill>
      </header>

      <CardGrid>
        {status.apis.map((a) => (
          <Card
            key={a.id}
            span={4}
            pad={20}
            accent={a.estado === "ok" ? "var(--verde-sem)" : a.estado === "degradado" ? "var(--amarillo)" : "var(--rojo)"}
          >
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
              <div>
                <h3 className="serif" style={{ margin: 0, fontSize: 19, fontWeight: 600, color: "var(--verde)" }}>
                  {a.nombre}
                </h3>
                <p style={{ margin: "3px 0 0", fontSize: 12.5, color: "var(--ink-soft)" }}>{a.desc}</p>
              </div>
              <StatusDot tone={estTone(a.estado)} size={11} pulse={a.estado !== "ok"} />
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
              <Pill tone={estTone(a.estado)}>{estLabel(a.estado)}</Pill>
            </div>
            <div className="mono" style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 10, display: "flex", alignItems: "center", gap: 6 }}>
              <Icon name="history" size={12} /> Actualizado {a.actualizado}
            </div>
          </Card>
        ))}

        <Card title="Métricas del bot" label="Comunidad · WhatsApp" span={12} icon="bot" motif="cana">
          <div className="cr-metric-grid">
            {status.bot_metricas.map((m) => (
              <div key={m.id} className="cr-metric">
                <span className="mono" style={{ fontSize: 11, color: "var(--ink-faint)", textTransform: "uppercase", letterSpacing: ".08em" }}>
                  {m.label}
                </span>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, margin: "6px 0 2px" }}>
                  <span className="serif" style={{ fontSize: 34, fontWeight: 600, color: "var(--ink)", lineHeight: 1 }}>
                    {m.valor}
                  </span>
                </div>
                <span style={{ fontSize: 11.5, color: "var(--ink-soft)" }}>{m.sub}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Alertas recientes" label="Enviadas a WhatsApp" span={12} icon="system">
          <div className="cr-alert-log">
            {status.log_alertas.map((al, i) => (
              <div key={i} className="cr-alert-row">
                <div className="cr-alert-time mono">{al.hora}</div>
                <span style={{ marginTop: 3 }}>
                  <StatusDot tone={al.tipo === "red" || al.tipo === "rojo" ? "rojo" : al.tipo === "yellow" || al.tipo === "amarillo" ? "amarillo" : "verde"} pulse={al.tipo === "red" || al.tipo === "rojo"} />
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 13, color: "var(--ink)", fontWeight: 600 }}>{al.zonas}</span>
                    <MonoChip>{al.canal}</MonoChip>
                  </div>
                  <p style={{ margin: "3px 0 0", fontSize: 12.5, lineHeight: 1.45, color: "var(--ink-soft)" }}>{al.texto}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </CardGrid>
    </div>
  );
}
