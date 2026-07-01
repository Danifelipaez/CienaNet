import { Pill } from "./primitives";

export function BackendError({ title }: { title: string }) {
  return (
    <div className="cr-content-scroll">
      <header className="cr-page-head">
        <div>
          <h1 className="serif cr-page-title">{title}</h1>
        </div>
        <Pill tone="rojo" dot>
          No se pudo contactar al backend
        </Pill>
      </header>
    </div>
  );
}
