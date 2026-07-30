'use client';

import { useState } from 'react';
import type { Paper } from '../store/useAppStore';

interface PaperListProps {
  papers: Paper[];
  source?: string;
}

export default function PaperList({ papers, source }: PaperListProps) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  if (!papers || papers.length === 0) {
    return (
      <div data-design-id="report:card-papers" className="bg-card border border-border rounded-xl overflow-hidden flex flex-col mb-4 mx-auto w-full max-w-[1320px]">
        <div className="flex justify-between items-center py-3 px-6 bg-muted/50 border-b border-border">
          <span data-design-id="report:title-papers" className="text-lg text-foreground font-semibold">📚 相关文献</span>
        </div>
        <div className="text-center px-10 py-8 text-muted-foreground text-sm">未检索到相关文献</div>
      </div>
    );
  }

  const toggleAbstract = (idx: number) => {
    const next = new Set(expanded);
    if (next.has(idx)) next.delete(idx);
    else next.add(idx);
    setExpanded(next);
  };

  const sourceLabel = source ? `（来自 ${source}）` : '';

  return (
    <div data-design-id="report:card-papers" className="bg-card border border-border rounded-xl overflow-hidden flex flex-col mb-4 mx-auto w-full max-w-[1320px]">
      <div className="flex justify-between items-center py-3 px-6 bg-muted/50 border-b border-border">
        <span data-design-id="report:title-papers" className="text-lg text-foreground font-semibold">
          📚 相关文献（{papers.length} 篇）{sourceLabel}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-3 flex flex-col gap-2.5">
        {papers.map((paper, idx) => (
          <div key={`${paper.arxiv_id}-${idx}`} className="bg-muted/40 rounded-lg py-3 px-6 border border-border transition-colors duration-200 hover:border-primary/30">
            <div className="flex justify-between items-start gap-3 mb-1.5">
              <a
                href={paper.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-semibold text-primary no-underline leading-snug flex-1 hover:underline"
                title={paper.title}
              >
                {paper.title}
              </a>
              <span className="text-xs text-muted-foreground bg-muted py-0.5 px-2 rounded whitespace-nowrap">{paper.year || '—'}</span>
            </div>
            <div className="text-sm text-muted-foreground mb-1.5 leading-snug">
              {paper.authors && paper.authors.length > 0
                ? `${paper.authors.slice(0, 5).join(', ')}${
                    paper.authors.length > 5 ? ` et al. (${paper.authors.length} 位作者)` : ''
                  }`
                : '作者未知'}
            </div>
            <div className="flex gap-3 items-center flex-wrap mb-1.5">
              <span className="text-sm text-muted-foreground bg-muted py-0.5 px-1.5 rounded">arXiv:{paper.arxiv_id}</span>
              {paper.relevance_score !== undefined && paper.relevance_score !== null && (
                <span className="text-sm text-warning bg-warning/10 py-0.5 px-1.5 rounded" title="相关性评分">
                  相关度 {paper.relevance_score}
                </span>
              )}
              {paper.citation_count !== undefined && paper.citation_count !== null && (
                <span className="text-sm text-muted-foreground bg-muted py-0.5 px-1.5 rounded" title="被引次数">
                  被引 {paper.citation_count} 次
                </span>
              )}
              {paper.venue && (
                <span className="text-sm text-muted-foreground bg-muted py-0.5 px-1.5 rounded max-w-[220px] overflow-hidden text-ellipsis whitespace-nowrap" title={paper.venue}>
                  {paper.venue.length > 30 ? paper.venue.slice(0, 30) + '...' : paper.venue}
                </span>
              )}
              {paper.doi && (
                <a
                  href={`https://doi.org/${paper.doi}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-primary no-underline py-0.5 px-3.5 border border-border rounded hover:bg-muted"
                >
                  DOI
                </a>
              )}
              {paper.categories?.slice(0, 3).map((cat) => (
                <span key={cat} className="text-sm text-success bg-success/10 py-0.5 px-1.5 rounded">
                  {cat}
                </span>
              ))}
              {paper.pdf_url ? (
                <a
                  href={paper.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-error no-underline ml-auto py-0.5 px-3.5 border border-error/30 rounded hover:bg-error/10"
                >
                  PDF
                </a>
              ) : null}
            </div>
            {paper.fields_of_study && paper.fields_of_study.length > 0 && (
              <div className="flex gap-3 flex-wrap mb-1.5">
                {paper.fields_of_study.slice(0, 4).map((field) => (
                  <span key={field} className="text-xs text-muted-foreground bg-muted py-0.5 px-1 rounded">
                    {field}
                  </span>
                ))}
              </div>
            )}
            {paper.tldr && (
              <div className="text-sm text-muted-foreground mb-2 py-1.5 px-5 bg-muted rounded-md border-l-2 border-l-primary/30 leading-relaxed">
                <span className="text-primary font-semibold mr-1.5">TL;DR:</span> {paper.tldr}
              </div>
            )}
            {paper.extraction && (
              <div className="text-sm text-muted-foreground mb-2 py-2 px-5 bg-success/10 rounded-md border-l-2 border-l-success/30 leading-relaxed">
                {paper.extraction.methods && <div className="mb-1"><strong className="text-success mr-1.5">方法：</strong> {paper.extraction.methods}</div>}
                {paper.extraction.conclusion && <div className="mb-1"><strong className="text-success mr-1.5">结论：</strong> {paper.extraction.conclusion}</div>}
                {paper.extraction.datasets && paper.extraction.datasets.length > 0 && <div className="mb-1"><strong className="text-success mr-1.5">数据集：</strong> {paper.extraction.datasets.join(', ')}</div>}
                {paper.extraction.limitations && <div className="mb-1"><strong className="text-success mr-1.5">局限：</strong> {paper.extraction.limitations}</div>}
              </div>
            )}
            <button
              type="button"
              data-design-id="report:btn-abstract"
              className="text-xs text-muted-foreground bg-transparent border-none cursor-pointer py-1 px-2 text-left hover:text-foreground"
              onClick={() => toggleAbstract(idx)}
            >
              {expanded.has(idx) ? '收起摘要 ▲' : '查看摘要 ▼'}
            </button>
            {expanded.has(idx) && (
              <div className="text-sm text-muted-foreground leading-relaxed mt-1.5 pt-1.5 border-t border-border max-h-[200px] overflow-y-auto">{paper.abstract}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
