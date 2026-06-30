import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'MathModel Agent',
  description:
    '多智能体协作论文生产系统 · LangGraph 编排 · ReAct 工具循环 · 自动迭代 · CCF-A 论文全自动生成',
};

async function fetchInitialInfo() {
  try {
    // SSR 阶段预取后端 /info，消除 SystemStatus loading 闪烁
    // cache: 'no-store' 确保每次请求都重新获取，不缓存失败响应
    const res = await fetch('http://localhost:8000/api/v1/info', {
      cache: 'no-store',
    });
    if (res.ok) return await res.json();
  } catch {
    // 后端未启动时静默失败，客户端会自行重试
  }
  return null;
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const initialInfo = await fetchInitialInfo();
  const initialInfoScript = initialInfo
    ? `window.__INITIAL_INFO__=${JSON.stringify(initialInfo)};`
    : '';

  return (
    <html lang="zh-CN">
      {/* 在 React 水合之前注入全局变量，保证 window.__API_BASE__ 在所有浏览器环境都正确 */}
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var o=window.location.origin.replace(/:(\\d+)$/,'');window.__API_BASE__=o+':8000/api/v1';${initialInfoScript}})()`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
