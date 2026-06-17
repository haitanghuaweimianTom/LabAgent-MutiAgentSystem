'use client';

import { useEffect, useState } from 'react';
import styles from './SystemStatus.module.css';

interface ProviderInfo {
  id: string;
  name: string;
  type: string;
  available: boolean;
  model?: string;
}

interface AgentInfo {
  id: string;
  label: string;
  description: string;
}

interface SystemInfo {
  app_name: string;
  version: string;
  started_at: number;
  default_provider?: {
    id?: string;
    name?: string;
    type?: string;
    model?: string;
  } | null;
  default_model?: string;
  default_llm_backend?: string;
  agent_count: number;
  agents: AgentInfo[];
  knowledge_base_count: number;
  total_tasks: number;
  active_tasks: number;
  ccswitch_status?: {
    installed: boolean;
    current_provider?: string;
    auto_sync_enabled?: boolean;
  };
  providers: ProviderInfo[];
  claude_code_available: boolean;
  claude_code_path: string;
}

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}小时${m}分钟`;
}

export default function SystemStatus() {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [uptime, setUptime] = useState('');

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(apiBase() + '/info');
        if (res.ok) {
          const data = await res.json();
          setInfo(data);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  useEffect(() => {
    if (!info?.started_at) return;
    const update = () => {
      const seconds = Date.now() / 1000 - info.started_at;
      setUptime(formatUptime(seconds));
    };
    update();
    const timer = setInterval(update, 30000);
    return () => clearInterval(timer);
  }, [info?.started_at]);

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
        <div className={styles.errorHint}>
          请确认后端服务已启动：<code>python -m backend.app.main</code>
        </div>
      </div>
    );
  }

  const defaultModel = info.default_provider?.model || info.default_model || '未配置';
  const defaultProviderName = info.default_provider?.name || info.default_llm_backend || '未配置';

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.title}>🖥️ 系统状态</span>
        <span className={styles.version}>v{info.version}</span>
      </div>

      <div className={styles.grid}>
        <div className={styles.item}>
          <span className={styles.label}>默认模型</span>
          <span className={styles.value}>{defaultModel}</span>
          <span className={styles.valueSmall}>{defaultProviderName}</span>
        </div>
        <div className={styles.item}>
          <span className={styles.label}>Agent 团队</span>
          <span className={styles.value}>{info.agent_count} 个</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem', marginTop: '0.3rem' }}>
            {info.agents?.map(a => (
              <span key={a.id} title={a.description} style={{
                fontSize: '0.7rem',
                color: '#aaa',
                background: 'rgba(255,255,255,0.06)',
                padding: '0.15rem 0.4rem',
                borderRadius: '4px',
                cursor: 'default',
              }}>
                {a.label}
              </span>
            ))}
          </div>
        </div>
        <div className={styles.item}>
          <span className={styles.label}>知识库</span>
          <span className={styles.value}>{info.knowledge_base_count} 个</span>
        </div>
        <div className={styles.item}>
          <span className={styles.label}>任务</span>
          <span className={styles.value}>
            {info.active_tasks > 0 ? (
              <span style={{ color: '#4caf50' }}>{info.active_tasks} 运行中</span>
            ) : (
              '空闲'
            )}
            <span style={{ color: '#888', fontSize: '0.75rem', marginLeft: 4 }}>
              / {info.total_tasks} 总计
            </span>
          </span>
        </div>
        <div className={styles.item}>
          <span className={styles.label}>运行时长</span>
          <span className={styles.value}>{uptime || '-'}</span>
        </div>
        <div className={styles.item}>
          <span className={styles.label}>后端连接</span>
          <span className={styles.value} style={{ color: '#4caf50' }}>✅ 正常</span>
          <span className={styles.valueSmall}>{apiBase()}</span>
        </div>
      </div>

      <div className={styles.providersTitle}>Provider 配置状态</div>
      {info.providers.length === 0 ? (
        <div className={styles.emptyHint}>暂无 Provider 配置，请前往「模型设置」添加</div>
      ) : (
        <div className={styles.providers}>
          {info.providers.map(p => (
            <div key={p.id} className={styles.provider}>
              <span className={`${styles.dot} ${p.available ? styles.dotOn : styles.dotOff}`} />
              <span className={styles.providerName}>{p.name}</span>
              <span className={styles.providerType}>{p.type}</span>
              {p.model && <span className={styles.providerModel}>{p.model}</span>}
            </div>
          ))}
        </div>
      )}

      <div className={styles.providersTitle}>工具链</div>
      <div className={styles.providers}>
        <div className={styles.provider}>
          <span className={`${styles.dot} ${info.claude_code_available ? styles.dotOn : styles.dotOff}`} />
          <span className={styles.providerName}>Claude Code CLI</span>
          <span className={styles.providerDetail}>
            {info.claude_code_available ? info.claude_code_path : '未安装'}
          </span>
        </div>
      </div>

      <div className={styles.providersTitle}>CC Switch</div>
      <div className={styles.providers}>
        <div className={styles.provider}>
          <span className={`${styles.dot} ${info.ccswitch_status?.installed ? styles.dotOn : styles.dotOff}`} />
          <span className={styles.providerName}>CC Switch</span>
          <span className={styles.providerDetail}>
            {info.ccswitch_status?.installed
              ? (info.ccswitch_status?.current_provider || '已安装')
              : '未安装'}
          </span>
        </div>
      </div>
    </div>
  );
}
