import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '数学建模论文自动生成系统',
  description: 'Multi-Agent团队协作 · 实时讨论 · 数据驱动',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      {/* 在 React 水合之前注入全局变量，保证 window.__API_BASE__ 在所有浏览器环境都正确 */}
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var o=window.location.origin.replace(/:(\\d+)$/,'');window.__API_BASE__=o+':8000/api/v1'})()`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
