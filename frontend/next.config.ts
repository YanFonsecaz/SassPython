import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // output: "export" só em produção (gera HTML estático para o FastAPI servir).
  // Em dev, omitir para que next dev suporte rotas dinâmicas ([id], [auditoriaId]).
  ...(process.env.NODE_ENV === "production" && { output: "export" }),
  images: {
    unoptimized: true,
  },
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
