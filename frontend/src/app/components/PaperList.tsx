'use client';

import { useState } from 'react';
import styles from './PaperList.module.css';
import type { Paper } from '../store/useAppStore';

interface PaperListProps {
  papers: Paper[];
  source?: string;
}

export default function PaperList({ papers, source }: PaperListProps) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  if (!papers || papers.length === 0) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <span className={styles.title}>📚 相关文献</span>
        </div>
        <div className={styles.empty}>未检索到相关文献</div>
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
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.title}>
          📚 相关文献（{papers.length} 篇）{sourceLabel}
        </span>
      </div>
      <div className={styles.list}>
        {papers.map((paper, idx) => (
          <div key={`${paper.arxiv_id}-${idx}`} className={styles.card}>
            <div className={styles.cardHeader}>
              <a
                href={paper.url}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.titleLink}
                title={paper.title}
              >
                {paper.title}
              </a>
              <span className={styles.year}>{paper.year || '—'}</span>
            </div>
            <div className={styles.authors}>
              {paper.authors && paper.authors.length > 0
                ? `${paper.authors.slice(0, 5).join(', ')}${
                    paper.authors.length > 5 ? ` et al. (${paper.authors.length} 位作者)` : ''
                  }`
                : '作者未知'}
            </div>
            <div className={styles.meta}>
              <span className={styles.tag}>arXiv:{paper.arxiv_id}</span>
              {paper.relevance_score !== undefined && paper.relevance_score !== null && (
                <span className={styles.relevance} title="相关性评分">
                  相关度 {paper.relevance_score}
                </span>
              )}
              {paper.citation_count !== undefined && paper.citation_count !== null && (
                <span className={styles.citation} title="被引次数">
                  被引 {paper.citation_count} 次
                </span>
              )}
              {paper.venue && (
                <span className={styles.venue} title={paper.venue}>
                  {paper.venue.length > 30 ? paper.venue.slice(0, 30) + '...' : paper.venue}
                </span>
              )}
              {paper.doi && (
                <a
                  href={`https://doi.org/${paper.doi}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.doi}
                >
                  DOI
                </a>
              )}
              {paper.categories?.slice(0, 3).map((cat) => (
                <span key={cat} className={styles.category}>
                  {cat}
                </span>
              ))}
              {paper.pdf_url ? (
                <a
                  href={paper.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.pdfLink}
                >
                  PDF
                </a>
              ) : null}
            </div>
            {paper.fields_of_study && paper.fields_of_study.length > 0 && (
              <div className={styles.fields}>
                {paper.fields_of_study.slice(0, 4).map((field) => (
                  <span key={field} className={styles.fieldTag}>
                    {field}
                  </span>
                ))}
              </div>
            )}
            {paper.tldr && (
              <div className={styles.tldr}>
                <span className={styles.tldrLabel}>TL;DR:</span> {paper.tldr}
              </div>
            )}
            {paper.extraction && (
              <div className={styles.extraction}>
                {paper.extraction.methods && <div><strong>方法：</strong> {paper.extraction.methods}</div>}
                {paper.extraction.conclusion && <div><strong>结论：</strong> {paper.extraction.conclusion}</div>}
                {paper.extraction.datasets && paper.extraction.datasets.length > 0 && <div><strong>数据集：</strong> {paper.extraction.datasets.join(', ')}</div>}
                {paper.extraction.limitations && <div><strong>局限：</strong> {paper.extraction.limitations}</div>}
              </div>
            )}
            <button
              type="button"
              className={styles.toggleBtn}
              onClick={() => toggleAbstract(idx)}
            >
              {expanded.has(idx) ? '收起摘要 ▲' : '查看摘要 ▼'}
            </button>
            {expanded.has(idx) && (
              <div className={styles.abstract}>{paper.abstract}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
