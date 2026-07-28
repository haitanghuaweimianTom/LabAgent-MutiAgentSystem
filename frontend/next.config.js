/** @type {import('next').NextConfig} */
const nextConfig = {
  // 关闭 trailingSlash：让 Next 不干预斜杠，完全透传给 route handler 代理。
  // 代理层（src/app/api/[...path]/route.ts）原样保留路径，并改写后端 3xx 的
  // Location 为同源相对路径，杜绝暴露 127.0.0.1:8001。
  trailingSlash: false,
  images: {
    unoptimized: true,
  },
};

module.exports = nextConfig;
