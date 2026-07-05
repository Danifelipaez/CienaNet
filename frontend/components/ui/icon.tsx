import type { CSSProperties } from "react";

const ICON_PATHS: Record<string, string> = {
  home: "M3 10.5 12 3l9 7.5M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5",
  map: "M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Zm0 0v14m6-12v14",
  chart: "M4 20V4m0 16h16M8 16v-5m4 5V8m4 8v-3",
  bot: "M12 2v2m-5 4h10a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Zm2 5v2m6-2v2M9 17h6",
  system: "M3 12h4l2 6 4-14 2 8h6",
  settings:
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8-3a8 8 0 0 0-.2-1.8l2-1.5-2-3.4-2.3 1a8 8 0 0 0-3-1.8L14 1h-4l-.5 2.7a8 8 0 0 0-3 1.8l-2.3-1-2 3.4 2 1.5A8 8 0 0 0 4 12c0 .6 0 1.2.2 1.8l-2 1.5 2 3.4 2.3-1a8 8 0 0 0 3 1.8L10 23h4l.5-2.7a8 8 0 0 0 3-1.8l2.3 1 2-3.4-2-1.5c.1-.6.2-1.2.2-1.8Z",
  help: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm-2-12a2 2 0 1 1 3 1.7c-.7.5-1 .9-1 1.8m0 3h0",
  plus: "M12 5v14M5 12h14",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm10 2-4.3-4.3",
  calendar: "M7 3v3m10-3v3M4 8h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z",
  thermometer: "M10 13.5V5a2 2 0 1 1 4 0v8.5a4 4 0 1 1-4 0Z",
  leaf: "M5 21c0-9 5-15 16-16 0 11-7 16-16 16Zm0 0C9 14 13 11 18 9",
  wind: "M3 8h11a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h8a2.5 2.5 0 1 1-2.5 2.5",
  droplet: "M12 3s6 6.5 6 11a6 6 0 1 1-12 0c0-4.5 6-11 6-11Z",
  gauge: "M12 13l4-4M4.5 17a8 8 0 1 1 15 0M12 13a2 2 0 1 0 0-4",
  download: "M12 4v11m0 0 4-4m-4 4-4-4M5 19h14",
  layers: "M12 3 3 8l9 5 9-5-9-5Zm-9 9 9 5 9-5m-18 5 9 5 9-5",
  sliders: "M4 8h10m4 0h2M4 16h2m4 0h10M12 6v4m-4 4v4",
  target: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-5a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-3a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z",
  sprout: "M12 21v-7m0 0c0-3-2-5-6-5 0 4 2 6 6 6Zm0 0c0-4 2-6 6-6 0 4-3 6-6 6Z",
  chevron: "M9 6l6 6-6 6",
  x: "M6 6l12 12M18 6 6 18",
  book: "M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2V5Zm2 14h12M9 7h6",
  history: "M12 7v5l3 2M3 12a9 9 0 1 0 3-6.7L3 8m0-5v5h5",
  waves: "M2 8c2 0 2 2 4 2s2-2 4-2 2 2 4 2 2-2 4-2 2 2 4 2M2 14c2 0 2 2 4 2s2-2 4-2 2 2 4 2 2-2 4-2 2 2 4 2",
  fish: "M3 12c3-5 9-6 13-3 2-2 4-2 5-2-1 2-1 3 0 5-1 0-3 0-5-2-4 3-10 2-13-3Z",
  dot: "M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
  pin: "M12 22s7-6 7-12a7 7 0 1 0-14 0c0 6 7 12 7 12Zm0-9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  arrowRight: "M5 12h14m0 0-5-5m5 5-5 5",
  filter: "M3 5h18l-7 8v6l-4-2v-4L3 5Z",
  trash: "M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m2 0v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V7M10 11v6m4-6v6",
};

export function Icon({
  name,
  size = 18,
  stroke = 1.6,
  fill = false,
  style,
  className,
}: {
  name: string;
  size?: number;
  stroke?: number;
  fill?: boolean;
  style?: CSSProperties;
  className?: string;
}) {
  const d = ICON_PATHS[name] || ICON_PATHS.dot;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={fill ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={style}
      className={className}
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}
