import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  // Next.js usa path alias @/* -> src/*. Espelhamos para os testes.
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
