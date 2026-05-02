'use client';

import { useEffect, useState } from 'react';
import styles from './SystemStatus.module.css';

interface SystemInfo {
  app_name: string;
  version: string;
  default_model: string;
  api_base_url: string;
  team_size: number;
  active_chat_rooms: string[];
  claude_code_available: boolean;
  claude_code_path: string;
  claude_model: string;
  default_llm_backend: string;
}

interface ProviderStatus {
  name: string;
  available: boolean;
  detail?: string;
}

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

export default function SystemStatus() {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(apiBase() + '/info');
        if (res.ok) {
          const data = await res.json();
          setInfo(data);
          // Derive provider statuses
          const provs: ProviderStatus[] = [
            { name: 'Claude Code CLI', available: data.claude_code_available, detail: data.claude_code_path || '未安装' },
            { name: '默认后端', available: true, detail: data.default_llm_backend },
          ];
          setProviders(provs);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>⏳ 检测系统状态中...</div>
      </div>
    );
  }

  if (!info) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>❌ 无法连接到后端</div>
        <div className={styles.errorHint}>请确认后端服务已启动：<code>python -m backend.app.main</code></div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.title}>🖥️ 系统状态</span>
        <span className={styles.version}>v{info.version}</span>
      </div>

      <div className={styles.grid}>
        <div className={styles.item}>
          <span className={styles.label}>默认模型</span>
          <span className={styles.value}>{info.default_model || '未配置'}</span>
        </div>
        <div className={styles.item}>
          <span className={styles.label}>团队规模</span>
          <span className={styles.value}>{info.team_size} 个 Agent</span>
        </div>
        <div className={styles.item}>
          <span className={styles.label}>活跃会话</span>
          <span className={styles.value}>{info.active_chat_rooms.length} 个</span>
        </div>
        <div className={styles.item}>
          <span className={styles.label}>后端地址</span>
          <span className={styles.valueSmall}>{info.api_base_url}</span>
        </div>
      </div>

      <div className={styles.providersTitle}>Provider 可用性</div>
      <div className={styles.providers}>
        {providers.map(p => (
          <div key={p.name} className={styles.provider}>
            <span className={`${styles.dot} ${p.available ? styles.dotOn : styles.dotOff}`} />
            <span className={styles.providerName}>{p.name}</span>
            <span className={styles.providerDetail}>{p.detail}</span>
          </div>
        ))}
      </div>

      {!info.claude_code_available && (
        <div className={styles.hint}>
          💡 建议安装 Claude Code CLI 作为备用 Provider：
          <code>npm install -g @anthropic-ai/claude-code</code>
        </div>
      )}
    </div>
  );
}
