import { DashboardShell } from "@/components/dashboard-shell";
import { backendFetchAdmin, READ_REVALIDATE, type ApiStatus, type SystemStatusResponse } from "@/lib/api";

// Todo /dashboard/* depende de datos en vivo del backend (puntos, semáforo, IA,
// estado del sistema) — nunca debe congelarse como HTML estático en build time,
// sobre todo si el backend no estaba levantado durante `next build`.
export const dynamic = "force-dynamic";

async function getApiStatuses(): Promise<ApiStatus[]> {
  try {
    const data = await backendFetchAdmin<SystemStatusResponse>("/dashboard/system-status", undefined, READ_REVALIDATE);
    return data.apis;
  } catch {
    // El header muestra las pills de estado como cortesía; si el backend admin
    // no está disponible, el resto del dashboard (vistas públicas) sigue funcionando.
    return [];
  }
}

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const apis = await getApiStatuses();
  return <DashboardShell apis={apis}>{children}</DashboardShell>;
}
