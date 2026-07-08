import { Card, CardGrid } from "@/components/ui/card";

// Esqueleto de la vista Gráficas: se muestra al instante mientras el Server
// Component trae el histórico (getHistory) y renderiza los charts reales.
function Bar({ w = "100%", h = 12, mt = 0 }: { w?: number | string; h?: number; mt?: number }) {
  return <div className="cr-skel" style={{ width: w, height: h, marginTop: mt }} />;
}

export default function Loading() {
  return (
    <div className="cr-content-scroll">
      <header className="cr-page-head">
        <div>
          <Bar w={300} h={30} />
          <Bar w={240} h={13} mt={10} />
        </div>
        <Bar w={170} h={34} />
      </header>

      <CardGrid>
        {[0, 1].map((i) => (
          <Card key={i} span={6} pad={20}>
            <Bar w={160} h={16} />
            <div className="cr-skel" style={{ height: 180, marginTop: 16 }} />
          </Card>
        ))}
        <Card span={12} pad={20}>
          <Bar w={200} h={16} />
          <div className="cr-skel" style={{ height: 200, marginTop: 16 }} />
        </Card>
      </CardGrid>
    </div>
  );
}
