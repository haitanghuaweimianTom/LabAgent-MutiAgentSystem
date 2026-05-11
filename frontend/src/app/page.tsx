'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import styles from './page.module.css';

import SystemStatus from './components/SystemStatus';
import ProblemInput from './components/ProblemInput';
import AgentChat from './components/AgentChat';
import FileManager from './components/FileManager';
import TaskHistory from './components/TaskHistory';

declare global {
  interface Window {
    __API_BASE__?: string;
  }
}

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

// Provider 标签映射
function getProviderLabel(id: string): string {
  const labels: Record<string, string> = {
    claude_cli: 'Claude CLI',
    anthropic: 'Anthropic',
    openai: 'OpenAI',
    gemini: 'Gemini',
    ollama: 'Ollama',
  };
  return labels[id] || id;
}

// 单个 Provider 配置卡片
function ProviderConfigCard({
  id, name, apiKeySet, defaultBaseUrl, defaultModel,
  currentBaseUrl, currentModel, docsUrl, docsLabel,
  testFn, testing, testResult, noApiKey, noBaseUrl,
}: {
  id: string; name: string; apiKeySet?: boolean;
  defaultBaseUrl: string; defaultModel: string;
  currentBaseUrl?: string; currentModel?: string;
  docsUrl: string; docsLabel: string;
  testFn: (id: string) => void; testing: boolean; testResult?: string;
  noApiKey?: boolean; noBaseUrl?: boolean;
}) {
  return (
    <div className={styles.settingsSection}>
      <div className={styles.settingsLabel}>
        {name}
        {apiKeySet && <span style={{ color: '#2ecc71', marginLeft: 8, fontSize: 12 }}>✓ 已配置</span>}
      </div>
      {!noApiKey && (
        <div className={styles.apiKeyRow}>
          <input
            type="password"
            className={styles.apiKeyInput}
            placeholder={`${name} API Key`}
            id={`${id}_api_key`}
          />
        </div>
      )}
      {!noBaseUrl && (
        <div className={styles.apiKeyRow}>
          <input
            type="text"
            className={styles.apiKeyInput}
            placeholder={defaultBaseUrl}
            defaultValue={currentBaseUrl || defaultBaseUrl}
            id={`${id}_base_url`}
          />
        </div>
      )}
      <div className={styles.apiKeyRow}>
        <input
          type="text"
          className={styles.apiKeyInput}
          placeholder={defaultModel}
          defaultValue={currentModel || defaultModel}
          id={`${id}_model`}
        />
      </div>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
        <button
          className={styles.testBtn}
          onClick={() => testFn(id)}
          disabled={testing}
        >
          {testing ? '测试中...' : '🧪 测试连接'}
        </button>
        {testResult && (
          <span style={{ fontSize: '0.8rem', color: testResult.startsWith('✓') ? '#2ecc71' : '#e74c3c' }}>
            {testResult}
          </span>
        )}
        <span style={{ fontSize: '0.75rem', color: '#666' }}>
          <a href={docsUrl} target="_blank" rel="noopener" style={{ color: '#3498db' }}>{docsLabel}</a>
        </span>
      </div>
    </div>
  );
}

interface Message {
  id: string;
  sender: string;
  sender_label: string;
  content: string;
  type: string;
  timestamp: string;
}

interface ProviderInfo {
  api_key_set?: boolean;
  base_url?: string;
  model?: string;
  available?: boolean;
}

interface SettingsData {
  minimax_api_key_set?: boolean;
  kimi_api_key_set?: boolean;
  kimi_base_url?: string;
  default_model?: string;
  api_base_url?: string;
  providers?: Record<string, ProviderInfo>;
  default_llm_provider?: string;
}

export default function Home() {
  const [tab, setTab] = useState<'dashboard' | 'generate' | 'files' | 'history' | 'settings'>('dashboard');

  // Task state
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string>('idle');
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [eventSource, setEventSource] = useState<EventSource | null>(null);

  // Pause/Resume
  const [paused, setPaused] = useState(false);
  const [resuming, setResuming] = useState(false);

  // Submitting
  const [submitting, setSubmitting] = useState(false);

  // Settings
  const [settingsMsg, setSettingsMsg] = useState('');
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [defaultProvider, setDefaultProvider] = useState('claude_cli');
  const [testingProvider, setTestingProvider] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});

  const handleSubmit = async (params: {
    problemText: string;
    projectName: string;
    workflow: string;
    template: string;
    mode: string;
    useCritique: boolean;
  }) => {
    setSubmitting(true);
    try {
      const res = await fetch(apiBase() + '/tasks/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          problem_text: params.problemText,
          project_name: params.projectName,
          mode: params.mode,
          options: {
            workflow: params.workflow,
            template: params.template,
            use_critique: params.useCritique,
          },
        }),
      });
      const data = await res.json();
      setTaskId(data.task_id);
      setTaskStatus('running');
      setProgress(0);
      setCurrentStep('等待启动');
      setMessages([]);
      setPaused(false);
      setTab('generate');
      startSSE(data.task_id);
    } catch (err) {
      console.error(err);
      alert('提交失败，请确认后端已启动');
    } finally {
      setSubmitting(false);
    }
  };

  // ========== SSE 流 ==========
  const startSSE = (id: string) => {
    if (eventSource) eventSource.close();
    const es = new EventSource(apiBase() + '/tasks/' + id + '/stream');
    setEventSource(es);

    const msgPoll = setInterval(async () => {
      try {
        const res = await fetch(apiBase() + '/tasks/' + id + '/messages');
        if (res.ok) {
          const msgs = await res.json();
          setMessages(
            msgs.map((m: any) => ({
              id: m.id,
              sender: m.sender,
              sender_label: m.sender_label || getTeamLabel(m.sender) || m.sender,
              content: m.content,
              type: m.type || 'text',
              timestamp: m.timestamp,
            }))
          );
        }
      } catch {}
    }, 1000);

    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        setTaskStatus(d.status);
        setProgress(d.progress || 0);
        setCurrentStep(d.current_step || '');
        if (d.status === 'paused') {
          setPaused(true);
          es.close();
          clearInterval(msgPoll);
        }
        if (['completed', 'failed', 'cancelled'].includes(d.status)) {
          es.close();
          clearInterval(msgPoll);
        }
      } catch {}
    };

    es.onerror = () => {
      es.close();
      clearInterval(msgPoll);
    };
  };

  // ========== 暂停/恢复 ==========
  const handlePause = async () => {
    if (!taskId) return;
    try {
      await fetch(apiBase() + '/tasks/' + taskId + '/pause', { method: 'POST' });
      setPaused(true);
    } catch {}
  };

  const handleResume = async () => {
    if (!taskId) return;
    setResuming(true);
    try {
      await fetch(apiBase() + '/tasks/' + taskId + '/resume', { method: 'POST' });
      setPaused(false);
      startSSE(taskId);
    } catch {} finally {
      setResuming(false);
    }
  };

  // ========== 加载设置 ==========
  useEffect(() => {
    fetch(apiBase() + '/settings')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          setSettings(d);
          setDefaultProvider(d.default_llm_provider || 'claude_cli');
          setSettingsLoaded(true);
        }
      })
      .catch(() => { setSettingsLoaded(true); });
  }, []);

  // ========== 测试Provider ==========
  const handleTestProvider = async (providerId: string) => {
    setTestingProvider(providerId);
    setTestResults(prev => ({ ...prev, [providerId]: '测试中...' }));
    try {
      const res = await fetch(apiBase() + '/debug/test-llm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: providerId }),
      });
      const data = await res.json();
      if (data.success) {
        setTestResults(prev => ({ ...prev, [providerId]: `✓ 成功: ${data.response?.slice(0, 50)}` }));
      } else {
        setTestResults(prev => ({ ...prev, [providerId]: `✗ ${data.error || '未知错误'}` }));
      }
    } catch {
      setTestResults(prev => ({ ...prev, [providerId]: '✗ 连接失败' }));
    } finally {
      setTestingProvider(null);
    }
  };

  // ========== 保存设置 ==========
  const handleSaveSettings = async () => {
    const payload: Record<string, string> = {};
    // Collect provider configs from DOM
    const providerConfigs: Record<string, Record<string, string>> = {};
    for (const pid of ['anthropic', 'openai', 'gemini', 'ollama']) {
      const keyEl = document.getElementById(`${pid}_api_key`) as HTMLInputElement;
      const urlEl = document.getElementById(`${pid}_base_url`) as HTMLInputElement;
      const modelEl = document.getElementById(`${pid}_model`) as HTMLInputElement;
      if (keyEl?.value.trim()) {
        if (pid === 'ollama') {
          // Ollama doesn't need API key
        } else {
          payload[`${pid}_api_key`] = keyEl.value.trim();
        }
      }
      if (urlEl?.value.trim()) payload[`${pid}_base_url`] = urlEl.value.trim();
      if (modelEl?.value.trim()) payload[`${pid}_model`] = modelEl.value.trim();
    }

    payload.default_llm_provider = defaultProvider;

    // Also save legacy keys for backward compatibility
    const minimaxInput = document.getElementById('minimax_api_key') as HTMLInputElement;
    const kimiInput = document.getElementById('kimi_api_key') as HTMLInputElement;
    const kimiUrlInput = document.getElementById('kimi_base_url') as HTMLInputElement;
    if (minimaxInput?.value.trim()) payload.minimax_api_key = minimaxInput.value.trim();
    if (kimiInput?.value.trim()) payload.kimi_api_key = kimiInput.value.trim();
    if (kimiUrlInput?.value.trim()) payload.kimi_base_url = kimiUrlInput.value.trim();

    try {
      const res = await fetch(apiBase() + '/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.success) {
        setSettingsMsg('✓ 设置保存成功！Agent已重新初始化');
        // Reload settings
        fetch(apiBase() + '/settings').then(r => r.ok ? r.json() : null).then(d => { if (d) setSettings(d); });
      } else {
        setSettingsMsg('保存失败: ' + (data.message || ''));
      }
    } catch {
      setSettingsMsg('保存失败，请检查后端连接');
    }
  };

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <span className={styles.headerTitle}>数学建模论文全自动生成系统 v2.1</span>
        <p className={styles.subtitle}>Multi-Agent 协作 · 算法智能推荐 · 分段生成 · 显式记忆池</p>
      </header>

      <nav className={styles.nav}>
        {([
          { id: 'dashboard', label: '🏠 首页', desc: '快速开始' },
          { id: 'generate', label: '🚀 生成', desc: taskStatus === 'running' ? `进行中 ${progress}%` : '实时进度' },
          { id: 'files', label: '📁 数据', desc: '文件管理' },
          { id: 'history', label: '📋 历史', desc: '任务记录' },
          { id: 'settings', label: '⚙️ 设置', desc: '系统配置' },
        ] as const).map((t) => (
          <button
            key={t.id}
            className={`${styles.navItem} ${tab === t.id ? styles.navItemActive : ''}`}
            onClick={() => setTab(t.id)}
          >
            <span className={styles.navLabel}>{t.label}</span>
            <span className={styles.navDesc}>{t.desc}</span>
            {t.id === 'generate' && (taskStatus === 'running' || taskStatus === 'phase1' || taskStatus === 'phase2') && (
              <span className={styles.navDot} />
            )}
          </button>
        ))}
      </nav>

      <div className={styles.container}>
        {/* ===== 首页 ===== */}
        {tab === 'dashboard' && (
          <div className={styles.dashboard}>
            <SystemStatus />
            <ProblemInput
              onSubmit={handleSubmit}
              submitting={submitting}
              taskStatus={taskStatus}
              progress={progress}
            />
          </div>
        )}

        {/* ===== 生成 ===== */}
        {tab === 'generate' && (
          <div className={styles.generateLayout}>
            <AgentChat
              messages={messages}
              taskStatus={taskStatus}
              progress={progress}
              currentStep={currentStep}
              paused={paused}
              onPause={handlePause}
              onResume={handleResume}
              resuming={resuming}
            />
          </div>
        )}

        {/* ===== 数据 ===== */}
        {tab === 'files' && (
          <FileManager taskId={taskId} />
        )}

        {/* ===== 历史 ===== */}
        {tab === 'history' && (
          <TaskHistory />
        )}

        {/* ===== 设置 ===== */}
        {tab === 'settings' && (
          <div className={styles.settingsCard}>
            <span className={styles.cardTitle}>⚙️ LLM Provider 配置</span>

            {/* 默认 Provider 选择 */}
            <div className={styles.settingsSection}>
              <div className={styles.settingsLabel}>默认 LLM Provider</div>
              <div className={styles.providerSelector}>
                {['claude_cli', 'anthropic', 'openai', 'gemini', 'ollama'].map(pid => {
                  const isActive = defaultProvider === pid;
                  const prov = settings?.providers?.[pid];
                  const isConfigured = pid === 'claude_cli'
                    ? prov?.available
                    : pid === 'ollama'
                      ? true
                      : prov?.api_key_set;
                  return (
                    <button
                      key={pid}
                      className={`${styles.providerChip} ${isActive ? styles.providerChipActive : ''}`}
                      onClick={() => setDefaultProvider(pid)}
                    >
                      <span className={styles.providerName}>{getProviderLabel(pid)}</span>
                      {isConfigured ? (
                        <span className={styles.providerStatusOk}>✓</span>
                      ) : (
                        <span className={styles.providerStatusOff}>未配置</span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className={styles.divider} />

            {/* Anthropic */}
            <ProviderConfigCard
              id="anthropic"
              name="Anthropic (Claude)"
              apiKeySet={settings?.providers?.anthropic?.api_key_set}
              defaultBaseUrl="https://api.anthropic.com"
              defaultModel="claude-sonnet-4-6-20250514"
              currentBaseUrl={settings?.providers?.anthropic?.base_url}
              currentModel={settings?.providers?.anthropic?.model}
              docsUrl="https://console.anthropic.com/settings/keys"
              docsLabel="Anthropic 控制台"
              testFn={handleTestProvider}
              testing={testingProvider === 'anthropic'}
              testResult={testResults['anthropic']}
            />

            <div className={styles.divider} />

            {/* OpenAI */}
            <ProviderConfigCard
              id="openai"
              name="OpenAI"
              apiKeySet={settings?.providers?.openai?.api_key_set}
              defaultBaseUrl="https://api.openai.com/v1"
              defaultModel="gpt-4o"
              currentBaseUrl={settings?.providers?.openai?.base_url}
              currentModel={settings?.providers?.openai?.model}
              docsUrl="https://platform.openai.com/api-keys"
              docsLabel="OpenAI 控制台"
              testFn={handleTestProvider}
              testing={testingProvider === 'openai'}
              testResult={testResults['openai']}
            />

            <div className={styles.divider} />

            {/* Gemini */}
            <ProviderConfigCard
              id="gemini"
              name="Google Gemini"
              apiKeySet={settings?.providers?.gemini?.api_key_set}
              defaultBaseUrl=""
              defaultModel="gemini-2.5-pro"
              currentBaseUrl=""
              currentModel={settings?.providers?.gemini?.model}
              docsUrl="https://aistudio.google.com/app/apikey"
              docsLabel="Google AI Studio"
              testFn={handleTestProvider}
              testing={testingProvider === 'gemini'}
              testResult={testResults['gemini']}
              noBaseUrl
            />

            <div className={styles.divider} />

            {/* Ollama */}
            <ProviderConfigCard
              id="ollama"
              name="Ollama (本地)"
              apiKeySet={true}
              defaultBaseUrl="http://localhost:11434"
              defaultModel="qwen2.5:latest"
              currentBaseUrl={settings?.providers?.ollama?.base_url}
              currentModel={settings?.providers?.ollama?.model}
              docsUrl="https://ollama.com/library"
              docsLabel="Ollama 模型库"
              testFn={handleTestProvider}
              testing={testingProvider === 'ollama'}
              testResult={testResults['ollama']}
              noApiKey
            />

            <div className={styles.divider} />

            {/* 传统配置：MiniMax / Kimi */}
            <div className={styles.settingsSection}>
              <div className={styles.settingsLabel}>兼容配置（MiniMax / Kimi）</div>
              <div className={styles.apiKeyRow}>
                <input type="password" className={styles.apiKeyInput} placeholder="MiniMax API 密钥" id="minimax_api_key" />
              </div>
              <div className={styles.apiKeyRow}>
                <input type="password" className={styles.apiKeyInput} placeholder="Kimi API 密钥" id="kimi_api_key" />
              </div>
              <div className={styles.apiKeyRow}>
                <input type="text" className={styles.apiKeyInput} placeholder="Kimi Base URL" defaultValue="https://api.kimi.com/coding" id="kimi_base_url" />
              </div>
            </div>

            <div className={styles.btnRow}>
              <button className={styles.submitBtn} onClick={handleSaveSettings}>💾 保存所有设置</button>
            </div>
            {settingsMsg && (
              <div className={styles.settingsMsg} style={{ color: settingsMsg.includes('✓') ? '#2ecc71' : '#e74c3c' }}>
                {settingsMsg}
              </div>
            )}

            <div className={styles.divider} />
            <div className={styles.noteBox}>
              <strong>📍 访问地址：</strong>
              <code>本机: http://localhost:3000</code><br />
              <code>局域网: 请使用本机 IP:3000</code><br />
              <strong>📖 后端 API 文档：</strong>
              <code>http://localhost:8000/docs</code>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

function getTeamLabel(sender: string): string {
  const labels: Record<string, string> = {
    coordinator: '协调者',
    research_agent: '研究员',
    data_agent: '数据分析师',
    analyzer_agent: '分析师',
    modeler_agent: '建模师',
    solver_agent: '求解器',
    writer_agent: '写作专家',
    system: '系统',
    user: '你',
  };
  return labels[sender] || sender;
}
