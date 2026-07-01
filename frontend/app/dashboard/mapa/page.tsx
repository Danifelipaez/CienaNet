import { MapaViewLoader } from "@/components/map/mapa-view-loader";
import { BackendError } from "@/components/ui/backend-error";
import { getPoints, getSpecies, getSedimentation } from "@/lib/api";

export default async function MapaPage() {
  try {
    const [puntos, especies, zonas] = await Promise.all([getPoints(), getSpecies(), getSedimentation()]);
    const sedimentacion = zonas.map((z) => z.polygon);
    return <MapaViewLoader puntos={puntos} especies={especies} sedimentacion={sedimentacion} />;
  } catch {
    return <BackendError title="Mapa interactivo" />;
  }
}
