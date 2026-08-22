import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const api = process.env.API_INTERNAL_URL ?? "http://localhost:8000/api/v1";
    return [{ source: "/api/v1/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;
