'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiBase } from '@/lib/api';

// =============================================================
// v5.4.0 样式常量（仅保留 layout，颜色全部走 Tailwind 语义令牌）
// =============================================================
const fieldStyle: React.CSSProperties = {
  padding: '8px 12px',
  height: 40,
  borderRadius: 6,
  fontSize: 14,
  outline: 'none',
};

const thStyle: React.CSSProperties = {
  padding: '10px 12px',
  fontSize: 13,
  fontWeight: 600,
  textAlign: 'left',
  whiteSpace: 'nowrap',
};

const tdStyle: React.CSSProperties = {
  padding: '10px 12px',
  fontSize: 14,
  verticalAlign: 'middle',
};

const primaryBtnStyle: React.CSSProperties = {
  padding: '8px 20px',
  height: 40,
  borderRadius: 6,
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
};

const primaryBtnSmStyle: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: 4,
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: '8px 20px',
  height: 40,
  borderRadius: 6,
  fontSize: 14,
  cursor: 'pointer',
};

const secondaryBtnSmStyle: React.CSSProperties = {
  padding: '4px 10px',
  borderRadius: 4,
  fontSize: 12,
  cursor: 'pointer',
};

const dangerBtnSmStyle: React.CSSProperties = {
  padding: '4px 10px',
  borderRadius: 4,
  fontSize: 12,
  cursor: 'pointer',
};

const disabledBtnStyle: React.CSSProperties = {
  padding: '4px 10px',
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
      <h2 className="text-foreground" style={{ fontSize: 20, marginBottom: 12 }}>🐍 环境管理</h2>

      {msg && (
        <div
          className={
            /失败|错误|error|fail/i.test(msg)
              ? 'border border-error/20 bg-error/10 text-error'
              : 'border border-info/20 bg-info/10 text-info'
          }
          style={{ padding: '10px 14px', marginBottom: 12, borderRadius: 6, fontSize: 13 }}
        >
          {msg}
        </div>
      )}

      <section className="bg-card border border-border rounded-xl p-7" style={{ marginBottom: 24 }}>
        <h3 className="text-foreground" style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>创建新环境</h3>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <select
            value={newBackend}
            onChange={(e) => setNewBackend(e.target.value)}
            className="bg-muted border border-border text-foreground"
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
            className="bg-muted border border-border text-foreground"
            style={fieldStyle}
          />
          <input
            placeholder="Python 版本"
            value={newPython}
            onChange={(e) => setNewPython(e.target.value)}
            className="bg-muted border border-border text-foreground"
            style={fieldStyle}
          />
          <button
            onClick={createEnv}
            disabled={creating || !newName.trim()}
            className="bg-primary text-primary-foreground hover:opacity-90"
            style={primaryBtnStyle}
          >
            {creating ? '创建中...' : '创建'}
          </button>
        </div>
      </section>

      {installTarget && (
        <section className="bg-card border border-border rounded-xl p-5" style={{ marginBottom: 24 }}>
          <h3 className="text-foreground" style={{ fontSize: 16, marginBottom: 12 }}>
            安装依赖到 {installTarget.name}
          </h3>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              placeholder="requirements.txt 路径（留空使用项目默认）"
              value={requirementsPath}
              onChange={(e) => setRequirementsPath(e.target.value)}
              className="bg-muted border border-border text-foreground"
              style={{ ...fieldStyle, minWidth: 320 }}
            />
            <button
              onClick={installReqs}
              disabled={installing}
              className="bg-primary text-primary-foreground hover:opacity-90"
              style={primaryBtnStyle}
            >
              {installing ? '安装中...' : '安装'}
            </button>
            <button
              onClick={() => setInstallTarget(null)}
              className="bg-muted border border-border text-muted-foreground"
              style={secondaryBtnStyle}
            >
              取消
            </button>
          </div>
        </section>
      )}

      <section>
        <h3 className="text-foreground" style={{ fontSize: 16, marginBottom: 12 }}>环境列表</h3>
        {loading ? (
          <p className="text-muted-foreground" style={{ fontSize: 13 }}>加载中...</p>
        ) : envs.length === 0 ? (
          <p className="text-muted-foreground" style={{ fontSize: 13 }}>暂无环境</p>
        ) : (
          <table className="text-foreground" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr className="bg-muted">
                <th className="border-b border-border bg-muted text-muted-foreground" style={thStyle}>名称</th>
                <th className="border-b border-border bg-muted text-muted-foreground" style={thStyle}>后端</th>
                <th className="border-b border-border bg-muted text-muted-foreground" style={thStyle}>Python</th>
                <th className="border-b border-border bg-muted text-muted-foreground" style={thStyle}>路径</th>
                <th className="border-b border-border bg-muted text-muted-foreground" style={thStyle}>状态</th>
                <th className="border-b border-border bg-muted text-muted-foreground" style={{ ...thStyle, minWidth: 220 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {envs.map((env) => (
                <tr key={`${env.backend}-${env.name}`} className="border-b border-border">
                  <td className="border-b border-border text-foreground" style={tdStyle}>{env.name}</td>
                  <td className="border-b border-border text-foreground" style={tdStyle}>{env.backend}</td>
                  <td className="border-b border-border text-foreground" style={tdStyle}>{env.python_version}</td>
                  <td
                    className="border-b border-border text-muted-foreground"
                    style={{
                      ...tdStyle,
                      maxWidth: 300,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
                      fontSize: 12,
                    }}
                  >
                    {env.path}
                  </td>
                  <td className="border-b border-border text-foreground" style={tdStyle}>
                    {env.is_active ? (
                      <span className="text-success" style={{ fontWeight: 700, fontSize: 13 }}>
                        ● 激活
                      </span>
                    ) : (
                      <span className="text-muted-foreground" style={{ fontSize: 13 }}>未激活</span>
                    )}
                  </td>
                  <td className="border-b border-border text-foreground" style={{ ...tdStyle, minWidth: 220 }}>
                    <button
                      onClick={() => activateEnv(env.backend, env.name)}
                      disabled={env.is_active}
                      className={
                        env.is_active
                          ? 'bg-muted border border-border text-muted-foreground'
                          : 'bg-primary text-primary-foreground hover:opacity-90'
                      }
                      style={env.is_active ? disabledBtnStyle : primaryBtnSmStyle}
                    >
                      激活
                    </button>{' '}
                    <button
                      onClick={() => setInstallTarget({ backend: env.backend, name: env.name })}
                      className="bg-muted border border-border text-muted-foreground"
                      style={secondaryBtnSmStyle}
                    >
                      安装依赖
                    </button>{' '}
                    <button
                      onClick={() => deleteEnv(env.backend, env.name)}
                      className="border border-error/20 bg-error/10 text-error"
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
