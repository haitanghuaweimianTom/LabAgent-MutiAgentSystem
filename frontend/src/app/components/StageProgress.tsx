'use client';

import styles from './StageProgress.module.css';

interface Stage {
  id: string;
  name: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  detail?: string;
}

interface MemoryItem {
  key: string;
  label: string;
  content: string;
}

interface StageProgressProps {
  stages: Stage[];
  memoryPool?: MemoryItem[];
  currentStep?: string;
}

const STAGE_ICONS: Record<string, string> = {
  analysis: '🔍',
  modeling: '📐',
  solving: '⚙️',
  writing: '📝',
};

export default function StageProgress({ stages, memoryPool, currentStep }: StageProgressProps) {
  const completedCount = stages.filter(s => s.status === 'completed').length;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.title}>📊 四阶段流水线</span>
        <span className={styles.summary}>
          {completedCount}/{stages.length} 阶段完成
          {currentStep && ` · 当前: ${currentStep}`}
        </span>
      </div>

      <div className={styles.stages}>
        {stages.map((stage, idx) => (
          <div key={stage.id} className={styles.stage}>
            {/* connector line */}
            {idx > 0 && (
              <div className={`${styles.connector} ${stage.status !== 'pending' ? styles.connectorActive : ''}`} />
            )}

            <div className={styles.stageContent}>
              <div className={`${styles.badge} ${styles[stage.status]}`}>
                <span className={styles.icon}>{STAGE_ICONS[stage.id] || '●'}</span>
                <span className={styles.badgeLabel}>{stage.name}</span>
                {stage.status === 'running' && <span className={styles.spinner} />}
                {stage.status === 'completed' && <span className={styles.check}>✓</span>}
                {stage.status === 'failed' && <span className={styles.cross}>✕</span>}
              </div>

              {stage.status !== 'pending' && (
                <div className={styles.detailBox}>
                  <div className={styles.detailText}>{stage.description}</div>
                  {stage.progress > 0 && stage.status !== 'completed' && (
                    <div className={styles.miniBar}>
                      <div className={styles.miniFill} style={{ width: `${stage.progress}%` }} />
                    </div>
                  )}
                  {stage.detail && <div className={styles.subDetail}>{stage.detail}</div>}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Memory Pool */}
      {memoryPool && memoryPool.length > 0 && (
        <div className={styles.memorySection}>
          <div className={styles.memoryTitle}>🧠 显式记忆池</div>
          <div className={styles.memoryList}>
            {memoryPool.map(m => (
              <div key={m.key} className={styles.memoryItem}>
                <span className={styles.memoryLabel}>{m.label}</span>
                <span className={styles.memoryContent}>{m.content}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
