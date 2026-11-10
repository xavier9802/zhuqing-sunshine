import type { NextConfig } from "next";

// Repo Pages: xavier9802.github.io/zhuqing-sunshine/; omit for local root hosting.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  basePath,
  poweredByHeader: false,
  reactStrictMode: true,
};
export default nextConfig;
