'use client';

import { useState, useEffect } from 'react';
import ProviderSettings from './ProviderSettings';
import McpManager from './McpManager';
import KnowledgeBaseManager from './KnowledgeBaseManager';
import DatasourceSettings from './DatasourceSettings';
import { apiBase } from '@/lib/api';

interface SystemInfo {
  claude_code_available: boolean;
  claude_code_path: string;
  claude_model: string;
  claude_mcp_tools: string;
  claude_mcp_config_path: string;
  default_llm_backend: string;
  default_model: string;
  version: string;
}

const TABS = [
  { id: 'providers' as const, label: '🔌 Provider 管理' },
  { id: 'datasources' as const, label: '🗃️ 数据源' },
  { id: 'mcp' as const, label: '🔗 MCP 管理' },
  { id: 'knowledge' as const, label: '📚 知识库' },
  { id: 'system' as const, label: '⚙️ 系统设置' },
];

export default function SettingsPage() {
  const [settingsMsg, setSettingsMsg] = useState('');
  const [sysInfo, setSysInfo] = useState<SystemInfo | null>(null);
  const [activeTab, setActiveTab] = useState<'providers' | 'datasources' | 'mcp' | 'knowledge' | 'system'>('providers');

  const [claudeModel, setClaudeModel] = useState('');
  const [claudeMcpTools, setClaudeMcpTools] = useState('');
  const [claudeMcpConfigPath, setClaudeMcpConfigPath] = useState('');
  const [claudeTemperature, setClaudeTemperature] = useState('0.3');
  const [claudeMaxTokens, setClaudeMaxTokens] = useState('8192');
  const [claudeCoderPreferCli, setClaudeCoderPreferCli] = useState(false);

  const [availableModels, setAvailableModels] = useState<{id: string, name: string, provider: string}[]>([]);

  useEffect(() => {
    fetch(apiBase() + '/info').then(r => r.ok ? r.json() : null).then(i => {
      if (i) {
        setSysInfo(i);
        setClaudeModel(i.claude_model || '');
        setClaudeMcpTools(i.claude_mcp_tools || '');
        setClaudeMcpConfigPath(i.claude_mcp_config_path || '');
      }
    }).catch(() => {});

    fetch(apiBase() + '/providers/').then(r => r.ok ? r.json() : null).then(data => {
      if (data) {
        const models: {id: string, name: string, provider: string}[] = [];
        const customProviders = data.custom_providers || [];
        customProviders.forEach((p: any) => {
          const providerName = p.name || p.id;
          (p.models || []).forEach((m: any) => {
            if (m.enabled !== false) {
              models.push({id: m.name, name: `${m.name} (${providerName})`, provider: p.id});
            }
          });
        });
        const presets = data.presets || [];
        presets.forEach((p: any) => {
          (p.models || []).forEach((m: any) => {
            if (m.enabled !== false && !models.find((mm: any) => mm.id === m.name)) {
              models.push({id: m.name, name: `${m.name} (${p.name})`, provider: p.id});
            }
          });
        });
        setAvailableModels(models);
      }
    }).catch(() => {});

    // 加载 Claude Code CLI 代码生成开关（/settings GET）
    fetch(apiBase() + '/settings').then(r => r.ok ? r.json() : null).then(st => {
      if (st && st.providers?.claude_cli) {
        setClaudeCoderPreferCli(st.providers.claude_cli.coder_prefer_cli === true);
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const handler = (e: CustomEvent) => {
      const targetTab = e.detail as 'providers' | 'datasources' | 'mcp' | 'knowledge' | 'system';
      if (TABS.some(t => t.id === targetTab)) {
        setActiveTab(targetTab);
      }
    };
    window.addEventListener('mm:settings-tab', handler as EventListener);
    return () => window.removeEventListener('mm:settings-tab', handler as EventListener);
  }, []);

  const handleSaveClaudeSettings = async () => {
    try {
      const res = await fetch(apiBase() + '/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          claude_model: claudeModel,
          claude_mcp_tools: claudeMcpTools,
          claude_mcp_config_path: claudeMcpConfigPath,
          claude_temperature: parseFloat(claudeTemperature) || 0.3,
          claude_max_tokens: parseInt(claudeMaxTokens) || 8192,
          claude_coder_prefer_cli: claudeCoderPreferCli,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setSettingsMsg('✓ Claude Code 设置保存成功！Agent已重新初始化');
        const i = await fetch(apiBase() + '/info').then(r => r.ok ? r.json() : null);
        if (i) setSysInfo(i);
      } else {
        setSettingsMsg('保存失败: ' + (data.message || ''));
      }
    } catch {
      setSettingsMsg('保存失败');
    }
  };

  return (
    <div className="flex flex-col gap-6 space-y-6">
      <div className="flex gap-3 flex-wrap">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`py-2 px-5 rounded-md cursor-pointer text-sm transition-colors border ${
              activeTab === tab.id
                ? 'bg-primary/10 border-primary/40 text-primary font-semibold'
                : 'bg-muted border-border text-muted-foreground font-normal'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {settingsMsg && (
        <div className={`text-sm text-center ${settingsMsg.includes('✓') ? 'text-success' : 'text-error'}`}>
          {settingsMsg}
        </div>
      )}

      {activeTab === 'providers' && <ProviderSettings />}
      {activeTab === 'datasources' && <DatasourceSettings />}
      {activeTab === 'mcp' && <McpManager />}
      {activeTab === 'knowledge' && <KnowledgeBaseManager />}

      {activeTab === 'system' && (
        <div className="flex flex-col gap-6">
          <div className="bg-card border border-border rounded-lg p-5">
            <span className="text-sm text-foreground font-semibold">🤖 Claude Code CLI 配置</span>

            <div className="mb-3 flex items-center gap-3 mt-4">
              <span className={`w-2 h-2 rounded-full ${sysInfo?.claude_code_available ? 'bg-success' : 'bg-muted-foreground'}`} />
              <span className="text-foreground text-sm">
                {sysInfo?.claude_code_available ? `已安装: ${sysInfo?.claude_code_path}` : '未安装 - 请运行 npm install -g @anthropic-ai/claude-code'}
              </span>
            </div>

            <div className="flex flex-col gap-3 mb-4">
              <div className="text-sm text-muted-foreground font-semibold">Claude 模型</div>
              <div className="flex gap-3">
                <select
                  className="flex-1 text-foreground bg-muted border border-border p-2 rounded-md"
                  value={claudeModel}
                  onChange={e => setClaudeModel(e.target.value)}
                >
                  <option value="">-- 选择模型 --</option>
                  {availableModels.length === 0 && (
                    <option value="" disabled>未检测到可用模型，请先在 Provider 管理中添加</option>
                  )}
                  {availableModels.map(m => (
                    <option key={`${m.provider}-${m.id}`} value={m.id}>{m.name}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-3 mb-4">
              <div className="text-sm text-muted-foreground font-semibold">MCP 工具（逗号分隔）</div>
              <div className="flex gap-3">
                <input type="text" className="flex-1 text-foreground bg-muted border border-border p-2 rounded-md" placeholder="bing_search,web_search,paper_search,sequentialthinking" value={claudeMcpTools} onChange={e => setClaudeMcpTools(e.target.value)} />
              </div>
              <div className="text-xs text-muted-foreground">可用: bing_search, web_search, paper_search, python_execute, sequentialthinking</div>
            </div>

            <div className="flex flex-col gap-3 mb-4">
              <div className="text-sm text-muted-foreground font-semibold">MCP 配置文件路径</div>
              <div className="flex gap-3">
                <input type="text" className="flex-1 text-foreground bg-muted border border-border p-2 rounded-md" placeholder="留空则自动搜索" value={claudeMcpConfigPath} onChange={e => setClaudeMcpConfigPath(e.target.value)} />
              </div>
            </div>

            <div className="flex flex-col gap-3 mb-4">
              <div className="text-sm text-muted-foreground font-semibold">温度</div>
              <div className="flex gap-3">
                <input type="number" className="flex-1 text-foreground bg-muted border border-border p-2 rounded-md" placeholder="0.3" value={claudeTemperature} onChange={e => setClaudeTemperature(e.target.value)} min="0" max="1" step="0.1" />
              </div>
            </div>

            <div className="flex flex-col gap-3 mb-4">
              <div className="text-sm text-muted-foreground font-semibold">最大输出 Token</div>
              <div className="flex gap-3">
                <input type="number" className="flex-1 text-foreground bg-muted border border-border p-2 rounded-md" placeholder="8192" value={claudeMaxTokens} onChange={e => setClaudeMaxTokens(e.target.value)} min="100" max="32000" />
              </div>
            </div>

            <div className="flex flex-col gap-3 mb-4">
              <div className="text-sm text-muted-foreground font-semibold">代码生成方式</div>
              <label className="flex items-center gap-3 cursor-pointer">
                <input type="checkbox" checked={claudeCoderPreferCli} onChange={e => setClaudeCoderPreferCli(e.target.checked)} className="cursor-pointer" />
                <span className="text-sm text-muted-foreground">
                  优先使用 Claude Code CLI 生成代码
                  <span className="text-muted-foreground text-xs">（默认关闭=走 HTTP API，更快更稳；CLI 在部分子问题上会反复超时重试）</span>
                </span>
              </label>
            </div>

            <div className="flex gap-3 mt-4">
              <button className="bg-primary text-primary-foreground border-none py-2.5 px-5 rounded-md cursor-pointer font-semibold hover:opacity-90" onClick={handleSaveClaudeSettings}>💾 保存 Claude Code 配置</button>
            </div>
          </div>

          <div className="bg-card border border-border rounded-lg p-5">
            <span className="text-sm text-foreground font-semibold">ℹ️ 系统信息</span>
            <div className="mt-4 p-4 bg-muted rounded-md text-sm text-muted-foreground leading-relaxed">
              <strong className="text-foreground">📍 访问地址：</strong>
              <code className="text-warning">本机: http://localhost:3000</code><br />
              <code className="text-warning">局域网: 请使用本机 IP:3000</code><br />
              <strong className="text-foreground">📖 后端 API 文档：</strong>
              <code className="text-warning">http://localhost:8001/docs</code><br />
              {sysInfo && (
                <>
                  <strong className="text-foreground">🔄 版本：</strong><code className="text-warning">v{sysInfo.version}</code><br />
                  <strong className="text-foreground">🤖 默认后端：</strong><code className="text-warning">{sysInfo.default_llm_backend}</code><br />
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
