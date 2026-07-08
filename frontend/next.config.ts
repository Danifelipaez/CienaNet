import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Requerido para el build de Docker (servidor universitario) — genera
  // .next/standalone con un server.js autocontenido. No afecta a Vercel.
  output: "standalone",
};

export default nextConfig;
