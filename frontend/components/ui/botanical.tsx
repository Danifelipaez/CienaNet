import type { CSSProperties } from "react";

type BotanicalKind = "raya" | "mangle" | "cana" | "lirio";

export function Botanical({
  kind = "lirio",
  w = 120,
  h = 120,
  opacity = 0.07,
  color,
  style,
  className,
}: {
  kind?: BotanicalKind;
  w?: number;
  h?: number;
  opacity?: number;
  color?: string;
  style?: CSSProperties;
  className?: string;
}) {
  const c = color || "var(--verde)";
  const common = {
    fill: "none",
    stroke: c,
    strokeWidth: 1.1,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    vectorEffect: "non-scaling-stroke" as const,
  };
  let paths;
  if (kind === "raya") {
    paths = (
      <g {...common}>
        <path d="M60 30 C40 40 22 58 18 78 C30 74 44 72 60 74 C76 72 90 74 102 78 C98 58 80 40 60 30Z" />
        <path d="M60 74 C60 90 58 104 54 116 M60 74 C60 88 62 100 66 112" />
        <path d="M44 56 q16 -8 32 0" />
        <circle cx="50" cy="50" r="1.6" />
        <circle cx="70" cy="50" r="1.6" />
      </g>
    );
  } else if (kind === "mangle") {
    paths = (
      <g {...common}>
        <path d="M60 18 V70" />
        <path d="M60 36 C48 30 40 32 32 26 M60 44 C72 38 80 40 88 34" />
        <path d="M60 56 C46 52 36 56 26 50 M60 62 C74 58 84 62 94 56" />
        <path d="M48 70 C40 84 34 96 30 108 M60 70 V108 M72 70 C80 84 86 96 90 108" />
        <path d="M38 108 q-6 6 0 8 M60 108 q-5 6 0 8 M82 108 q6 6 0 8" />
      </g>
    );
  } else if (kind === "cana") {
    paths = (
      <g {...common}>
        <path d="M44 110 C44 70 48 40 52 16 M60 110 C60 66 60 38 60 14 M76 110 C76 72 72 44 68 18" />
        <path d="M52 16 q-10 -6 -16 -2 q8 4 16 2 M52 22 q12 -6 18 -1 q-8 5 -18 1" />
        <path d="M60 14 q-12 -7 -19 -2 q9 5 19 2 M68 18 q12 -5 18 0 q-8 4 -18 0" />
      </g>
    );
  } else {
    paths = (
      <g {...common}>
        <path d="M60 60 C60 44 52 32 60 22 C68 32 60 44 60 60Z" />
        <path d="M60 60 C46 54 34 56 28 44 C42 42 54 50 60 60Z" />
        <path d="M60 60 C74 54 86 56 92 44 C78 42 66 50 60 60Z" />
        <path d="M60 60 C50 70 40 74 42 86 C54 80 58 70 60 60Z" />
        <path d="M60 60 C70 70 80 74 78 86 C66 80 62 70 60 60Z" />
        <circle cx="60" cy="60" r="3" />
        <path d="M18 96 q14 -6 28 0 t28 0 t28 0" />
      </g>
    );
  }
  return (
    <svg
      className={"cr-botanical" + (className ? " " + className : "")}
      viewBox="0 0 120 120"
      width={w}
      height={h}
      style={{ opacity, pointerEvents: "none", ...style }}
      aria-hidden="true"
    >
      {paths}
    </svg>
  );
}

export function SealLogo({ size = 44 }: { size?: number }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: "var(--sedimento-soft)",
        border: "1.5px solid var(--sedimento)",
        display: "grid",
        placeItems: "center",
        flexShrink: 0,
        position: "relative",
        overflow: "hidden",
      }}
    >
      <Botanical kind="raya" w={size * 0.78} h={size * 0.78} opacity={0.85} color="var(--verde)" />
    </div>
  );
}
