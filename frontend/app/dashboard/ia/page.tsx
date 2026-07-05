import { IAView } from "@/components/ia/ia-view";

// El historial es por usuario y la identidad vive en localStorage (solo cliente),
// así que IAView carga su propio historial en el navegador — no hay fetch SSR aquí.
export default function IAPage() {
  return <IAView />;
}
