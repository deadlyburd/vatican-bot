import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  trailingSlash: true,
  images: {
    unoptimized: true
  },
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: 'http://backend:8000/api/v1/:path*/',
      },
      {
        source: '/static/:path*',
        destination: 'http://backend:8000/static/:path*',
      },
      {
        source: '/pay/:path*',
        destination: 'http://backend:8000/pay/:path*',
      },
    ];
  },
};

export default nextConfig;
