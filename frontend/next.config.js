/** @type {import('next').NextConfig} */
const nextConfig = {
  // 关闭 trailingSlash：让 Next 不干预斜杠，完全透传给 route handler 代理。
  // 代理层（src/app/api/[...path]/route.ts）原样保留路径，并改写后端 3xx 的
  // Location 为同源相对路径，杜绝暴露 127.0.0.1:8001。
  trailingSlash: false,
  images: {
    unoptimized: true,
  },
  // 生产构建（start.sh 跑 next build）不因 ESLint 报错中断。
  // 原因：代码库积累了大量历史 exhaustive-deps 警告（FileManager/MemoryManager 等，
  // 均非 bug），且 react/no-unescaped-entities 这类规则对一个直角引号也判 Error，
  // 会把整个启动链卡死。ESLint 退为「npm run lint」单独检查；TypeScript 类型检查
  // 仍保留（真正能跑出 bug 的那一道），所以不会掩盖类型/编译错误。
  eslint: {
    ignoreDuringBuilds: true,
  },
};

module.exports = nextConfig;
