import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The /api rewrite proxies Server-Sent Events (live run stream). Next's gzip compression buffers those streams,
  // so browsers behind this proxy would never receive live events.
  compress: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
