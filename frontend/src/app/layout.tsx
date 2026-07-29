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
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        {/* 防 SSR 闪烁：在 React hydrate 前同步设定主题 class，默认浅色。
            系统字体栈在 globals.css --font-sans 定义，无需 CDN 加载。 */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){
              try {
                var t = localStorage.getItem('theme');
                if (t !== 'dark' && t !== 'light') t = 'light';
                document.documentElement.classList.add(t);
              } catch (e) {
                document.documentElement.classList.add('light');
              }
              window.__API_BASE__='/api/v1';${initialInfoScript}
            })()`,
          }}
        />
      </head>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <ClientLayout>{children}</ClientLayout>
      </body>
    </html>
  );
}
