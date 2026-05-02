'use client';

import styles from './AlgorithmRecommend.module.css';

interface Algorithm {
  name_cn: string;
  name_en: string;
  relevance_score: number;
  description: string;
  applicable_scenarios: string[];
  mathematical_model: string;
  advantages: string[];
  limitations: string[];
  subtypes?: Record<string, string>;
}

interface AlgorithmRecommendProps {
  algorithms: Algorithm[];
}

export default function AlgorithmRecommend({ algorithms }: AlgorithmRecommendProps) {
  if (!algorithms || algorithms.length === 0) return null;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.title}>🔍 算法库推荐</span>
        <span className={styles.subtitle}>基于问题特征自动检索</span>
      </div>
      <div className={styles.list}>
        {algorithms.map((algo, idx) => (
          <div key={algo.name_en} className={styles.card}>
            <div className={styles.cardHeader}>
              <span className={styles.rank}>#{idx + 1}</span>
              <span className={styles.name}>{algo.name_cn}</span>
              <span className={styles.nameEn}>{algo.name_en}</span>
              <span className={styles.score}>相关度 {algo.relevance_score}</span>
            </div>
            <div className={styles.cardBody}>
              <div className={styles.row}>
                <span className={styles.label}>描述</span>
                <span className={styles.text}>{algo.description}</span>
              </div>
              <div className={styles.row}>
                <span className={styles.label}>适用场景</span>
                <span className={styles.text}>{algo.applicable_scenarios.slice(0, 3).join(' · ')}</span>
              </div>
              <div className={styles.row}>
                <span className={styles.label}>数学模型</span>
                <span className={styles.textMono}>{algo.mathematical_model}</span>
              </div>
              {algo.subtypes && Object.keys(algo.subtypes).length > 0 && (
                <div className={styles.row}>
                  <span className={styles.label}>具体方法</span>
                  <div className={styles.tags}>
                    {Object.keys(algo.subtypes).map(st => (
                      <span key={st} className={styles.tag}>{st}</span>
                    ))}
                  </div>
                </div>
              )}
              <div className={styles.rowInline}>
                {algo.advantages.length > 0 && (
                  <div className={styles.pros}>
                    <span className={styles.prosLabel}>优点</span>
                    {algo.advantages.join(' · ')}
                  </div>
                )}
                {algo.limitations.length > 0 && (
                  <div className={styles.cons}>
                    <span className={styles.consLabel}>局限</span>
                    {algo.limitations.join(' · ')}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
