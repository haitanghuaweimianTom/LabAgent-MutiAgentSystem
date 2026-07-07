'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTheme } from '@/hooks/useTheme';
import { apiBase } from '@/lib/api';

interface MCPServer {
  name: string;
  command: string;
  args: string[];
  enabled: boolean;
  description: string;
  url?: string;
  headers?: Record<string, string>;
  tags?: string[];
  disabled_tools?: string[];
  apps?: Record<string, boolean>;
  install_source?: string;
  server_type?: string;
  is_trusted?: boolean;
}

interface MCPTool {
  name: string;
  server: string;
  description: string;
}

const TRANSPORT_TYPES = [
  { id: 'stdio', label: 'STDIO', desc: '本地进程通信' },
  { id: 'sse', label: 'SSE', desc: 'Server-Sent Events' },
  { id: 'streamableHttp', label: 'HTTP', desc: 'Streamable HTTP' },
];

// v5.4.0: 所有 11 个 Agent（不含 orchestrator）
const ALL_AGENTS = [
  { id: 'research_agent', label: '研究员', desc: '搜集相关资料、文献、数据' },
  { id: 'analyzer_agent', label: '分析师', desc: '理解问题、分解任务、制定策略' },
  { id: 'modeler_agent', label: '建模师', desc: '建立数学模型、设计算法' },
  { id: 'solver_agent', label: '求解器', desc: '编程求解、结果验证、数据处理' },
  { id: 'writer_agent', label: '写作专家', desc: '按章节独立生成完整 LaTeX 论文' },
  { id: 'data_agent', label: '数据分析师', desc: '上传、分析、预处理数据' },
  { id: 'algorithm_engineer_agent', label: '算法工程师', desc: '为 CCF-A 论文设计算法/方法' },
  { id: 'financial_analyst_agent', label: '金融分析师', desc: '建立金融数学、量化模型' },
  { id: 'figure_agent', label: '科研绘图师', desc: '生成发表级质量图表' },
  { id: 'peer_review_agent', label: '模拟审稿人', desc: '四维度评分 + 修改建议' },
  { id: 'experimentation_agent', label: '实验设计专家', desc: '设计严谨可复现的实验方案' },
];

// MCP 服务器定义（供用户为每个 Agent 勾选）
// 每个服务器对应一个外部进程，提供一组相关工具
const MCP_SERVERS = [
  {
    id: 'web_search',
    label: '🔍 网页搜索',
    desc: 'DuckDuckGo / Brave 实时搜索',
    tools: ['web_search'],
    tags: ['search', 'web'],
    recommended: true,
  },
  {
    id: 'scholarly_research',
    label: '📚 学术搜索',
    desc: 'Google Scholar, ArXiv, PubMed, JSTOR 论文搜索',
    tools: ['paper_search', 'scholar_search'],
    tags: ['search', 'academic'],
    recommended: true,
  },
  {
    id: 'arxiv_server',
    label: '📄 arXiv 服务',
    desc: 'arXiv 论文搜索、下载、摘要、引用图谱',
    tools: ['arxiv_search', 'arxiv_download', 'arxiv_abstract', 'arxiv_citation'],
    tags: ['search', 'academic', 'arxiv'],
    recommended: false,
  },
  {
    id: 'file_system',
    label: '📁 文件系统',
    desc: '文件读写、代码执行、LaTeX 编译（所有 Agent 必备）',
    tools: ['file_read', 'file_write', 'code_execute', 'latex_compile'],
    tags: ['filesystem'],
    recommended: true,
  },
];

export default function McpManager() {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [agentToolsMap, setAgentToolsMap] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const { theme } = useTheme();
  const dark = theme === 'dark';
  const [msg, setMsg] = useState('');
  const [savingAgent, setSavingAgent] = useState<string | null>(null);

  // Add server form
  const [showAddServer, setShowAddServer] = useState(false);
  const [newServer, setNewServer] = useState({
    name: '', command: '', args: '', description: '',
    url: '', server_type: 'stdio',
  });

  // Add tool form
  const [showAddTool, setShowAddTool] = useState(false);
  const [newTool, setNewTool] = useState({ name: '', server: '', description: '' });

  // JSON import/export
  const [showJsonImport, setShowJsonImport] = useState(false);
  const [jsonText, setJsonText] = useState('');
  const [importingJson, setImportingJson] = useState(false);

  // Agent-MCP config tab
  const [activeSection, setActiveSection] = useState<'servers' | 'tools' | 'agents'>('servers');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [srvRes, toolRes, agentRes] = await Promise.all([
        fetch(apiBase() + '/mcp/servers'),
        fetch(apiBase() + '/mcp/tools'),
        fetch(apiBase() + '/mcp/agent-tools'),
      ]);
      if (srvRes.ok) setServers(await srvRes.json());
      if (toolRes.ok) setTools(await toolRes.json());
      if (agentRes.ok) {
        const data = await agentRes.json();
        setAgentToolsMap(data);
      }
    } catch { } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleToggleServer = async (name: string, enabled: boolean) => {
    try {
      await fetch(apiBase() + '/mcp/servers/' + name + '/toggle?enabled=' + !enabled, { method: 'PUT' });
      setMsg(`${name} ${!enabled ? '已启用' : '已禁用'}`);
      load();
    } catch { setMsg('操作失败'); }
  };

  const handleAddServer = async () => {
    if (!newServer.name) { setMsg('名称不能为空'); return; }
    if (newServer.server_type === 'stdio' && !newServer.command) { setMsg('STDIO 类型需要命令'); return; }
    if ((newServer.server_type === 'sse' || newServer.server_type === 'streamableHttp') && !newServer.url) { setMsg('HTTP/SSE 类型需要 URL'); return; }
    try {
      const argsList = newServer.args.split(' ').filter(s => s);
      const body: Record<string, any> = {
        name: newServer.name,
        description: newServer.description,
        server_type: newServer.server_type,
      };
      if (newServer.server_type === 'stdio') {
        body.command = newServer.command;
        body.args = argsList;
      } else {
        body.url = newServer.url;
      }
      const res = await fetch(apiBase() + '/mcp/servers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.success) { setMsg(`服务器 ${newServer.name} 已添加`); setShowAddServer(false); setNewServer({ name: '', command: '', args: '', description: '', url: '', server_type: 'stdio' }); load(); }
      else { setMsg(data.detail || '添加失败'); }
    } catch { setMsg('添加失败'); }
  };

  const handleAddTool = async () => {
    if (!newTool.name) { setMsg('工具名称不能为空'); return; }
    try {
      const res = await fetch(apiBase() + '/mcp/tools', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newTool),
      });
      const data = await res.json();
      if (data.success) { setMsg(`工具 ${newTool.name} 已添加`); setShowAddTool(false); setNewTool({ name: '', server: '', description: '' }); load(); }
      else { setMsg(data.detail || '添加失败'); }
    } catch { setMsg('添加失败'); }
  };

  const handleExportConfig = async () => {
    try {
      const res = await fetch(apiBase() + '/mcp/export-json');
      if (res.ok) {
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'mcp_servers.json'; a.click();
        URL.revokeObjectURL(url);
        setMsg('MCP 配置已导出');
      }
    } catch { setMsg('导出失败'); }
  };

  const handleJsonImport = async () => {
    if (!jsonText.trim()) { setMsg('请输入 JSON 内容'); return; }
    let parsed: any;
    try { parsed = JSON.parse(jsonText); } catch { setMsg('JSON 格式错误，请检查后重试'); return; }
    if (!parsed.mcpServers || typeof parsed.mcpServers !== 'object') {
      setMsg('缺少 mcpServers 字段'); return;
    }
    setImportingJson(true);
    try {
      const res = await fetch(apiBase() + '/mcp/import-json', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed),
      });
      const data = await res.json();
      if (data.success) {
        setMsg(`✓ 成功导入 ${data.imported?.length || 0} 个服务器` + (data.failed?.length ? `，${data.failed.length} 个失败` : ''));
        setShowJsonImport(false);
        setJsonText('');
        load();
      } else {
        setMsg(data.detail || '导入失败');
      }
    } catch { setMsg('导入失败'); } finally { setImportingJson(false); }
  };

  // 判断 Agent 是否启用了某个 MCP 服务器
  const isServerEnabledForAgent = (agentId: string, serverId: string): boolean => {
    const agentTools = agentToolsMap[agentId] || [];
    const server = MCP_SERVERS.find(s => s.id === serverId);
    if (!server) return false;
    // 如果 Agent 配置了该服务器的任意一个工具，则认为启用了该服务器
    return server.tools.some(t => agentTools.includes(t));
  };

  // 切换 Agent 的 MCP 服务器
  const toggleAgentServer = (agentId: string, serverId: string) => {
    const server = MCP_SERVERS.find(s => s.id === serverId);
    if (!server) return;

    setAgentToolsMap(prev => {
      const current = prev[agentId] || [];
      const hasServer = server.tools.some(t => current.includes(t));
      let next: string[];
      if (hasServer) {
        // 禁用：移除该服务器的所有工具
        next = current.filter(t => !server.tools.includes(t));
      } else {
        // 启用：添加该服务器的所有工具
        next = Array.from(new Set([...current, ...server.tools]));
      }
      return { ...prev, [agentId]: next };
    });
  };

  // 保存单个 Agent 的工具配置
  const saveAgentTools = async (agentId: string) => {
    setSavingAgent(agentId);
    try {
      const tools = agentToolsMap[agentId] || [];
      const res = await fetch(apiBase() + '/mcp/agent-tools/' + agentId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tools }),
      });
      const data = await res.json();
      if (data.success) {
        setMsg(`✓ ${ALL_AGENTS.find(a => a.id === agentId)?.label || agentId} 配置已保存`);
      } else {
        setMsg(data.detail || '保存失败');
      }
    } catch {
      setMsg('保存失败');
    } finally {
      setSavingAgent(null);
    }
  };

  // 一键应用推荐配置
  const applyRecommended = async () => {
    setMsg('正在应用推荐配置...');
    try {
      for (const agent of ALL_AGENTS) {
        const recommendedServers = MCP_SERVERS.filter(s => s.recommended);
        const recommendedTools = Array.from(new Set(recommendedServers.flatMap(s => s.tools)));
        setAgentToolsMap(prev => ({ ...prev, [agent.id]: recommendedTools }));
        await fetch(apiBase() + '/mcp/agent-tools/' + agent.id, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tools: recommendedTools }),
        });
      }
      setMsg('✓ 已为所有 Agent 应用推荐配置');
      load();
    } catch {
      setMsg('批量配置失败');
    }
  };

  // 获取 Agent 当前启用的服务器列表
  const getEnabledServersForAgent = (agentId: string): string[] => {
    const agentTools = agentToolsMap[agentId] || [];
    return MCP_SERVERS.filter(s => s.tools.some(t => agentTools.includes(t))).map(s => s.id);
  };

  if (loading) return <div style={{ color: dark ? '#cbd5e1' : '#aaa', textAlign: 'center', padding: '2rem' }}>加载中...</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Section tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {[
          { id: 'servers' as const, label: '🔗 MCP 服务器' },
          { id: 'tools' as const, label: '🔧 MCP 工具' },
          { id: 'agents' as const, label: '🤖 Agent 工具配置' },
        ].map(sec => (
          <button
            key={sec.id}
            onClick={() => setActiveSection(sec.id)}
            style={{
              padding: '0.5rem 1.2rem',
              background: activeSection === sec.id ? 'rgba(52,152,219,0.15)' : 'rgba(255,255,255,0.05)',
              border: `1px solid ${activeSection === sec.id ? 'rgba(52,152,219,0.4)' : 'rgba(255,255,255,0.1)'}`,
              borderRadius: 8,
              color: activeSection === sec.id ? '#3498db' : '#aaa',
              cursor: 'pointer',
              fontWeight: activeSection === sec.id ? 600 : 400,
              fontSize: '0.9rem',
            }}
          >
            {sec.label}
          </button>
        ))}
      </div>

      {msg && (
        <div style={{ fontSize: '0.85rem', color: msg.includes('✓') ? '#2ecc71' : '#e74c3c', textAlign: 'center' }}>
          {msg}
        </div>
      )}

      {/* ===== MCP Servers ===== */}
      {activeSection === 'servers' && (
        <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <span style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 600 }}>🔗 MCP 服务器</span>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button onClick={() => setShowJsonImport(!showJsonImport)} style={{ padding: '0.4rem 0.8rem', background: 'rgba(241,196,15,0.15)', border: '1px solid rgba(241,196,15,0.3)', borderRadius: 6, color: '#f1c40f', fontSize: '0.78rem', cursor: 'pointer' }}>📋 JSON 导入</button>
              <button onClick={handleExportConfig} style={{ padding: '0.4rem 0.8rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 6, color: '#3498db', fontSize: '0.78rem', cursor: 'pointer' }}>💾 导出</button>
              <button onClick={() => setShowAddServer(!showAddServer)} style={{ padding: '0.4rem 0.8rem', background: 'rgba(46,204,113,0.15)', border: '1px solid rgba(46,204,113,0.3)', borderRadius: 6, color: '#2ecc71', fontSize: '0.78rem', cursor: 'pointer' }}>+ 添加服务器</button>
            </div>
          </div>

          {/* JSON import */}
          {showJsonImport && (
            <div style={{ background: 'rgba(0,0,0,0.2)', borderRadius: 8, padding: '1rem', marginBottom: '1rem' }}>
              <span style={{ color: '#f1c40f', fontSize: '0.9rem', fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>📋 粘贴 MCP JSON（Cherry Studio / Claude Desktop 格式）</span>
              <textarea
                value={jsonText}
                onChange={e => setJsonText(e.target.value)}
                rows={8}
                placeholder={`{\n  "mcpServers": {\n    "server_name": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-xxx"],\n      "env": {"API_KEY": "xxx"}\n    }\n  }\n}`}
                style={{ width: '100%', padding: '0.75rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.85rem', fontFamily: 'monospace', resize: 'vertical', boxSizing: 'border-box' }}
              />
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.8rem' }}>
                <button onClick={handleJsonImport} disabled={importingJson} style={{ padding: '0.5rem 1.2rem', background: 'linear-gradient(135deg, #f1c40f, #e67e22)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
                  {importingJson ? '导入中...' : '确认导入'}
                </button>
                <button onClick={() => { setShowJsonImport(false); setJsonText(''); }} style={{ padding: '0.5rem 1.2rem', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: dark ? '#cbd5e1' : '#aaa', cursor: 'pointer' }}>
                  取消
                </button>
              </div>
            </div>
          )}

          {showAddServer && (
            <div style={{ background: 'rgba(0,0,0,0.2)', borderRadius: 8, padding: '1rem', marginBottom: '1rem' }}>
              <div style={{ marginBottom: '0.8rem' }}>
                <div style={{ color: dark ? '#e2e8f0' : '#ddd', fontSize: '0.85rem', marginBottom: '0.5rem' }}>传输类型</div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  {TRANSPORT_TYPES.map(tt => (
                    <button
                      key={tt.id}
                      onClick={() => setNewServer(s => ({ ...s, server_type: tt.id }))}
                      style={{
                        padding: '0.4rem 0.7rem',
                        background: newServer.server_type === tt.id ? 'rgba(52,152,219,0.2)' : 'rgba(0,0,0,0.2)',
                        border: `1px solid ${newServer.server_type === tt.id ? 'rgba(52,152,219,0.5)' : 'rgba(255,255,255,0.1)'}`,
                        borderRadius: 8,
                        color: newServer.server_type === tt.id ? '#3498db' : '#aaa',
                        cursor: 'pointer',
                        fontSize: '0.8rem',
                      }}
                    >
                      {tt.label} — {tt.desc}
                    </button>
                  ))}
                </div>
              </div>
              <input value={newServer.name} onChange={e => setNewServer(s => ({ ...s, name: e.target.value }))} placeholder="服务器名称" style={{ width: '100%', padding: '0.6rem', marginBottom: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }} />
              {newServer.server_type === 'stdio' ? (
                <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <input value={newServer.command} onChange={e => setNewServer(s => ({ ...s, command: e.target.value }))} placeholder="命令 (如 npx)" style={{ flex: 1, padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }} />
                  <input value={newServer.args} onChange={e => setNewServer(s => ({ ...s, args: e.target.value }))} placeholder="参数 (空格分隔)" style={{ flex: 1, padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }} />
                </div>
              ) : (
                <input value={newServer.url} onChange={e => setNewServer(s => ({ ...s, url: e.target.value }))} placeholder="URL (如 http://localhost:3000/mcp)" style={{ width: '100%', padding: '0.6rem', marginBottom: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }} />
              )}
              <input value={newServer.description} onChange={e => setNewServer(s => ({ ...s, description: e.target.value }))} placeholder="描述" style={{ width: '100%', padding: '0.6rem', marginBottom: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }} />
              <button onClick={handleAddServer} style={{ padding: '0.5rem 1rem', background: 'linear-gradient(135deg, #2ecc71, #27ae60)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>添加</button>
            </div>
          )}

          {servers.length === 0 && <div style={{ color: dark ? '#94a3b8' : '#666', textAlign: 'center' }}>暂无 MCP 服务器</div>}
          {servers.map(srv => {
            const sType = srv.server_type || 'stdio';
            const isHttp = sType !== 'stdio';
            const installSource = srv.install_source || 'manual';
            return (
              <div key={srv.name} style={{ padding: '0.8rem', marginBottom: '0.5rem', background: srv.enabled ? 'rgba(46,204,113,0.05)' : 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: srv.enabled ? '#2ecc71' : '#666' }} />
                  <span style={{ color: '#fff', fontWeight: 600 }}>{srv.name}</span>
                  <span style={{ padding: '0.1rem 0.4rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 4, color: '#3498db', fontSize: '0.7rem' }}>
                    {TRANSPORT_TYPES.find(t => t.id === sType)?.label || 'STDIO'}
                  </span>
                  <span style={{ padding: '0.1rem 0.4rem', background: installSource === 'builtin' ? 'rgba(46,204,113,0.15)' : 'rgba(255,255,255,0.08)', border: `1px solid ${installSource === 'builtin' ? 'rgba(46,204,113,0.3)' : 'rgba(255,255,255,0.1)'}`, borderRadius: 4, color: installSource === 'builtin' ? '#2ecc71' : '#888', fontSize: '0.7rem' }}>
                    {installSource === 'builtin' ? '内置' : '手动'}
                  </span>
                </div>
                <div style={{ marginTop: '0.4rem', marginLeft: '1.2rem' }}>
                  {isHttp ? (
                    <code style={{ color: dark ? '#cbd5e1' : '#aaa', fontSize: '0.8rem' }}>{srv.url}</code>
                  ) : (
                    <code style={{ color: dark ? '#cbd5e1' : '#aaa', fontSize: '0.8rem' }}>{srv.command} {(srv.args || []).join(' ')}</code>
                  )}
                </div>
                {(srv.tags && srv.tags.length > 0) && (
                  <div style={{ display: 'flex', gap: '0.3rem', marginTop: '0.4rem', marginLeft: '1.2rem', flexWrap: 'wrap' }}>
                    {srv.tags.map((tag: string) => (
                      <span key={tag} style={{ padding: '0.1rem 0.4rem', background: 'rgba(155,89,182,0.1)', border: '1px solid rgba(155,89,182,0.2)', borderRadius: 4, color: '#9b59b6', fontSize: '0.7rem' }}>#{tag}</span>
                    ))}
                  </div>
                )}
                {(srv.disabled_tools && srv.disabled_tools.length > 0) && (
                  <div style={{ marginTop: '0.4rem', marginLeft: '1.2rem', color: dark ? '#94a3b8' : '#888', fontSize: '0.75rem' }}>
                    禁用工具: {srv.disabled_tools.join(', ')}
                  </div>
                )}
                <span style={{ color: dark ? '#94a3b8' : '#888', fontSize: '0.85rem', flex: 1, display: 'block', marginTop: '0.3rem' }}>{srv.description}</span>
                <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.4rem', marginLeft: '1.2rem' }}>
                  <button onClick={() => handleToggleServer(srv.name, srv.enabled)} style={{ padding: '0.3rem 0.6rem', background: srv.enabled ? 'rgba(231,76,60,0.15)' : 'rgba(46,204,113,0.15)', border: `1px solid ${srv.enabled ? 'rgba(231,76,60,0.3)' : 'rgba(46,204,113,0.3)'}`, borderRadius: 6, color: srv.enabled ? '#e74c3c' : '#2ecc71', fontSize: '0.75rem', cursor: 'pointer' }}>
                    {srv.enabled ? '禁用' : '启用'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ===== MCP Tools ===== */}
      {activeSection === 'tools' && (
        <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <span style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 600 }}>🔧 MCP 工具</span>
            <button onClick={() => setShowAddTool(!showAddTool)} style={{ padding: '0.4rem 0.8rem', background: 'rgba(46,204,113,0.15)', border: '1px solid rgba(46,204,113,0.3)', borderRadius: 6, color: '#2ecc71', fontSize: '0.78rem', cursor: 'pointer' }}>+ 添加工具</button>
          </div>

          {showAddTool && (
            <div style={{ background: 'rgba(0,0,0,0.2)', borderRadius: 8, padding: '1rem', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <input value={newTool.name} onChange={e => setNewTool(s => ({ ...s, name: e.target.value }))} placeholder="工具名称" style={{ flex: 1, padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }} />
                <select value={newTool.server} onChange={e => setNewTool(s => ({ ...s, server: e.target.value }))} style={{ flex: 1, padding: '0.6rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }}>
                  <option value="">选择服务器</option>
                  {servers.map(s => <option key={s.name} value={s.name}>{s.name}</option>)}
                </select>
              </div>
              <input value={newTool.description} onChange={e => setNewTool(s => ({ ...s, description: e.target.value }))} placeholder="描述" style={{ width: '100%', padding: '0.6rem', marginBottom: '0.5rem', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, color: '#e0e0e0', fontSize: '0.9rem' }} />
              <button onClick={handleAddTool} style={{ padding: '0.5rem 1rem', background: 'linear-gradient(135deg, #2ecc71, #27ae60)', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>添加</button>
            </div>
          )}

          {tools.length === 0 && <div style={{ color: dark ? '#94a3b8' : '#666', textAlign: 'center' }}>暂无 MCP 工具</div>}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '0.5rem' }}>
            {tools.map(tool => (
              <div key={tool.name} style={{ padding: '0.6rem', background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8 }}>
                <div style={{ color: '#fff', fontWeight: 600 }}>{tool.name}</div>
                <div style={{ color: dark ? '#94a3b8' : '#888', fontSize: '0.8rem' }}>服务器: {tool.server}</div>
                <div style={{ color: dark ? '#cbd5e1' : '#aaa', fontSize: '0.85rem' }}>{tool.description}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ===== Agent-MCP 配置 ===== */}
      {activeSection === 'agents' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* 说明 */}
          <div style={{ background: 'rgba(52,152,219,0.08)', border: '1px solid rgba(52,152,219,0.2)', borderRadius: 14, padding: '1.2rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <span style={{ fontSize: '1rem', color: '#3498db', fontWeight: 600 }}>🤖 Agent-MCP 配置</span>
                <p style={{ color: '#94A3B8', fontSize: '0.85rem', margin: '0.3rem 0 0 0' }}>
                  为每个 Agent 选择可用的 MCP 服务器。服务器 = 一组相关工具的外部进程。
                </p>
                <p style={{ color: '#64748B', fontSize: '0.8rem', margin: '0.2rem 0 0 0' }}>
                  例如：勾选「网页搜索」= 该 Agent 可以使用 web_search 工具；勾选「文件系统」= 该 Agent 可以读写文件。
                </p>
              </div>
              <button
                onClick={applyRecommended}
                style={{
                  padding: '0.6rem 1.2rem',
                  background: 'linear-gradient(135deg, #3498db, #2980b9)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                }}
              >
                应用推荐配置
              </button>
            </div>
          </div>

          {/* 每个 Agent 的配置卡片 */}
          {ALL_AGENTS.map(agent => {
            const enabledServers = getEnabledServersForAgent(agent.id);
            const hasFileSystem = enabledServers.includes('file_system');
            return (
              <div key={agent.id} style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: '1.2rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.6rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                    <span style={{ fontSize: '1rem', color: '#fff', fontWeight: 600 }}>{agent.label}</span>
                    <span style={{ fontSize: '0.8rem', color: '#64748B' }}>{agent.id}</span>
                    {!hasFileSystem && (
                      <span style={{ padding: '0.1rem 0.4rem', background: 'rgba(243,156,18,0.15)', border: '1px solid rgba(243,156,18,0.3)', borderRadius: 4, color: '#f39c12', fontSize: '0.7rem' }}>
                        缺少文件系统
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() => saveAgentTools(agent.id)}
                    disabled={savingAgent === agent.id}
                    style={{
                      padding: '0.4rem 1rem',
                      background: 'linear-gradient(135deg, #2ecc71, #27ae60)',
                      color: '#fff',
                      border: 'none',
                      borderRadius: 8,
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: '0.85rem',
                      opacity: savingAgent === agent.id ? 0.6 : 1,
                    }}
                  >
                    {savingAgent === agent.id ? '保存中...' : '💾 保存'}
                  </button>
                </div>
                <p style={{ color: '#94A3B8', fontSize: '0.85rem', margin: '0 0 0.8rem 0' }}>{agent.desc}</p>

                {/* MCP 服务器选择 */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.5rem' }}>
                  {MCP_SERVERS.map(server => {
                    const isChecked = enabledServers.includes(server.id);
                    return (
                      <label key={server.id} style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.3rem',
                        padding: '0.6rem',
                        background: isChecked ? 'rgba(52,152,219,0.1)' : 'rgba(0,0,0,0.1)',
                        border: `1px solid ${isChecked ? 'rgba(52,152,219,0.3)' : 'rgba(255,255,255,0.08)'}`,
                        borderRadius: 8,
                        cursor: 'pointer',
                        transition: 'all 0.15s',
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => toggleAgentServer(agent.id, server.id)}
                            style={{ cursor: 'pointer' }}
                          />
                          <span style={{ fontSize: '0.9rem', color: isChecked ? '#3498db' : '#CBD5E1', fontWeight: 600 }}>
                            {server.label}
                          </span>
                          {server.recommended && (
                            <span style={{ padding: '0.05rem 0.3rem', background: 'rgba(46,204,113,0.15)', border: '1px solid rgba(46,204,113,0.3)', borderRadius: 4, color: '#2ecc71', fontSize: '0.7rem' }}>
                              推荐
                            </span>
                          )}
                        </div>
                        <span style={{ fontSize: '0.8rem', color: '#64748B', marginLeft: '1.4rem' }}>{server.desc}</span>
                        <span style={{ fontSize: '0.75rem', color: '#475569', marginLeft: '1.4rem' }}>
                          工具: {server.tools.join(', ')}
                        </span>
                      </label>
                    );
                  })}
                </div>

                {/* 当前已配置工具展示 */}
                {(() => {
                  const currentTools = agentToolsMap[agent.id] || [];
                  if (currentTools.length === 0) return null;
                  return (
                    <div style={{ marginTop: '0.8rem', padding: '0.5rem', background: 'rgba(0,0,0,0.15)', borderRadius: 6 }}>
                      <span style={{ fontSize: '0.8rem', color: '#64748B' }}>已配置工具: </span>
                      {currentTools.map(t => (
                        <span key={t} style={{ display: 'inline-block', padding: '0.1rem 0.4rem', margin: '0.1rem', background: 'rgba(52,152,219,0.15)', border: '1px solid rgba(52,152,219,0.3)', borderRadius: 4, color: '#3498db', fontSize: '0.75rem' }}>{t}</span>
                      ))}
                    </div>
                  );
                })()}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
