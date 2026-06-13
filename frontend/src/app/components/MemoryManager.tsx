'use client';

import { useEffect, useState } from 'react';
import styles from './MemoryManager.module.css';

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

type Tab = 'lessons' | 'task' | 'stats';

interface Lesson {
  id: string;
  category: string;
  content: string;
  problem_type: string;
  method: string;
  success: boolean;
  source_task: string;
  created_at: string;
  use_count: number;
}

export default function MemoryManager() {
  const [tab, setTab] = useState<Tab>('lessons');
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [taskMemory, setTaskMemory] = useState<any>(null);
  const [taskId, setTaskId] = useState('');
  const [loading, setLoading] = useState(false);

  const [categoryFilter, setCategoryFilter] = useState('');
  const [problemTypeFilter, setProblemTypeFilter] = useState('');

  const [newLesson, setNewLesson] = useState({
    category: 'method_selection',
    content: '',
    problem_type: '',
    method: '',
    success: true,
  });

  const loadLessons = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (categoryFilter) params.set('category', categoryFilter);
      if (problemTypeFilter) params.set('problem_type', problemTypeFilter);
      params.set('top_k', '50');
      const res = await fetch(apiBase() + '/memory/lessons?' + params.toString());
      if (res.ok) {
        const data = await res.json();
        setLessons(data.lessons || []);
      }
    } catch (e) {
      console.error('加载经验教训失败:', e);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const res = await fetch(apiBase() + '/memory/stats');
      if (res.ok) setStats(await res.json());
    } catch (e) {
      console.error('加载记忆统计失败:', e);
    }
  };

  const addLesson = async () => {
    if (!newLesson.content.trim()) return;
    try {
      const res = await fetch(apiBase() + '/memory/lessons', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newLesson),
      });
      if (res.ok) {
        setNewLesson({ category: 'method_selection', content: '', problem_type: '', method: '', success: true });
        loadLessons();
        loadStats();
      }
    } catch (e) {
      console.error('添加经验失败:', e);
    }
  };

  const deleteLesson = async (id: string) => {
    if (!confirm('确定删除这条经验？')) return;
    try {
      const res = await fetch(apiBase() + '/memory/lessons', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lesson_id: id }),
      });
      if (res.ok) {
        loadLessons();
        loadStats();
      }
    } catch (e) {
      console.error('删除经验失败:', e);
    }
  };

  const clearLessons = async () => {
    if (!confirm('确定清空所有经验教训？此操作不可恢复。')) return;
    try {
      const res = await fetch(apiBase() + '/memory/lessons/clear', { method: 'POST' });
      if (res.ok) {
        loadLessons();
        loadStats();
      }
    } catch (e) {
      console.error('清空经验失败:', e);
    }
  };

  const loadTaskMemory = async (id: string) => {
    if (!id.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(apiBase() + '/memory/task/' + id);
      if (res.ok) {
        setTaskMemory(await res.json());
      } else {
        setTaskMemory({ error: '任务记忆不存在或加载失败' });
      }
    } catch (e) {
      setTaskMemory({ error: '网络错误' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLessons();
    loadStats();
  }, []);

  useEffect(() => {
    if (tab === 'lessons') loadLessons();
    if (tab === 'stats') loadStats();
  }, [tab, categoryFilter, problemTypeFilter]);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.title}>🧠 记忆管理</span>
      </div>

      {stats && (
        <div className={styles.stats}>
          <div className={styles.statCard}>
            <div className={styles.statValue}>{stats.total_lessons}</div>
            <div className={styles.statLabel}>经验总数</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statValue}>{stats.active_task_memories}</div>
            <div className={styles.statLabel}>活跃任务记忆</div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statValue}>{Object.keys(stats.by_category || {}).length}</div>
            <div className={styles.statLabel}>经验类别</div>
          </div>
        </div>
      )}

      <div className={styles.tabs}>
        <button className={`${styles.tab} ${tab === 'lessons' ? styles.tabActive : ''}`} onClick={() => setTab('lessons')}>
          📚 经验教训
        </button>
        <button className={`${styles.tab} ${tab === 'task' ? styles.tabActive : ''}`} onClick={() => setTab('task')}>
          📋 任务记忆
        </button>
        <button className={`${styles.tab} ${tab === 'stats' ? styles.tabActive : ''}`} onClick={() => setTab('stats')}>
          📊 统计
        </button>
      </div>

      {tab === 'lessons' && (
        <>
          <div className={styles.form}>
            <div className={styles.sectionTitle}>➕ 添加经验</div>
            <div className={styles.formRow}>
              <select
                className={styles.select}
                value={newLesson.category}
                onChange={(e) => setNewLesson({ ...newLesson, category: e.target.value })}
              >
                <option value="method_selection">方法选择</option>
                <option value="data_processing">数据处理</option>
                <option value="modeling">建模</option>
                <option value="solving">求解</option>
                <option value="writing">写作</option>
              </select>
              <input
                className={styles.input}
                placeholder="问题类型"
                value={newLesson.problem_type}
                onChange={(e) => setNewLesson({ ...newLesson, problem_type: e.target.value })}
              />
              <input
                className={styles.input}
                placeholder="方法/模型"
                value={newLesson.method}
                onChange={(e) => setNewLesson({ ...newLesson, method: e.target.value })}
              />
              <select
                className={styles.select}
                value={newLesson.success ? 'true' : 'false'}
                onChange={(e) => setNewLesson({ ...newLesson, success: e.target.value === 'true' })}
              >
                <option value="true">有效经验</option>
                <option value="false">失败教训</option>
              </select>
            </div>
            <textarea
              className={styles.textarea}
              placeholder="经验内容..."
              value={newLesson.content}
              onChange={(e) => setNewLesson({ ...newLesson, content: e.target.value })}
            />
            <div className={styles.formRow} style={{ marginTop: '0.8rem' }}>
              <button className={styles.btnSuccess} onClick={addLesson}>添加经验</button>
              <button className={styles.btnDanger} onClick={clearLessons}>清空全部</button>
            </div>
          </div>

          <div className={styles.filters}>
            <input
              className={styles.input}
              placeholder="按类别筛选"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
            />
            <input
              className={styles.input}
              placeholder="按问题类型筛选"
              value={problemTypeFilter}
              onChange={(e) => setProblemTypeFilter(e.target.value)}
            />
            <button className={styles.btn} onClick={loadLessons}>刷新</button>
          </div>

          {loading && lessons.length === 0 ? (
            <div className={styles.empty}>加载中...</div>
          ) : lessons.length === 0 ? (
            <div className={styles.empty}>暂无经验教训</div>
          ) : (
            <div className={styles.list}>
              {lessons.map((lesson) => (
                <div key={lesson.id} className={styles.card}>
                  <div className={styles.cardHeader}>
                    <div className={styles.cardMeta}>
                      <span className={styles.tag}>{lesson.category}</span>
                      <span className={lesson.success ? `${styles.tag} ${styles.tagSuccess}` : `${styles.tag} ${styles.tagWarning}`}>
                        {lesson.success ? '有效' : '教训'}
                      </span>
                      {lesson.problem_type && <span className={styles.tag}>{lesson.problem_type}</span>}
                      {lesson.method && <span className={styles.tag}>{lesson.method}</span>}
                    </div>
                    <button className={styles.btnDanger} onClick={() => deleteLesson(lesson.id)}>删除</button>
                  </div>
                  <div className={styles.content}>{lesson.content}</div>
                  <div className={styles.cardMeta} style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#888' }}>
                    <span>引用 {lesson.use_count || 0} 次</span>
                    <span>来源: {lesson.source_task}</span>
                    <span>{new Date(lesson.created_at).toLocaleString('zh-CN')}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {tab === 'task' && (
        <>
          <div className={styles.taskInput}>
            <input
              className={styles.input}
              style={{ flex: 1 }}
              placeholder="输入任务ID"
              value={taskId}
              onChange={(e) => setTaskId(e.target.value)}
            />
            <button className={styles.btn} onClick={() => loadTaskMemory(taskId)}>加载</button>
          </div>
          {loading && !taskMemory ? (
            <div className={styles.empty}>加载中...</div>
          ) : taskMemory ? (
            <pre className={styles.jsonView}>{JSON.stringify(taskMemory, null, 2)}</pre>
          ) : (
            <div className={styles.empty}>输入任务ID后加载工作记忆与情景记忆</div>
          )}
        </>
      )}

      {tab === 'stats' && stats && (
        <>
          <div className={styles.sectionTitle}>按类别分布</div>
          <pre className={styles.jsonView}>{JSON.stringify(stats.by_category, null, 2)}</pre>
          <div className={styles.sectionTitle} style={{ marginTop: '1rem' }}>按问题类型分布</div>
          <pre className={styles.jsonView}>{JSON.stringify(stats.by_problem_type, null, 2)}</pre>
        </>
      )}
    </div>
  );
}
