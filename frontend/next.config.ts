import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  webpack: (config) => {
    config.externals.push({ 'utf-8-validate': 'commonjs utf-8-validate' });
    return config;
  },
};

export default nextConfig;
