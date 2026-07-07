'use client';

import { useState, useEffect } from 'react';
import ProviderSettings from './ProviderSettings';
import McpManager from './McpManager';
import KnowledgeBaseManager from './KnowledgeBaseManager';
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
  { id: 'mcp' as const, label: '🔗 MCP 管理' },
  { id: 'knowledge' as const, label: '📚 知识库' },
  { id: 'system' as const, label: '⚙️ 系统设置' },
];

export default function SettingsPage() {
  const [settingsMsg, setSettingsMsg] = useState('');
  const [sysInfo, setSysInfo] = useState<SystemInfo | null>(null);
  const [activeTab, setActiveTab] = useState<'providers' | 'mcp' | 'knowledge' | 'system'>('providers');

  const [claudeModel, setClaudeModel] = useState('');
  const [claudeMcpTools, setClaudeMcpTools] = useState('');
  const [claudeMcpConfigPath, setClaudeMcpConfigPath] = useState('');
  const [claudeTemperature, setClaudeTemperature] = useState('0.3');
  const [claudeMaxTokens, setClaudeMaxTokens] = useState('8192');

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
  }, []);

  useEffect(() => {
    const handler = (e: CustomEvent) => {
      const targetTab = e.detail as 'providers' | 'mcp' | 'knowledge' | 'system';
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
    <div className="flex flex-col gap-4">
      <div className="flex gap-2 flex-wrap">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className="py-2 px-[1.2rem] rounded-[8px] cursor-pointer text-[0.9rem] transition-colors"
            style={{
              background: activeTab === tab.id ? 'rgba(52,152,219,0.15)' : 'rgba(255,255,255,0.05)',
              border: `1px solid ${activeTab === tab.id ? 'rgba(52,152,219,0.4)' : 'rgba(255,255,255,0.1)'}`,
              color: activeTab === tab.id ? '#3498db' : '#aaa',
              fontWeight: activeTab === tab.id ? 600 : 400,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {settingsMsg && (
        <div className="text-[0.85rem] text-center" style={{ color: settingsMsg.includes('✓') ? '#2ecc71' : '#e74c3c' }}>
          {settingsMsg}
        </div>
      )}

      {activeTab === 'providers' && <ProviderSettings />}
      {activeTab === 'mcp' && <McpManager />}
      {activeTab === 'knowledge' && <KnowledgeBaseManager />}

      {activeTab === 'system' && (
        <div className="flex flex-col gap-6">
          <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-[1.2rem]">
            <span className="text-[0.95rem] text-[#F8FAFC] font-semibold">🤖 Claude Code CLI 配置</span>

            <div className="mb-[0.8rem] flex items-center gap-2 mt-4">
              <span className="w-2 h-2 rounded-full" style={{ background: sysInfo?.claude_code_available ? '#2ecc71' : '#666' }} />
              <span className="text-[#ddd] text-[0.85rem]">
                {sysInfo?.claude_code_available ? `已安装: ${sysInfo?.claude_code_path}` : '未安装 - 请运行 npm install -g @anthropic-ai/claude-code'}
              </span>
            </div>

            <div className="flex flex-col gap-2 mb-4">
              <div className="text-[0.875rem] text-[#94A3B8] font-semibold">Claude 模型</div>
              <div className="flex gap-2">
                <select
                  className="flex-1 text-[#F8FAFC] bg-[#1E293B] border border-[#334155] p-2 rounded-[6px]"
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

            <div className="flex flex-col gap-2 mb-4">
              <div className="text-[0.875rem] text-[#94A3B8] font-semibold">MCP 工具（逗号分隔）</div>
              <div className="flex gap-2">
                <input type="text" className="flex-1 text-[#F8FAFC] bg-[#1E293B] border border-[#334155] p-2 rounded-[6px]" placeholder="bing_search,web_search,paper_search,sequentialthinking" value={claudeMcpTools} onChange={e => setClaudeMcpTools(e.target.value)} />
              </div>
              <div className="text-[0.75rem] text-[#666]">可用: bing_search, web_search, paper_search, python_execute, sequentialthinking</div>
            </div>

            <div className="flex flex-col gap-2 mb-4">
              <div className="text-[0.875rem] text-[#94A3B8] font-semibold">MCP 配置文件路径</div>
              <div className="flex gap-2">
                <input type="text" className="flex-1 text-[#F8FAFC] bg-[#1E293B] border border-[#334155] p-2 rounded-[6px]" placeholder="留空则自动搜索" value={claudeMcpConfigPath} onChange={e => setClaudeMcpConfigPath(e.target.value)} />
              </div>
            </div>

            <div className="flex flex-col gap-2 mb-4">
              <div className="text-[0.875rem] text-[#94A3B8] font-semibold">温度</div>
              <div className="flex gap-2">
                <input type="number" className="flex-1 text-[#F8FAFC] bg-[#1E293B] border border-[#334155] p-2 rounded-[6px]" placeholder="0.3" value={claudeTemperature} onChange={e => setClaudeTemperature(e.target.value)} min="0" max="1" step="0.1" />
              </div>
            </div>

            <div className="flex flex-col gap-2 mb-4">
              <div className="text-[0.875rem] text-[#94A3B8] font-semibold">最大输出 Token</div>
              <div className="flex gap-2">
                <input type="number" className="flex-1 text-[#F8FAFC] bg-[#1E293B] border border-[#334155] p-2 rounded-[6px]" placeholder="8192" value={claudeMaxTokens} onChange={e => setClaudeMaxTokens(e.target.value)} min="100" max="32000" />
              </div>
            </div>

            <div className="flex gap-2 mt-4">
              <button className="bg-[#3498db] text-white border-none py-2 px-4 rounded-[6px] cursor-pointer font-semibold hover:bg-[#2980b9]" onClick={handleSaveClaudeSettings}>💾 保存 Claude Code 配置</button>
            </div>
          </div>

          <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-[1.2rem]">
            <span className="text-[0.95rem] text-[#F8FAFC] font-semibold">ℹ️ 系统信息</span>
            <div className="mt-4 p-4 bg-black/20 rounded-[6px] text-[0.875rem] text-[#CBD5E1] leading-relaxed">
              <strong className="text-[#F8FAFC]">📍 访问地址：</strong>
              <code className="text-[#e0c080]">本机: http://localhost:3000</code><br />
              <code className="text-[#e0c080]">局域网: 请使用本机 IP:3000</code><br />
              <strong className="text-[#F8FAFC]">📖 后端 API 文档：</strong>
              <code className="text-[#e0c080]">http://localhost:8000/docs</code><br />
              {sysInfo && (
                <>
                  <strong className="text-[#F8FAFC]">🔄 版本：</strong><code className="text-[#e0c080]">v{sysInfo.version}</code><br />
                  <strong className="text-[#F8FAFC]">🤖 默认后端：</strong><code className="text-[#e0c080]">{sysInfo.default_llm_backend}</code><br />
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
