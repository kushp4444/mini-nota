import { defineConfig } from "@playwright/test";
import baseConfig from "./playwright.config";

const port = 3307;
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig(baseConfig, {
  grep: /@smoke/,
  use: { baseURL },
  webServer: {
    command: `npm run start -- --hostname 127.0.0.1 --port ${port}`,
    url: baseURL,
  },
});
