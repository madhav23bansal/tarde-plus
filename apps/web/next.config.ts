import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: ".",  // Watch only this app, not the monorepo root
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
