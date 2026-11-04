import { resolve } from "node:path";

import { defineConfig } from "vitest/config";

// Mirror the tsconfig "@/*" path alias so unit tests resolve the same imports as the app.
export default defineConfig({
  resolve: { alias: { "@": resolve(__dirname, ".") } },
  test: { include: ["lib/**/*.spec.ts"], environment: "node" },
});
