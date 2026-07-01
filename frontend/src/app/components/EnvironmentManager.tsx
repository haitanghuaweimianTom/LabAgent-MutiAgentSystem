'use client';

import { useState, useEffect, useCallback } from 'react';

// =============================================================
// v5.4.0 深色模式样式常量（替代原 inline 浅色样式）
// =============================================================
const fieldStyle: React.CSSProperties = {
  padding: '6px 10px',
  height: 32,
  background: '#0F172A',
  border: '1px solid #334155',
  borderRadius: 6,
  color: '#F8FAFC',
  fontSize: 14,
  outline: 'none',
};

const thStyle: React.CSSProperties = {
  padding: '8px 10px',
  borderBottom: '1px solid #334155',
  background: '#0F172A',
  color: '#94A3B8',
  fontSize: 12,
  fontWeight: 600,
  textAlign: 'left',
  whiteSpace: 'nowrap',
};

const tdStyle: React.CSSProperties = {
  padding: '8px 10px',
  borderBottom: '1px solid #334155',
  color: '#E2E8F0',
  fontSize: 13,
  verticalAlign: 'middle',
};

const primaryBtnStyle: React.CSSProperties = {
  padding: '6px 16px',
  height: 32,
  background: '#2DD4BF',
  color: '#0F172A',
  border: 'none',
  borderRadius: 6,
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
};

const primaryBtnSmStyle: React.CSSProperties = {
  padding: '4px 10px',
  background: '#2DD4BF',
  color: '#0F172A',
  border: 'none',
  borderRadius: 4,
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: '6px 16px',
  height: 32,
  background: '#1E293B',
  color: '#CBD5E1',
  border: '1px solid #334155',
  borderRadius: 6,
  fontSize: 14,
  cursor: 'pointer',
};

const secondaryBtnSmStyle: React.CSSProperties = {
  padding: '4px 10px',
  background: '#1E293B',
  color: '#CBD5E1',
  border: '1px solid #334155',
  borderRadius: 4,
  fontSize: 12,
  cursor: 'pointer',
};

const dangerBtnSmStyle: React.CSSProperties = {
  padding: '4px 10px',
  background: '#7F1D1D',
  color: '#FCA5A5',
  border: '1px solid #B91C1C',
  borderRadius: 4,
  fontSize: 12,
  cursor: 'pointer',
};

const disabledBtnStyle: React.CSSProperties = {
  padding: '4px 10px',
  background: '#1E293B',
  color: '#475569',
  border: '1px solid #334155',
  borderRadius: 4,
  fontSize: 12,
  cursor: 'not-allowed',
  opacity: 0.6,
};

interface EnvironmentInfo {
  name: string;
  backend: string;
  python_version: string;
  path: string;
  is_active: boolean;
  packages_count: number;
}

interface ActiveEnv {
  name: string | null;
  backend: string | null;
}

const apiBase = () => window.__API_BASE__ || '/api/v1';

export default function EnvironmentManager() {
  const [envs, setEnvs] = useState<EnvironmentInfo[]>([]);
  const [backends, setBackends] = useState<string[]>([]);
  const [active, setActive] = useState<ActiveEnv>({ name: null, backend: null });
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');

  // create form
  const [newBackend, setNewBackend] = useState('conda');
  const [newName, setNewName] = useState('');
  const [newPython, setNewPython] = useState('3.11');
  const [creating, setCreating] = useState(false);

  // install form
  const [installTarget, setInstallTarget] = useState<{ backend: string; name: string } | null>(null);
  const [requirementsPath, setRequirementsPath] = useState('');
  const [installing, setInstalling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [backendsRes, envsRes, activeRes] = await Promise.all([
        fetch(apiBase() + '/environments/backends', { cache: 'no-store' }),
        fetch(apiBase() + '/environments', { cache: 'no-store' }),
        fetch(apiBase() + '/environments/active', { cache: 'no-store' }),
      ]);
      setBackends(await backendsRes.json());
      setEnvs(await envsRes.json());
      setActive(await activeRes.json());
    } catch (e: any) {
      setMsg('加载失败: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const showMsg = (text: string) => {
    setMsg(text);
    setTimeout(() => setMsg(''), 5000);
  };

  const createEnv = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const res = await fetch(apiBase() + '/environments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backend: newBackend, name: newName.trim(), python_version: newPython }),
      });
      if (!res.ok) throw new Error(await res.text());
      showMsg(`环境 ${newName} 创建成功`);
      setNewName('');
      await load();
    } catch (e: any) {
      showMsg('创建失败: ' + e.message);
    } finally {
      setCreating(false);
    }
  };

  const deleteEnv = async (backend: string, name: string) => {
    if (!confirm(`确定删除环境 ${name} (${backend})?`)) return;
    try {
      const res = await fetch(apiBase() + `/environments/${backend}/${name}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(await res.text());
      showMsg(`环境 ${name} 已删除`);
      await load();
    } catch (e: any) {
      showMsg('删除失败: ' + e.message);
    }
  };

  const activateEnv = async (backend: string, name: string) => {
    try {
      const res = await fetch(apiBase() + '/environments/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backend, name }),
      });
      if (!res.ok) throw new Error(await res.text());
      showMsg(`已激活环境 ${name}`);
      await load();
    } catch (e: any) {
      showMsg('激活失败: ' + e.message);
    }
  };

  const installReqs = async () => {
    if (!installTarget) return;
    setInstalling(true);
    try {
      const res = await fetch(apiBase() + '/environments/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          backend: installTarget.backend,
          name: installTarget.name,
          requirements_path: requirementsPath.trim() || null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      showMsg(`依赖安装完成`);
      setInstallTarget(null);
      setRequirementsPath('');
      await load();
    } catch (e: any) {
      showMsg('安装失败: ' + e.message);
    } finally {
      setInstalling(false);
    }
  };

  return (
    <div style={{ padding: 16, maxWidth: 960, margin: '0 auto' }}>
      <h2 style={{ color: '#F8FAFC', fontSize: 20, marginBottom: 12 }}>🐍 环境管理</h2>

      {msg && (
        <div style={{
          padding: '10px 14px',
          marginBottom: 12,
          background: /失败|错误|error|fail/i.test(msg) ? '#7F1D1D' : '#1E3A8A',
          color: '#F8FAFC',
          borderRadius: 6,
          border: '1px solid #334155',
          fontSize: 13,
        }}>
          {msg}
        </div>
      )}

      <section style={{
        marginBottom: 24,
        padding: 16,
        background: '#1E293B',
        border: '1px solid #334155',
        borderRadius: 8,
      }}>
        <h3 style={{ color: '#F8FAFC', fontSize: 16, marginBottom: 12 }}>创建新环境</h3>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <select
            value={newBackend}
            onChange={(e) => setNewBackend(e.target.value)}
            style={fieldStyle}
          >
            {backends.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
          <input
            placeholder="环境名称"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={fieldStyle}
          />
          <input
            placeholder="Python 版本"
            value={newPython}
            onChange={(e) => setNewPython(e.target.value)}
            style={fieldStyle}
          />
          <button
            onClick={createEnv}
            disabled={creating || !newName.trim()}
            style={primaryBtnStyle}
          >
            {creating ? '创建中...' : '创建'}
          </button>
        </div>
      </section>

      {installTarget && (
        <section style={{
          marginBottom: 24,
          padding: 16,
          background: '#1E293B',
          border: '1px solid #334155',
          borderRadius: 8,
        }}>
          <h3 style={{ color: '#F8FAFC', fontSize: 16, marginBottom: 12 }}>
            安装依赖到 {installTarget.name}
          </h3>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              placeholder="requirements.txt 路径（留空使用项目默认）"
              value={requirementsPath}
              onChange={(e) => setRequirementsPath(e.target.value)}
              style={{ ...fieldStyle, minWidth: 320 }}
            />
            <button onClick={installReqs} disabled={installing} style={primaryBtnStyle}>
              {installing ? '安装中...' : '安装'}
            </button>
            <button onClick={() => setInstallTarget(null)} style={secondaryBtnStyle}>
              取消
            </button>
          </div>
        </section>
      )}

      <section>
        <h3 style={{ color: '#F8FAFC', fontSize: 16, marginBottom: 12 }}>环境列表</h3>
        {loading ? (
          <p style={{ color: '#94A3B8', fontSize: 13 }}>加载中...</p>
        ) : envs.length === 0 ? (
          <p style={{ color: '#94A3B8', fontSize: 13 }}>暂无环境</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, color: '#E2E8F0' }}>
            <thead>
              <tr style={{ background: '#0F172A' }}>
                <th style={thStyle}>名称</th>
                <th style={thStyle}>后端</th>
                <th style={thStyle}>Python</th>
                <th style={thStyle}>路径</th>
                <th style={thStyle}>状态</th>
                <th style={{ ...thStyle, minWidth: 220 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {envs.map((env) => (
                <tr key={`${env.backend}-${env.name}`} style={{ borderBottom: '1px solid #334155' }}>
                  <td style={tdStyle}>{env.name}</td>
                  <td style={tdStyle}>{env.backend}</td>
                  <td style={tdStyle}>{env.python_version}</td>
                  <td style={{ ...tdStyle, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'ui-monospace, Menlo, Consolas, monospace', fontSize: 12, color: '#94A3B8' }}>
                    {env.path}
                  </td>
                  <td style={tdStyle}>
                    {env.is_active ? (
                      <span style={{ color: '#4ADE80', fontWeight: 700, fontSize: 13 }}>
                        ● 激活
                      </span>
                    ) : (
                      <span style={{ color: '#94A3B8', fontSize: 13 }}>未激活</span>
                    )}
                  </td>
                  <td style={{ ...tdStyle, minWidth: 220 }}>
                    <button
                      onClick={() => activateEnv(env.backend, env.name)}
                      disabled={env.is_active}
                      style={env.is_active ? disabledBtnStyle : primaryBtnSmStyle}
                    >
                      激活
                    </button>{' '}
                    <button
                      onClick={() => setInstallTarget({ backend: env.backend, name: env.name })}
                      style={secondaryBtnSmStyle}
                    >
                      安装依赖
                    </button>{' '}
                    <button
                      onClick={() => deleteEnv(env.backend, env.name)}
                      style={dangerBtnSmStyle}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
