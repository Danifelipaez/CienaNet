import { Card, CardGrid } from "@/components/ui/card";

// Esqueleto de la vista Sistema: aparece al instante al navegar (Suspense) y se
// reemplaza en cuanto el Server Component termina de traer el estado real.
function Bar({ w = "100%", h = 12, mt = 0 }: { w?: number | string; h?: number; mt?: number }) {
  return <div className="cr-skel" style={{ width: w, height: h, marginTop: mt }} />;
}

export default function Loading() {
  return (
    <div className="cr-content-scroll">
      <header className="cr-page-head">
        <div>
          <Bar w={260} h={30} />
          <Bar w={320} h={13} mt={10} />
        </div>
        <Bar w={130} h={28} />
      </header>

      <CardGrid>
        {[0, 1, 2].map((i) => (
          <Card key={i} span={4} pad={20}>
            <Bar w={150} h={18} />
            <Bar w="80%" h={12} mt={8} />
            <Bar w={90} h={22} mt={16} />
          </Card>
        ))}

        <Card span={12} pad={20}>
          <Bar w={180} h={18} />
          <div style={{ display: "flex", gap: 28, marginTop: 18, flexWrap: "wrap" }}>
            {[0, 1, 2, 3].map((i) => (
              <Bar key={i} w={80} h={44} />
            ))}
          </div>
        </Card>

        <Card span={12} pad={20}>
          <Bar w={180} h={18} />
          <Bar w="100%" h={12} mt={16} />
          <Bar w="92%" h={12} mt={10} />
          <Bar w="96%" h={12} mt={10} />
        </Card>
      </CardGrid>
    </div>
  );
}
