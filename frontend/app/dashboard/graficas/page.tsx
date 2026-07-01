import { GraficasView } from "@/components/charts/graficas-view";
import { BackendError } from "@/components/ui/backend-error";
import { getHistory } from "@/lib/api";

export default async function GraficasPage() {
  try {
    const history = await getHistory(30);
    return <GraficasView initialHistory={history} />;
  } catch {
    return <BackendError title="Gráficas e históricos" />;
  }
}
