'use client';

import { useState } from 'react';
import styles from './PaperPreview.module.css';

interface PaperPreviewProps {
  markdown?: string;
  latexCode?: string;
  abstract?: string;
  keywords?: string[];
}

export default function PaperPreview({ markdown, latexCode, abstract, keywords }: PaperPreviewProps) {
  const [view, setView] = useState<'markdown' | 'latex'>('markdown');

  const renderMarkdown = (text: string) => {
    // Very simple markdown-to-HTML renderer for preview
    const lines = text.split('\n');
    const out: string[] = [];
    let inCode = false;
    let codeLang = '';
    let codeBuffer: string[] = [];

    for (const line of lines) {
      if (line.startsWith('```')) {
        if (inCode) {
          out.push(`<pre class="${styles.codeBlock}"><code>${escapeHtml(codeBuffer.join('\n'))}</code></pre>`);
          codeBuffer = [];
          inCode = false;
        } else {
          inCode = true;
          codeLang = line.slice(3).trim();
        }
        continue;
      }
      if (inCode) {
        codeBuffer.push(line);
        continue;
      }

      let html = escapeHtml(line);
      // Headers
      if (html.startsWith('## ')) { out.push(`<h2 class="${styles.h2}">${html.slice(3)}</h2>`); continue; }
      if (html.startsWith('### ')) { out.push(`<h3 class="${styles.h3}">${html.slice(4)}</h3>`); continue; }
      if (html.startsWith('#### ')) { out.push(`<h4 class="${styles.h4}">${html.slice(5)}</h4>`); continue; }
      // Bold
      html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      // Italic
      html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
      // Images
      html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img alt="$1" src="$2" class="' + styles.img + '" />');
      // Links
      html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="' + styles.link + '" target="_blank" rel="noopener">$1</a>');
      // Inline code
      html = html.replace(/`([^`]+)`/g, '<code class="' + styles.inlineCode + '">$1</code>');
      // Block math (simple passthrough)
      if (html.startsWith('$$') && html.endsWith('$$')) {
        out.push(`<div class="${styles.mathBlock}">${html}</div>`);
        continue;
      }
      if (html.startsWith('$') && html.endsWith('$') && html.length > 2) {
        out.push(`<span class="${styles.mathInline}">${html}</span>`);
        continue;
      }
      // Lists
      if (html.startsWith('- ')) {
        out.push(`<li class="${styles.li}">${html.slice(2)}</li>`);
        continue;
      }
      // Tables (simple)
      if (html.includes('|')) {
        out.push(`<div class="${styles.tableWrapper}"><table class="${styles.table}"><tbody><tr>${html.split('|').filter(Boolean).map(c => `<td>${c.trim()}</td>`).join('')}</tr></tbody></table></div>`);
        continue;
      }
      // Empty line
      if (!html.trim()) { out.push('<br/>'); continue; }
      out.push(`<p class="${styles.p}">${html}</p>`);
    }
    return out.join('\n');
  };

  const escapeHtml = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.title}>📄 论文预览</span>
        <div className={styles.tabs}>
          <button className={`${styles.tab} ${view === 'markdown' ? styles.tabActive : ''}`} onClick={() => setView('markdown')}>Markdown</button>
          <button className={`${styles.tab} ${view === 'latex' ? styles.tabActive : ''}`} onClick={() => setView('latex')}>LaTeX</button>
        </div>
      </div>

      {view === 'markdown' && (
        <div className={styles.content}>
          {abstract && (
            <div className={styles.abstractBox}>
              <div className={styles.abstractTitle}>摘要</div>
              <p className={styles.abstractText}>{abstract}</p>
              {keywords && keywords.length > 0 && (
                <div className={styles.keywords}>
                  <span className={styles.keywordsLabel}>关键词：</span>
                  {keywords.join(' · ')}
                </div>
              )}
            </div>
          )}
          {markdown ? (
            <div className={styles.markdownBody} dangerouslySetInnerHTML={{ __html: renderMarkdown(markdown) }} />
          ) : (
            <div className={styles.empty}>暂无论文内容</div>
          )}
        </div>
      )}

      {view === 'latex' && (
        <div className={styles.content}>
          {latexCode ? (
            <pre className={styles.latexCode}><code>{latexCode}</code></pre>
          ) : (
            <div className={styles.empty}>暂无 LaTeX 代码</div>
          )}
        </div>
      )}
    </div>
  );
}
