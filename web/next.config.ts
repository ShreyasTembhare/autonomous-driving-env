import type { NextConfig } from "next";
import withStylex from "@stylexswc/nextjs-plugin/turbopack";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default withStylex({
  rsOptions: {
    aliases: { "@/*": ["./*"] },
    unstable_moduleResolution: { type: "commonJS" },
  },
})(nextConfig);
