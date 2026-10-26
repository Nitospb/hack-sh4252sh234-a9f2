import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  images: {
    remotePatterns: [
      new URL("https://alfabank.servicecdn.ru/site-upload/1c/74/21424/d-mb-250925.png"),
      new URL("https://alfabank.servicecdn.ru/site-upload/8c/66/7344/D01_MB_KV_564x450.png"),
      new URL("https://alfabank.servicecdn.ru/site-upload/16/f0/21424/cardpure-3.png"),
      new URL("https://alfabank.servicecdn.ru/site-upload/0e/d4/6088/MB_KV_328x192_D6E8FC.png"),
    ],
  },
  async redirects() {
    return [
      { source: "/index.html", destination: "/", permanent: true },
      ...[
        "feed",
        "event",
        "chat",
        "profile",
        "sources",
        "trace",
        "settings",
        "clients",
        "quality",
        "architecture",
      ].map((page) => ({
        source: `/${page}.html`,
        destination: `/${page}`,
        permanent: true,
      })),
    ];
  },
  experimental: {
    agentFeedback: true,
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
