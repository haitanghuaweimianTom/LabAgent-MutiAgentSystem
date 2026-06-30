'use client';

import { useState, useEffect } from 'react';
import styles from '../page.module.css';
import ProviderSettings from './ProviderSettings';
import McpManager from './McpManager';
import KnowledgeBaseManager from './KnowledgeBaseManager';

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

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

  // Claude Code CLI settings
  const [claudeModel, setClaudeModel] = useState('');
  const [claudeMcpTools, setClaudeMcpTools] = useState('');
  const [claudeMcpConfigPath, setClaudeMcpConfigPath] = useState('');
  const [claudeTemperature, setClaudeTemperature] = useState('0.3');
  const [claudeMaxTokens, setClaudeMaxTokens] = useState('8192');

  // Available models from providers
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

    // Load available models from providers
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
        // Also add presets as fallback
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

  // 监听跨组件子 tab 切换事件
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {/* Tab switch */}
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '0.5rem 1.2rem',
              background: activeTab === tab.id ? 'rgba(52,152,219,0.15)' : 'rgba(255,255,255,0.05)',
              border: `1px solid ${activeTab === tab.id ? 'rgba(52,152,219,0.4)' : 'rgba(255,255,255,0.1)'}`,
              borderRadius: 8,
              color: activeTab === tab.id ? '#3498db' : '#aaa',
              cursor: 'pointer',
              fontWeight: activeTab === tab.id ? 600 : 400,
              fontSize: '0.9rem',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {settingsMsg && (
        <div style={{ fontSize: '0.85rem', color: settingsMsg.includes('✓') ? '#2ecc71' : '#e74c3c', textAlign: 'center' }}>
          {settingsMsg}
        </div>
      )}

      {activeTab === 'providers' && <ProviderSettings />}
      {activeTab === 'mcp' && <McpManager />}
      {activeTab === 'knowledge' && <KnowledgeBaseManager />}

      {/* System settings tab */}
      {activeTab === 'system' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Claude Code CLI 配置 */}
          <div className={styles.settingsCard}>
            <span className={styles.cardTitle}>🤖 Claude Code CLI 配置</span>

            <div style={{ marginBottom: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: sysInfo?.claude_code_available ? '#2ecc71' : '#666' }} />
              <span style={{ color: '#ddd', fontSize: '0.85rem' }}>
                {sysInfo?.claude_code_available ? `已安装: ${sysInfo?.claude_code_path}` : '未安装 - 请运行 npm install -g @anthropic-ai/claude-code'}
              </span>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.settingsLabel}>Claude 模型</div>
              <div className={styles.apiKeyRow}>
                <select
                  className={styles.apiKeyInput}
                  value={claudeModel}
                  onChange={e => setClaudeModel(e.target.value)}
                  style={{ color: '#F8FAFC', background: '#1E293B', border: '1px solid #334155', padding: '0.5rem', borderRadius: 6 }}
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

            <div className={styles.settingsSection}>
              <div className={styles.settingsLabel}>MCP 工具（逗号分隔）</div>
              <div className={styles.apiKeyRow}>
                <input type="text" className={styles.apiKeyInput} placeholder="bing_search,web_search,paper_search,sequentialthinking" value={claudeMcpTools} onChange={e => setClaudeMcpTools(e.target.value)} />
              </div>
              <div style={{ fontSize: '0.75rem', color: '#666' }}>可用: bing_search, web_search, paper_search, python_execute, sequentialthinking</div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.settingsLabel}>MCP 配置文件路径</div>
              <div className={styles.apiKeyRow}>
                <input type="text" className={styles.apiKeyInput} placeholder="留空则自动搜索" value={claudeMcpConfigPath} onChange={e => setClaudeMcpConfigPath(e.target.value)} />
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.settingsLabel}>温度</div>
              <div className={styles.apiKeyRow}>
                <input type="number" className={styles.apiKeyInput} placeholder="0.3" value={claudeTemperature} onChange={e => setClaudeTemperature(e.target.value)} min="0" max="1" step="0.1" style={{ color: '#F8FAFC', background: '#1E293B', border: '1px solid #334155', padding: '0.5rem', borderRadius: 6 }} />
              </div>
            </div>

            <div className={styles.settingsSection}>
              <div className={styles.settingsLabel}>最大输出 Token</div>
              <div className={styles.apiKeyRow}>
                <input type="number" className={styles.apiKeyInput} placeholder="8192" value={claudeMaxTokens} onChange={e => setClaudeMaxTokens(e.target.value)} min="100" max="32000" style={{ color: '#F8FAFC', background: '#1E293B', border: '1px solid #334155', padding: '0.5rem', borderRadius: 6 }} />
              </div>
            </div>

            <div className={styles.btnRow}>
              <button className={styles.submitBtn} onClick={handleSaveClaudeSettings}>💾 保存 Claude Code 配置</button>
            </div>
          </div>

          {/* 系统信息 */}
          <div className={styles.settingsCard}>
            <span className={styles.cardTitle}>ℹ️ 系统信息</span>
            <div className={styles.noteBox}>
              <strong>📍 访问地址：</strong>
              <code>本机: http://localhost:3000</code><br />
              <code>局域网: 请使用本机 IP:3000</code><br />
              <strong>📖 后端 API 文档：</strong>
              <code>http://localhost:8000/docs</code><br />
              {sysInfo && (
                <>
                  <strong>🔄 版本：</strong><code>v{sysInfo.version}</code><br />
                  <strong>🤖 默认后端：</strong><code>{sysInfo.default_llm_backend}</code><br />
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
