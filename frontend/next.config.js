/** @type {import('next').NextConfig} */
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

const nextConfig = {
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  // 同源代理：浏览器只请求 3002（同源，不走系统代理/不触发CORS），
  // 由 Next dev server（Node 进程，本机直连）转发到后端 8001。
  // 解决：Windows 浏览器经 Clash 代理劫持 localhost:8001 → 502。
  //
  // 关键：FastAPI 对 /tasks（无斜杠）会 307 补斜杠，且 Location 用绝对 host
  // (localhost:8001) → 浏览器跟随时又被 Clash 劫持。故此处两条规则把
  // 带尾斜杠和不带尾斜杠的请求都映射到「带尾斜杠」的后端路径，规避 307。
  async rewrites() {
    return [
      // 带尾斜杠：原样转发（保持尾斜杠）
      { source: '/api/:path*/', destination: `${BACKEND_URL}/api/:path*/` },
      // 不带尾斜杠：补尾斜杠后转发，避免后端 307
      { source: '/api/:path*', destination: `${BACKEND_URL}/api/:path*/` },
    ];
  },
};

module.exports = nextConfig;
