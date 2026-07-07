'use client';

import { useState } from 'react';

interface PaperPreviewProps {
  markdown?: string;
  latexCode?: string;
  abstract?: string;
  keywords?: string[];
}

const MARKDOWN_STYLES = `
.pp-markdown-body { font-size: 0.88rem; line-height: 1.8; color: #CBD5E1; }
.pp-markdown-body h2 { font-size: 1.1rem; color: #F8FAFC; margin: 1.2rem 0 0.6rem; padding-bottom: 0.3rem; border-bottom: 1px solid #334155; }
.pp-markdown-body h3 { font-size: 1rem; color: #E2E8F0; margin: 1rem 0 0.5rem; }
.pp-markdown-body h4 { font-size: 0.92rem; color: #CBD5E1; margin: 0.8rem 0 0.4rem; }
.pp-markdown-body p { margin-bottom: 0.6rem; }
.pp-markdown-body strong { color: #F8FAFC; }
.pp-markdown-body em { color: #94A3B8; }
.pp-markdown-body pre { background: rgba(0,0,0,0.4); padding: 0.8rem; border-radius: 8px; overflow-x: auto; margin: 0.6rem 0; }
.pp-markdown-body code { font-family: 'Courier New', monospace; font-size: 0.82rem; }
.pp-markdown-body img { max-width: 100%; border-radius: 6px; margin: 0.6rem 0; }
.pp-markdown-body a { color: #3498db; text-decoration: none; }
.pp-markdown-body a:hover { text-decoration: underline; }
.pp-markdown-body li { margin-left: 1rem; margin-bottom: 0.3rem; color: #94A3B8; }
.pp-markdown-body table { width: 100%; border-collapse: collapse; margin: 0.6rem 0; font-size: 0.82rem; }
.pp-markdown-body td, .pp-markdown-body th { border: 1px solid #334155; padding: 0.4rem 0.6rem; }
.pp-markdown-body th { background: #1E293B; color: #F8FAFC; }
.pp-markdown-body td { color: #CBD5E1; }
`;

const RENDER_CLASSES = {
  codeBlock: 'bg-black/40 p-[0.8rem] rounded-[8px] overflow-x-auto mb-2.5',
  mathBlock: 'bg-black/20 p-[0.8rem] rounded-[8px] my-2.5 text-center text-[#CBD5E1] font-[Times_New_Roman,serif] text-[0.95rem] overflow-x-auto',
  mathInline: 'text-[#CBD5E1] font-[Times_New_Roman,serif]',
  inlineCode: 'bg-[#334155] py-[0.1rem] px-[0.4rem] rounded-[4px] text-[#e0c080] font-mono text-[0.82rem]',
  img: 'max-w-full rounded-[6px] my-2.5',
  link: 'text-[#3498db] no-underline hover:underline',
  li: 'ml-4 mb-[0.3rem] text-[#94A3B8]',
  tableWrapper: 'overflow-x-auto my-2.5',
  table: 'w-full border-collapse text-[0.82rem]',
  p: '',
};

export default function PaperPreview({ markdown, latexCode, abstract, keywords }: PaperPreviewProps) {
  const [view, setView] = useState<'markdown' | 'latex'>('markdown');

  const renderMarkdown = (text: string) => {
    const lines = text.split('\n');
    const out: string[] = [];
    let inCode = false;
    let codeBuffer: string[] = [];

    for (const line of lines) {
      if (line.startsWith('```')) {
        if (inCode) {
          out.push(`<pre class="${RENDER_CLASSES.codeBlock}"><code>${escapeHtml(codeBuffer.join('\n'))}</code></pre>`);
          codeBuffer = [];
          inCode = false;
        } else {
          inCode = true;
        }
        continue;
      }
      if (inCode) {
        codeBuffer.push(line);
        continue;
      }

      let html = escapeHtml(line);
      if (html.startsWith('## ')) { out.push(`<h2>${html.slice(3)}</h2>`); continue; }
      if (html.startsWith('### ')) { out.push(`<h3>${html.slice(4)}</h3>`); continue; }
      if (html.startsWith('#### ')) { out.push(`<h4>${html.slice(5)}</h4>`); continue; }
      html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
      html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, `<img alt="$1" src="$2" class="${RENDER_CLASSES.img}" />`);
      html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, `<a href="$2" class="${RENDER_CLASSES.link}" target="_blank" rel="noopener">$1</a>`);
      html = html.replace(/`([^`]+)`/g, `<code class="${RENDER_CLASSES.inlineCode}">$1</code>`);
      if (html.startsWith('$$') && html.endsWith('$$')) {
        out.push(`<div class="${RENDER_CLASSES.mathBlock}">${html}</div>`);
        continue;
      }
      if (html.startsWith('$') && html.endsWith('$') && html.length > 2) {
        out.push(`<span class="${RENDER_CLASSES.mathInline}">${html}</span>`);
        continue;
      }
      if (html.startsWith('- ')) {
        out.push(`<li class="${RENDER_CLASSES.li}">${html.slice(2)}</li>`);
        continue;
      }
      if (html.includes('|')) {
        out.push(`<div class="${RENDER_CLASSES.tableWrapper}"><table class="${RENDER_CLASSES.table}"><tbody><tr>${html.split('|').filter(Boolean).map(c => `<td>${c.trim()}</td>`).join('')}</tr></tbody></table></div>`);
        continue;
      }
      if (!html.trim()) { out.push('<br/>'); continue; }
      out.push(`<p>${html}</p>`);
    }
    return out.join('\n');
  };

  const escapeHtml = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  return (
    <div className="bg-[#1E293B] border border-[#334155] rounded-[14px] overflow-hidden flex flex-col max-h-[700px]">
      <style>{MARKDOWN_STYLES}</style>
      <div className="flex justify-between items-center py-[0.8rem] px-4 bg-black/20 border-b border-[#334155]">
        <span className="text-[0.95rem] text-[#F8FAFC] font-semibold">📄 论文预览</span>
        <div className="flex gap-[0.3rem]">
          <button
            className={`py-[0.3rem] px-[0.8rem] rounded-[6px] text-[0.875rem] cursor-pointer border border-[#334155] bg-[#1E293B] text-[#94A3B8] transition-all duration-200 hover:bg-[#334155] hover:text-[#CBD5E1] ${view === 'markdown' ? 'bg-[rgba(45,212,191,0.15)] border-[rgba(45,212,191,0.15)] text-[#3498db]' : ''}`}
            onClick={() => setView('markdown')}
          >Markdown</button>
          <button
            className={`py-[0.3rem] px-[0.8rem] rounded-[6px] text-[0.875rem] cursor-pointer border border-[#334155] bg-[#1E293B] text-[#94A3B8] transition-all duration-200 hover:bg-[#334155] hover:text-[#CBD5E1] ${view === 'latex' ? 'bg-[rgba(45,212,191,0.15)] border-[rgba(45,212,191,0.15)] text-[#3498db]' : ''}`}
            onClick={() => setView('latex')}
          >LaTeX</button>
        </div>
      </div>

      {view === 'markdown' && (
        <div className="flex-1 overflow-y-auto p-4 bg-black/15">
          {abstract && (
            <div className="bg-[rgba(45,212,191,0.15)] border border-[rgba(45,212,191,0.15)] rounded-[10px] p-4 mb-4">
              <div className="text-[0.9375rem] text-[#3498db] font-bold mb-2">摘要</div>
              <p className="text-[0.9375rem] text-[#CBD5E1] leading-[1.7]">{abstract}</p>
              {keywords && keywords.length > 0 && (
                <div className="mt-2 text-[0.875rem] text-[#94A3B8]">
                  <span className="text-[#94A3B8] font-semibold">关键词：</span>
                  {keywords.join(' · ')}
                </div>
              )}
            </div>
          )}
          {markdown ? (
            <div className="pp-markdown-body" dangerouslySetInnerHTML={{ __html: renderMarkdown(markdown) }} />
          ) : (
            <div className="text-center p-12 text-[#475569] text-[0.9375rem]">暂无论文内容</div>
          )}
        </div>
      )}

      {view === 'latex' && (
        <div className="flex-1 overflow-y-auto p-4 bg-black/15">
          {latexCode ? (
            <pre className="bg-black/40 p-4 rounded-[8px] text-[#a0e0a0] font-mono text-[0.78rem] leading-[1.5] overflow-x-auto whitespace-pre"><code>{latexCode}</code></pre>
          ) : (
            <div className="text-center p-12 text-[#475569] text-[0.9375rem]">暂无 LaTeX 代码</div>
          )}
        </div>
      )}
    </div>
  );
}
