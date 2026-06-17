'use client';

import { useState, useEffect, useCallback } from 'react';

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
      <h2>🐍 环境管理</h2>
      {msg && <div style={{ padding: 10, marginBottom: 12, background: '#fff3cd', borderRadius: 6 }}>{msg}</div>}

      <section style={{ marginBottom: 24, padding: 16, border: '1px solid #ddd', borderRadius: 8 }}>
        <h3>创建新环境</h3>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <select value={newBackend} onChange={(e) => setNewBackend(e.target.value)}>
            {backends.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
          <input
            placeholder="环境名称"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <input
            placeholder="Python 版本"
            value={newPython}
            onChange={(e) => setNewPython(e.target.value)}
          />
          <button onClick={createEnv} disabled={creating || !newName.trim()}>
            {creating ? '创建中...' : '创建'}
          </button>
        </div>
      </section>

      {installTarget && (
        <section style={{ marginBottom: 24, padding: 16, border: '1px solid #ddd', borderRadius: 8, background: '#f8f9fa' }}>
          <h3>安装依赖到 {installTarget.name}</h3>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              placeholder="requirements.txt 路径（留空使用项目默认）"
              value={requirementsPath}
              onChange={(e) => setRequirementsPath(e.target.value)}
              style={{ minWidth: 320 }}
            />
            <button onClick={installReqs} disabled={installing}>{installing ? '安装中...' : '安装'}</button>
            <button onClick={() => setInstallTarget(null)}>取消</button>
          </div>
        </section>
      )}

      <section>
        <h3>环境列表</h3>
        {loading ? (
          <p>加载中...</p>
        ) : envs.length === 0 ? (
          <p>暂无环境</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f0f0f0' }}>
                <th style={{ padding: 8, border: '1px solid #ddd' }}>名称</th>
                <th style={{ padding: 8, border: '1px solid #ddd' }}>后端</th>
                <th style={{ padding: 8, border: '1px solid #ddd' }}>Python</th>
                <th style={{ padding: 8, border: '1px solid #ddd' }}>路径</th>
                <th style={{ padding: 8, border: '1px solid #ddd' }}>状态</th>
                <th style={{ padding: 8, border: '1px solid #ddd' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {envs.map((env) => (
                <tr key={`${env.backend}-${env.name}`}>
                  <td style={{ padding: 8, border: '1px solid #ddd' }}>{env.name}</td>
                  <td style={{ padding: 8, border: '1px solid #ddd' }}>{env.backend}</td>
                  <td style={{ padding: 8, border: '1px solid #ddd' }}>{env.python_version}</td>
                  <td style={{ padding: 8, border: '1px solid #ddd', fontSize: 12, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>{env.path}</td>
                  <td style={{ padding: 8, border: '1px solid #ddd' }}>
                    {env.is_active ? <span style={{ color: 'green', fontWeight: 'bold' }}>● 激活</span> : '未激活'}
                  </td>
                  <td style={{ padding: 8, border: '1px solid #ddd' }}>
                    <button onClick={() => activateEnv(env.backend, env.name)} disabled={env.is_active}>
                      激活
                    </button>{' '}
                    <button onClick={() => setInstallTarget({ backend: env.backend, name: env.name })}>
                      安装依赖
                    </button>{' '}
                    <button onClick={() => deleteEnv(env.backend, env.name)} style={{ color: 'red' }}>
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
