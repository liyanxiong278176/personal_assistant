import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Build output directory
  distDir: 'out',
  webpack: (config) => {
    config.externals.push({ 'utf-8-validate': 'commonjs utf-8-validate' });
    return config;
  },
  // API proxy to backend (for development only)
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ];
  },
};

export default nextConfig;
