import type { CSSProperties, MouseEventHandler, ReactNode } from "react";
import { Icon } from "./icon";
import { Botanical } from "./botanical";
import { SectionLabel } from "./primitives";

export function CardGrid({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div className="cr-grid" style={style}>
      {children}
    </div>
  );
}

export function Card({
  title,
  label,
  icon,
  span = 6,
  accent,
  motif,
  actions,
  pad = 20,
  children,
  style,
  bodyStyle,
  onClick,
  className,
}: {
  title?: ReactNode;
  label?: ReactNode;
  icon?: string;
  span?: number;
  accent?: boolean | string;
  motif?: "raya" | "mangle" | "cana" | "lirio";
  actions?: ReactNode;
  pad?: number;
  children?: ReactNode;
  style?: CSSProperties;
  bodyStyle?: CSSProperties;
  onClick?: MouseEventHandler;
  className?: string;
}) {
  const accentBar = accent ? (
    <span
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        bottom: 0,
        width: 4,
        background: accent === true ? "var(--verde)" : accent,
        borderRadius: "12px 0 0 12px",
      }}
    />
  ) : null;
  return (
    <section
      onClick={onClick}
      className={`cr-card s${span} ` + (className || "")}
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        boxShadow: "var(--shadow)",
        position: "relative",
        overflow: "hidden",
        padding: pad,
        cursor: onClick ? "pointer" : "default",
        ...style,
      }}
    >
      {accentBar}
      {motif && (
        <Botanical
          kind={motif}
          w={130}
          h={130}
          opacity={0.06}
          style={{ position: "absolute", right: -18, bottom: -22 }}
        />
      )}
      {(title || label || actions) && (
        <header
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 12,
            marginBottom: title || label ? 14 : 0,
            position: "relative",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
            {icon && (
              <span style={{ color: "var(--verde)", display: "flex" }}>
                <Icon name={icon} size={18} />
              </span>
            )}
            <div style={{ minWidth: 0 }}>
              {label && <SectionLabel style={{ marginBottom: title ? 2 : 0 }}>{label}</SectionLabel>}
              {title && (
                <h3
                  className="serif"
                  style={{
                    margin: 0,
                    fontSize: 21,
                    fontWeight: 600,
                    color: "var(--verde)",
                    lineHeight: 1.1,
                    letterSpacing: "-.01em",
                  }}
                >
                  {title}
                </h3>
              )}
            </div>
          </div>
          {actions && <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>{actions}</div>}
        </header>
      )}
      <div style={{ position: "relative", ...bodyStyle }}>{children}</div>
    </section>
  );
}
