import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
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
  // 生产镜像只需要 standalone 产物（自带精简的 node_modules），
  // 镜像从 1.16 GB 降到约 250 MB，也让 1 GB 内存的服务器有可能构建。
  output: "standalone",
};

export default nextConfig;