import path from "path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@maia/acp": path.resolve(__dirname, "../../vendor/maia-sdk/packages/acp-js/src/index.ts"),
      "@maia/computer-use": path.resolve(__dirname, "../../vendor/maia-sdk/packages/computer-use/src/index.ts"),
      "@maia/teamchat": path.resolve(__dirname, "../../vendor/maia-sdk/packages/teamchat/src/index.ts"),
      "@maia/theatre": path.resolve(__dirname, "../../vendor/maia-sdk/packages/theatre-react/src/index.ts"),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    clearMocks: true,
  },
});
