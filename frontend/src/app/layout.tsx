import type { Metadata } from 'next';
import './globals.css';
import { ClientLayout } from './client-layout';

export const metadata: Metadata = {
  title: 'LabAgent — 全自动科研论文生产系统',
  description:
    'LangGraph 编排 · ReAct 工具循环 · 实时协作讨论 · 自动迭代 · CCF-A 论文全自动生成',
};

async function fetchInitialInfo() {
  try {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
    const res = await fetch(`${apiUrl}/api/v1/info`, {
      cache: 'no-store',
    });
    if (res.ok) return await res.json();
  } catch {
    // 后端未启动时静默失败
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
    <html lang="zh-CN" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+SC:wght@300;400;500;600;700&display=swap" rel="stylesheet" />
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var o=window.location.origin.replace(/:(\\d+)$/,'');window.__API_BASE__=o+':8001/api/v1';${initialInfoScript}})()`,
          }}
        />
      </head>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <ClientLayout>{children}</ClientLayout>
      </body>
    </html>
  );
}
