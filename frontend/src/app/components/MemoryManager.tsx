'use client';

import { useEffect, useState } from 'react';
import { apiBase } from '@/lib/api';
import { cn } from '@/lib/utils';

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
    <div className="p-4 text-foreground">
      <div className="flex justify-between items-center mb-6">
        <span className="text-xl font-bold text-warning">🧠 记忆管理</span>
      </div>

      {stats && (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-4 mb-6">
          <div className="bg-card border border-border rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-success">{stats.total_lessons}</div>
            <div className="text-sm text-muted-foreground mt-1.5">经验总数</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-success">{stats.active_task_memories}</div>
            <div className="text-sm text-muted-foreground mt-1.5">活跃任务记忆</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-success">{Object.keys(stats.by_category || {}).length}</div>
            <div className="text-sm text-muted-foreground mt-1.5">经验类别</div>
          </div>
        </div>
      )}

      <div className="flex gap-2 mb-4 border-b border-border pb-2">
        <button className={cn('py-2 px-4 bg-transparent border border-border rounded-md text-muted-foreground cursor-pointer text-sm transition-colors', tab === 'lessons' && 'bg-warning/10 border-warning/40 text-warning')} onClick={() => setTab('lessons')}>
          📚 经验教训
        </button>
        <button className={cn('py-2 px-4 bg-transparent border border-border rounded-md text-muted-foreground cursor-pointer text-sm transition-colors', tab === 'task' && 'bg-warning/10 border-warning/40 text-warning')} onClick={() => setTab('task')}>
          📋 任务记忆
        </button>
        <button className={cn('py-2 px-4 bg-transparent border border-border rounded-md text-muted-foreground cursor-pointer text-sm transition-colors', tab === 'stats' && 'bg-warning/10 border-warning/40 text-warning')} onClick={() => setTab('stats')}>
          📊 统计
        </button>
      </div>

      {tab === 'lessons' && (
        <>
          <div className="bg-card border border-border rounded-lg p-4 mb-6">
            <div className="text-base font-semibold text-foreground mb-4">➕ 添加经验</div>
            <div className="flex gap-2 mb-4 flex-wrap">
              <select
                className="py-2 px-2.5 bg-muted border border-border rounded-md text-foreground text-sm"
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
                className="py-2 px-2.5 bg-muted border border-border rounded-md text-foreground text-sm"
                placeholder="问题类型"
                value={newLesson.problem_type}
                onChange={(e) => setNewLesson({ ...newLesson, problem_type: e.target.value })}
              />
              <input
                className="py-2 px-2.5 bg-muted border border-border rounded-md text-foreground text-sm"
                placeholder="方法/模型"
                value={newLesson.method}
                onChange={(e) => setNewLesson({ ...newLesson, method: e.target.value })}
              />
              <select
                className="py-2 px-2.5 bg-muted border border-border rounded-md text-foreground text-sm"
                value={newLesson.success ? 'true' : 'false'}
                onChange={(e) => setNewLesson({ ...newLesson, success: e.target.value === 'true' })}
              >
                <option value="true">有效经验</option>
                <option value="false">失败教训</option>
              </select>
            </div>
            <textarea
              className="w-full min-h-[80px] py-2 px-2.5 bg-muted border border-border rounded-md text-foreground text-sm font-[inherit] resize-y"
              placeholder="经验内容..."
              value={newLesson.content}
              onChange={(e) => setNewLesson({ ...newLesson, content: e.target.value })}
            />
            <div className="flex gap-2 mt-4">
              <button className="py-2 px-4 bg-primary text-primary-foreground border-none rounded-md cursor-pointer text-sm font-semibold transition-opacity hover:opacity-90" onClick={addLesson}>添加经验</button>
              <button className="py-1.5 px-4 bg-error/10 text-error border border-error/20 rounded-md cursor-pointer text-sm transition-colors hover:bg-error/15" onClick={clearLessons}>清空全部</button>
            </div>
          </div>

          <div className="flex gap-2 mb-4 flex-wrap">
            <input
              className="py-2 px-2.5 bg-muted border border-border rounded-md text-foreground text-sm"
              placeholder="按类别筛选"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
            />
            <input
              className="py-2 px-2.5 bg-muted border border-border rounded-md text-foreground text-sm"
              placeholder="按问题类型筛选"
              value={problemTypeFilter}
              onChange={(e) => setProblemTypeFilter(e.target.value)}
            />
            <button className="py-2 px-4 bg-primary/10 text-primary border border-primary/20 rounded-md cursor-pointer text-sm transition-colors hover:bg-primary/15" onClick={loadLessons}>刷新</button>
          </div>

          {loading && lessons.length === 0 ? (
            <div className="text-muted-foreground text-center p-8">加载中...</div>
          ) : lessons.length === 0 ? (
            <div className="text-muted-foreground text-center p-8">暂无经验教训</div>
          ) : (
            <div className="flex flex-col gap-4">
              {lessons.map((lesson) => (
                <div key={lesson.id} className="bg-card border border-border rounded-lg p-4">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex gap-2 flex-wrap">
                      <span className="px-2 py-1 bg-primary/10 rounded text-sm text-primary">{lesson.category}</span>
                      <span className={cn('px-2 py-1 rounded text-sm', lesson.success ? 'bg-primary/10 text-primary' : 'bg-warning/10 text-warning')}>
                        {lesson.success ? '有效' : '教训'}
                      </span>
                      {lesson.problem_type && <span className="px-2 py-1 bg-primary/10 rounded text-sm text-primary">{lesson.problem_type}</span>}
                      {lesson.method && <span className="px-2 py-1 bg-primary/10 rounded text-sm text-primary">{lesson.method}</span>}
                    </div>
                    <button className="py-1.5 px-4 bg-error/10 text-error border border-error/20 rounded-md cursor-pointer text-sm transition-colors hover:bg-error/15" onClick={() => deleteLesson(lesson.id)}>删除</button>
                  </div>
                  <div className="text-sm leading-relaxed text-foreground">{lesson.content}</div>
                  <div className="flex gap-2 flex-wrap mt-2 text-xs text-muted-foreground">
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
          <div className="flex gap-2 mb-4">
            <input
              className="py-2 px-2.5 bg-muted border border-border rounded-md text-foreground text-sm flex-1"
              placeholder="输入任务ID"
              value={taskId}
              onChange={(e) => setTaskId(e.target.value)}
            />
            <button className="py-2 px-4 bg-primary/10 text-primary border border-primary/20 rounded-md cursor-pointer text-sm transition-colors hover:bg-primary/15" onClick={() => loadTaskMemory(taskId)}>加载</button>
          </div>
          {loading && !taskMemory ? (
            <div className="text-muted-foreground text-center p-8">加载中...</div>
          ) : taskMemory ? (
            <pre className="bg-muted border border-border rounded-md p-4 font-mono text-sm text-foreground overflow-x-auto whitespace-pre-wrap break-word max-h-[500px] overflow-y-auto">{JSON.stringify(taskMemory, null, 2)}</pre>
          ) : (
            <div className="text-muted-foreground text-center p-8">输入任务ID后加载工作记忆与情景记忆</div>
          )}
        </>
      )}

      {tab === 'stats' && stats && (
        <>
          <div className="text-base font-semibold text-foreground mb-4">按类别分布</div>
          <pre className="bg-muted border border-border rounded-md p-4 font-mono text-sm text-foreground overflow-x-auto whitespace-pre-wrap break-word max-h-[500px] overflow-y-auto">{JSON.stringify(stats.by_category, null, 2)}</pre>
          <div className="text-base font-semibold text-foreground mt-4 mb-4">按问题类型分布</div>
          <pre className="bg-muted border border-border rounded-md p-4 font-mono text-sm text-foreground overflow-x-auto whitespace-pre-wrap break-word max-h-[500px] overflow-y-auto">{JSON.stringify(stats.by_problem_type, null, 2)}</pre>
        </>
      )}
    </div>
  );
}
