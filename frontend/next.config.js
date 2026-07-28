/** @type {import('next').NextConfig} */
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

const nextConfig = {
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  // 同源代理：浏览器只请求 3002（同源，不走系统代理/不触发CORS），
  // 由 Next dev server（Node 进程，本机直连）转发到后端 8001。
  // 解决：Windows 浏览器经 Clash 代理劫持 localhost:8001 → 502 的问题。
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
