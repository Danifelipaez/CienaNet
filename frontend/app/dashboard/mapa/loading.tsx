// Esqueleto de la vista Mapa: mismo layout (canvas + panel lateral) para que no
// haya salto cuando el mapa real y los puntos terminan de cargar.
function Bar({ w = "100%", h = 12, mt = 0 }: { w?: number | string; h?: number; mt?: number }) {
  return <div className="cr-skel" style={{ width: w, height: h, marginTop: mt }} />;
}

export default function Loading() {
  return (
    <div className="cr-mapa">
      <div className="cr-mapa-canvas">
        <div className="cr-skel" style={{ position: "absolute", inset: 0, borderRadius: 0 }} />
      </div>
      <aside className="cr-map-panel">
        <div className="cr-map-panel-head">
          <Bar w={150} h={20} />
        </div>
        <div className="cr-map-panel-body">
          {[0, 1, 2, 3, 4].map((i) => (
            <Bar key={i} w="100%" h={56} />
          ))}
        </div>
      </aside>
    </div>
  );
}
