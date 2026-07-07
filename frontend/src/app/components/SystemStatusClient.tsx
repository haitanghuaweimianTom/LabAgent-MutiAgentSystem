'use client';

import { useEffect, useState, useSyncExternalStore } from 'react';
import { cn } from '@/lib/utils';
import { apiBase } from '@/lib/api';
import { useTheme } from '@/hooks/useTheme';

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

declare global {
  interface Window {
    __API_BASE__?: string;
    __INITIAL_INFO__?: SystemInfo;
  }
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}小时${m}分钟`;
}

const infoStore = {
  getSnapshot: (): SystemInfo | null => {
    if (typeof window === 'undefined') return null;
    return window.__INITIAL_INFO__ || null;
  },
  getServerSnapshot: (): SystemInfo | null => null,
  subscribe: (callback: () => void) => {
    const interval = setInterval(() => {
      if (window.__INITIAL_INFO__) {
        callback();
        clearInterval(interval);
      }
    }, 50);
    return () => clearInterval(interval);
  },
};

function SystemStatusSkeleton() {
  return (
    <div className="bg-card border border-border rounded-[14px] p-[1.2rem] mb-4">
      <div className="flex justify-between items-center mb-4">
        <span className="text-[1rem] text-foreground font-semibold">🖥️ 系统状态</span>
        <span className="text-[0.875rem] text-muted-foreground bg-muted py-0.5 px-2 rounded-[6px]">加载中...</span>
      </div>
      <div className="grid grid-cols-2 gap-[0.6rem] mb-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex flex-col gap-0.5 p-2 bg-muted/50 rounded-[8px]">
            <span className="text-[0.72rem] text-muted-foreground font-semibold">加载中</span>
            <span className="text-[0.9375rem] text-muted-foreground">────</span>
          </div>
        ))}
      </div>
      <div className="text-[0.9375rem] text-muted-foreground font-semibold mb-2">Provider 配置状态</div>
      <div className="flex flex-col gap-[0.4rem]">
        <div className="flex items-center gap-2 py-[0.4rem] px-[0.6rem] bg-muted/50 rounded-[6px] text-[0.82rem]">
          <span className="w-2 h-2 rounded-full shrink-0 bg-muted-foreground" />
          <span className="text-muted-foreground">加载中...</span>
        </div>
      </div>
    </div>
  );
}

function SystemStatusError() {
  return (
    <div className="bg-card border border-border rounded-[14px] p-[1.2rem] mb-4">
      <div className="text-center p-4 text-error text-[0.9375rem]">❌ 无法连接到后端</div>
      <div className="text-center py-2 text-muted-foreground text-[0.82rem]">
        请确认后端服务已启动：<code className="bg-muted py-[0.15rem] px-[0.4rem] rounded-[4px] text-success font-mono text-[0.78rem]">python -m backend.app.main</code>
      </div>
    </div>
  );
}

function SystemStatusContent({ info }: { info: SystemInfo }) {
  const [uptime, setUptime] = useState('');
  const { theme } = useTheme();
  const dark = theme === 'dark';

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

  const defaultModel = info.default_provider?.model || info.default_model || '未配置';
  const defaultProviderName = info.default_provider?.name || info.default_llm_backend || '未配置';

  return (
    <div className="bg-card border border-border rounded-[14px] p-[1.2rem] mb-4">
      <div className="flex justify-between items-center mb-4">
        <span className="text-[1rem] text-foreground font-semibold">🖥️ 系统状态</span>
        <span className="text-[0.875rem] text-muted-foreground bg-muted py-0.5 px-2 rounded-[6px]">v{info.version}</span>
      </div>

      <div className="grid grid-cols-2 gap-[0.6rem] mb-4">
        <div className="flex flex-col gap-0.5 p-2 bg-muted/50 rounded-[8px]">
          <span className="text-[0.72rem] text-muted-foreground font-semibold">默认模型</span>
          <span className="text-[0.9375rem] text-foreground">{defaultModel}</span>
          <span className="text-[0.875rem] text-muted-foreground break-all">{defaultProviderName}</span>
        </div>
        <div className="flex flex-col gap-0.5 p-2 bg-muted/50 rounded-[8px]">
          <span className="text-[0.72rem] text-muted-foreground font-semibold">Agent 团队</span>
          <span className="text-[0.9375rem] text-foreground">{info.agent_count} 个</span>
          <div className="flex flex-wrap gap-1 mt-[0.3rem]">
            {info.agents?.map(a => (
              <span key={a.id} title={a.description} className="text-[0.7rem] text-muted-foreground bg-muted py-[0.15rem] px-[0.4rem] rounded-[4px] cursor-default">
                {a.label}
              </span>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-0.5 p-2 bg-muted/50 rounded-[8px]">
          <span className="text-[0.72rem] text-muted-foreground font-semibold">知识库</span>
          <span className="text-[0.9375rem] text-foreground">{info.knowledge_base_count} 个</span>
        </div>
        <div className="flex flex-col gap-0.5 p-2 bg-muted/50 rounded-[8px]">
          <span className="text-[0.72rem] text-muted-foreground font-semibold">任务</span>
          <span className="text-[0.9375rem] text-foreground">
            {info.active_tasks > 0 ? (
              <span className="text-success">{info.active_tasks} 运行中</span>
            ) : (
              '空闲'
            )}
            <span className="text-muted-foreground text-[0.75rem] ml-1">
              / {info.total_tasks} 总计
            </span>
          </span>
        </div>
        <div className="flex flex-col gap-0.5 p-2 bg-muted/50 rounded-[8px]">
          <span className="text-[0.72rem] text-muted-foreground font-semibold">运行时长</span>
          <span className="text-[0.9375rem] text-foreground">{uptime || '-'}</span>
        </div>
        <div className="flex flex-col gap-0.5 p-2 bg-muted/50 rounded-[8px]">
          <span className="text-[0.72rem] text-muted-foreground font-semibold">后端连接</span>
          <span className="text-[0.9375rem] text-success">✅ 正常</span>
          <span className="text-[0.875rem] text-muted-foreground break-all">{apiBase()}</span>
        </div>
      </div>

      <div className="text-[0.9375rem] text-muted-foreground font-semibold mb-2">Provider 配置状态</div>
      {info.providers.length === 0 ? (
        <div className="text-muted-foreground text-[0.82rem] py-2">暂无 Provider 配置，请前往「模型设置」添加</div>
      ) : (
        <div className="flex flex-col gap-[0.4rem]">
          {info.providers.map(p => (
            <div key={p.id} className="flex items-center gap-2 py-[0.4rem] px-[0.6rem] bg-muted/50 rounded-[6px] text-[0.82rem]">
              <span className={cn('w-2 h-2 rounded-full shrink-0', p.available ? 'bg-success shadow-[0_0_6px_rgba(16,185,129,0.15)]' : 'bg-error shadow-[0_0_6px_rgba(239,68,68,0.15)]')} />
              <span className="text-foreground font-medium min-w-[120px]">{p.name}</span>
              <span className="text-muted-foreground text-[0.8125rem] bg-muted py-[0.1rem] px-[0.35rem] rounded-[4px]">{p.type}</span>
              {p.model && <span className="text-muted-foreground text-[0.875rem] ml-auto">{p.model}</span>}
            </div>
          ))}
        </div>
      )}

      <div className="text-[0.9375rem] text-muted-foreground font-semibold mb-2">工具链</div>
      <div className="flex flex-col gap-[0.4rem]">
        <div className="flex items-center gap-2 py-[0.4rem] px-[0.6rem] bg-muted/50 rounded-[6px] text-[0.82rem]">
          <span className={cn('w-2 h-2 rounded-full shrink-0', info.claude_code_available ? 'bg-success shadow-[0_0_6px_rgba(16,185,129,0.15)]' : 'bg-error shadow-[0_0_6px_rgba(239,68,68,0.15)]')} />
          <span className="text-foreground font-medium min-w-[120px]">Claude Code CLI</span>
          <span className="text-muted-foreground text-[0.875rem]">
            {info.claude_code_available ? info.claude_code_path : '未安装'}
          </span>
        </div>
      </div>

      <div className="text-[0.9375rem] text-muted-foreground font-semibold mb-2">CC Switch</div>
      <div className="flex flex-col gap-[0.4rem]">
        <div className="flex items-center gap-2 py-[0.4rem] px-[0.6rem] bg-muted/50 rounded-[6px] text-[0.82rem]">
          <span className={cn('w-2 h-2 rounded-full shrink-0', info.ccswitch_status?.installed ? 'bg-success shadow-[0_0_6px_rgba(16,185,129,0.15)]' : 'bg-error shadow-[0_0_6px_rgba(239,68,68,0.15)]')} />
          <span className="text-foreground font-medium min-w-[120px]">CC Switch</span>
          <span className="text-muted-foreground text-[0.875rem]">
            {info.ccswitch_status?.installed
              ? (info.ccswitch_status?.current_provider || '已安装')
              : '未安装'}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function SystemStatusClient() {
  const info = useSyncExternalStore(
    infoStore.subscribe,
    infoStore.getSnapshot,
    infoStore.getServerSnapshot
  );

  if (!info) {
    return <SystemStatusSkeleton />;
  }

  return <SystemStatusContent info={info} />;
}
