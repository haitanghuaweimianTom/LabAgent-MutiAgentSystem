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
      <div className="bg-[#1E293B] border border-[#334155] rounded-[14px] overflow-hidden flex flex-col mb-4">
        <div className="flex justify-between items-center py-[0.8rem] px-4 bg-black/20 border-b border-[#334155]">
          <span className="text-[0.95rem] text-[#F8FAFC] font-semibold">📚 相关文献</span>
        </div>
        <div className="text-center p-8 text-[#94A3B8] text-[0.9375rem]">未检索到相关文献</div>
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
    <div className="bg-[#1E293B] border border-[#334155] rounded-[14px] overflow-hidden flex flex-col mb-4">
      <div className="flex justify-between items-center py-[0.8rem] px-4 bg-black/20 border-b border-[#334155]">
        <span className="text-[0.95rem] text-[#F8FAFC] font-semibold">
          📚 相关文献（{papers.length} 篇）{sourceLabel}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-[0.8rem] flex flex-col gap-[0.6rem]">
        {papers.map((paper, idx) => (
          <div key={`${paper.arxiv_id}-${idx}`} className="bg-black/25 rounded-[10px] py-[0.8rem] px-4 border border-[#334155] transition-all duration-200 hover:border-[rgba(45,212,191,0.15)]">
            <div className="flex justify-between items-start gap-2 mb-[0.4rem]">
              <a
                href={paper.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[0.9375rem] font-semibold text-[#3498db] no-underline leading-[1.4] flex-1 hover:underline"
                title={paper.title}
              >
                {paper.title}
              </a>
              <span className="text-[0.78rem] text-[#94A3B8] bg-[#334155] py-[0.15rem] px-2 rounded-[4px] whitespace-nowrap">{paper.year || '—'}</span>
            </div>
            <div className="text-[0.875rem] text-[#94A3B8] mb-[0.4rem] leading-[1.4]">
              {paper.authors && paper.authors.length > 0
                ? `${paper.authors.slice(0, 5).join(', ')}${
                    paper.authors.length > 5 ? ` et al. (${paper.authors.length} 位作者)` : ''
                  }`
                : '作者未知'}
            </div>
            <div className="flex gap-[0.3rem] items-center flex-wrap mb-[0.4rem]">
              <span className="text-[0.875rem] text-[#e0c080] bg-[rgba(224,192,128,0.1)] py-[0.15rem] px-[0.4rem] rounded-[4px]">arXiv:{paper.arxiv_id}</span>
              {paper.relevance_score !== undefined && paper.relevance_score !== null && (
                <span className="text-[0.875rem] text-[#f39c12] bg-[rgba(243,156,18,0.1)] py-[0.15rem] px-[0.4rem] rounded-[4px]" title="相关性评分">
                  相关度 {paper.relevance_score}
                </span>
              )}
              {paper.citation_count !== undefined && paper.citation_count !== null && (
                <span className="text-[0.875rem] text-[#e8a0a0] bg-[rgba(232,160,160,0.1)] py-[0.15rem] px-[0.4rem] rounded-[4px]" title="被引次数">
                  被引 {paper.citation_count} 次
                </span>
              )}
              {paper.venue && (
                <span className="text-[0.875rem] text-[#c0a0e8] bg-[rgba(192,160,232,0.1)] py-[0.15rem] px-[0.4rem] rounded-[4px] max-w-[220px] overflow-hidden text-ellipsis whitespace-nowrap" title={paper.venue}>
                  {paper.venue.length > 30 ? paper.venue.slice(0, 30) + '...' : paper.venue}
                </span>
              )}
              {paper.doi && (
                <a
                  href={`https://doi.org/${paper.doi}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[0.875rem] text-[#a0c0e8] no-underline py-[0.15rem] px-[0.4rem] border border-[rgba(160,192,232,0.3)] rounded-[4px] hover:bg-[rgba(160,192,232,0.15)]"
                >
                  DOI
                </a>
              )}
              {paper.categories?.slice(0, 3).map((cat) => (
                <span key={cat} className="text-[0.875rem] text-[#a0e0a0] bg-[rgba(160,224,160,0.1)] py-[0.15rem] px-[0.4rem] rounded-[4px]">
                  {cat}
                </span>
              ))}
              {paper.pdf_url ? (
                <a
                  href={paper.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[0.875rem] text-[#e74c3c] no-underline ml-auto py-[0.15rem] px-[0.4rem] border border-[rgba(248,113,113,0.15)] rounded-[4px] hover:bg-[rgba(248,113,113,0.15)]"
                >
                  PDF
                </a>
              ) : null}
            </div>
            {paper.fields_of_study && paper.fields_of_study.length > 0 && (
              <div className="flex gap-[0.3rem] flex-wrap mb-[0.4rem]">
                {paper.fields_of_study.slice(0, 4).map((field) => (
                  <span key={field} className="text-[0.72rem] text-[#94A3B8] bg-[#1E293B] py-[0.1rem] px-[0.35rem] rounded-[3px]">
                    {field}
                  </span>
                ))}
              </div>
            )}
            {paper.tldr && (
              <div className="text-[0.875rem] text-[#94A3B8] mb-2 py-[0.4rem] px-[0.6rem] bg-[#1E293B] rounded-[6px] border-l-2 border-l-[rgba(45,212,191,0.15)] leading-[1.5]">
                <span className="text-[#3498db] font-semibold mr-[0.3rem]">TL;DR:</span> {paper.tldr}
              </div>
            )}
            {paper.extraction && (
              <div className="text-[0.875rem] text-[#94A3B8] mb-2 py-[0.5rem] px-[0.7rem] bg-[rgba(74,222,128,0.15)] rounded-[6px] border-l-2 border-l-[rgba(74,222,128,0.15)] leading-[1.5]">
                {paper.extraction.methods && <div className="mb-[0.25rem]"><strong className="text-[#2ecc71] mr-[0.3rem]">方法：</strong> {paper.extraction.methods}</div>}
                {paper.extraction.conclusion && <div className="mb-[0.25rem]"><strong className="text-[#2ecc71] mr-[0.3rem]">结论：</strong> {paper.extraction.conclusion}</div>}
                {paper.extraction.datasets && paper.extraction.datasets.length > 0 && <div className="mb-[0.25rem]"><strong className="text-[#2ecc71] mr-[0.3rem]">数据集：</strong> {paper.extraction.datasets.join(', ')}</div>}
                {paper.extraction.limitations && <div className="mb-[0.25rem]"><strong className="text-[#2ecc71] mr-[0.3rem]">局限：</strong> {paper.extraction.limitations}</div>}
              </div>
            )}
            <button
              type="button"
              className="text-[0.78rem] text-[#94A3B8] bg-transparent border-none cursor-pointer py-[0.2rem] px-0 text-left hover:text-[#CBD5E1]"
              onClick={() => toggleAbstract(idx)}
            >
              {expanded.has(idx) ? '收起摘要 ▲' : '查看摘要 ▼'}
            </button>
            {expanded.has(idx) && (
              <div className="text-[0.82rem] text-[#94A3B8] leading-[1.6] mt-[0.4rem] pt-[0.4rem] border-t border-[#334155] max-h-[200px] overflow-y-auto">{paper.abstract}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
