import type { NextConfig } from "next";

const config: NextConfig = {
  devIndicators: false,
  async headers() {
    return [{
      source: "/examples/files/:file",
      headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
    }];
  },
};

export default config;
