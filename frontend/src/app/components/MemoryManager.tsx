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
    <div className="p-4 text-[#e0e0e0]">
      <div className="flex justify-between items-center mb-[1.5rem]">
        <span className="text-[1.3rem] font-bold text-[#f39c12]">🧠 记忆管理</span>
      </div>

      {stats && (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-4 mb-[1.5rem]">
          <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4 text-center">
            <div className="text-[1.6rem] font-bold text-[#2ecc71]">{stats.total_lessons}</div>
            <div className="text-[0.9375rem] text-[#94A3B8] mt-[0.3rem]">经验总数</div>
          </div>
          <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4 text-center">
            <div className="text-[1.6rem] font-bold text-[#2ecc71]">{stats.active_task_memories}</div>
            <div className="text-[0.9375rem] text-[#94A3B8] mt-[0.3rem]">活跃任务记忆</div>
          </div>
          <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4 text-center">
            <div className="text-[1.6rem] font-bold text-[#2ecc71]">{Object.keys(stats.by_category || {}).length}</div>
            <div className="text-[0.9375rem] text-[#94A3B8] mt-[0.3rem]">经验类别</div>
          </div>
        </div>
      )}

      <div className="flex gap-2 mb-4 border-b border-[#334155] pb-2">
        <button className={cn('py-2 px-4 bg-transparent border border-[#334155] rounded-[6px] text-[#94A3B8] cursor-pointer text-[0.9375rem]', tab === 'lessons' && 'bg-[rgba(243,156,18,0.15)] border-[rgba(243,156,18,0.4)] text-[#f39c12]')} onClick={() => setTab('lessons')}>
          📚 经验教训
        </button>
        <button className={cn('py-2 px-4 bg-transparent border border-[#334155] rounded-[6px] text-[#94A3B8] cursor-pointer text-[0.9375rem]', tab === 'task' && 'bg-[rgba(243,156,18,0.15)] border-[rgba(243,156,18,0.4)] text-[#f39c12]')} onClick={() => setTab('task')}>
          📋 任务记忆
        </button>
        <button className={cn('py-2 px-4 bg-transparent border border-[#334155] rounded-[6px] text-[#94A3B8] cursor-pointer text-[0.9375rem]', tab === 'stats' && 'bg-[rgba(243,156,18,0.15)] border-[rgba(243,156,18,0.4)] text-[#f39c12]')} onClick={() => setTab('stats')}>
          📊 统计
        </button>
      </div>

      {tab === 'lessons' && (
        <>
          <div className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4 mb-[1.5rem]">
            <div className="text-[1rem] font-semibold text-[#CBD5E1] mb-[0.8rem]">➕ 添加经验</div>
            <div className="flex gap-2 mb-[0.8rem] flex-wrap">
              <select
                className="py-2 px-[0.6rem] bg-[rgba(0,0,0,0.3)] border border-[#475569] rounded-[6px] text-[#e0e0e0] text-[0.9375rem]"
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
                className="py-2 px-[0.6rem] bg-[rgba(0,0,0,0.3)] border border-[#475569] rounded-[6px] text-[#e0e0e0] text-[0.9375rem]"
                placeholder="问题类型"
                value={newLesson.problem_type}
                onChange={(e) => setNewLesson({ ...newLesson, problem_type: e.target.value })}
              />
              <input
                className="py-2 px-[0.6rem] bg-[rgba(0,0,0,0.3)] border border-[#475569] rounded-[6px] text-[#e0e0e0] text-[0.9375rem]"
                placeholder="方法/模型"
                value={newLesson.method}
                onChange={(e) => setNewLesson({ ...newLesson, method: e.target.value })}
              />
              <select
                className="py-2 px-[0.6rem] bg-[rgba(0,0,0,0.3)] border border-[#475569] rounded-[6px] text-[#e0e0e0] text-[0.9375rem]"
                value={newLesson.success ? 'true' : 'false'}
                onChange={(e) => setNewLesson({ ...newLesson, success: e.target.value === 'true' })}
              >
                <option value="true">有效经验</option>
                <option value="false">失败教训</option>
              </select>
            </div>
            <textarea
              className="w-full min-h-[80px] py-2 px-[0.6rem] bg-[rgba(0,0,0,0.3)] border border-[#475569] rounded-[6px] text-[#e0e0e0] text-[0.9375rem] font-[inherit] resize-y"
              placeholder="经验内容..."
              value={newLesson.content}
              onChange={(e) => setNewLesson({ ...newLesson, content: e.target.value })}
            />
            <div className="flex gap-2 mt-[0.8rem]">
              <button className="py-2 px-4 bg-[#4ADE80] border-none rounded-[6px] text-[#F8FAFC] cursor-pointer text-[0.9375rem] font-semibold" onClick={addLesson}>添加经验</button>
              <button className="py-[0.4rem] px-[0.8rem] bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.15)] rounded-[6px] text-[#e74c3c] cursor-pointer text-[0.875rem]" onClick={clearLessons}>清空全部</button>
            </div>
          </div>

          <div className="flex gap-2 mb-4 flex-wrap">
            <input
              className="py-2 px-[0.6rem] bg-[rgba(0,0,0,0.3)] border border-[#475569] rounded-[6px] text-[#e0e0e0] text-[0.9375rem]"
              placeholder="按类别筛选"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
            />
            <input
              className="py-2 px-[0.6rem] bg-[rgba(0,0,0,0.3)] border border-[#475569] rounded-[6px] text-[#e0e0e0] text-[0.9375rem]"
              placeholder="按问题类型筛选"
              value={problemTypeFilter}
              onChange={(e) => setProblemTypeFilter(e.target.value)}
            />
            <button className="py-2 px-4 bg-[rgba(45,212,191,0.15)] border border-[rgba(45,212,191,0.15)] rounded-[6px] text-[#3498db] cursor-pointer text-[0.9375rem]" onClick={loadLessons}>刷新</button>
          </div>

          {loading && lessons.length === 0 ? (
            <div className="text-[#94A3B8] text-center p-[2rem]">加载中...</div>
          ) : lessons.length === 0 ? (
            <div className="text-[#94A3B8] text-center p-[2rem]">暂无经验教训</div>
          ) : (
            <div className="flex flex-col gap-[0.8rem]">
              {lessons.map((lesson) => (
                <div key={lesson.id} className="bg-[#1E293B] border border-[#334155] rounded-[10px] p-4">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex gap-2 flex-wrap">
                      <span className="px-[0.5rem] py-[0.2rem] bg-[rgba(45,212,191,0.15)] rounded-[4px] text-[0.875rem] text-[#3498db]">{lesson.category}</span>
                      <span className={cn('px-[0.5rem] py-[0.2rem] rounded-[4px] text-[0.875rem]', lesson.success ? 'bg-[rgba(45,212,191,0.15)] text-[#3498db]' : 'bg-[rgba(243,156,18,0.15)] text-[#f39c12]')}>
                        {lesson.success ? '有效' : '教训'}
                      </span>
                      {lesson.problem_type && <span className="px-[0.5rem] py-[0.2rem] bg-[rgba(45,212,191,0.15)] rounded-[4px] text-[0.875rem] text-[#3498db]">{lesson.problem_type}</span>}
                      {lesson.method && <span className="px-[0.5rem] py-[0.2rem] bg-[rgba(45,212,191,0.15)] rounded-[4px] text-[0.875rem] text-[#3498db]">{lesson.method}</span>}
                    </div>
                    <button className="py-[0.4rem] px-[0.8rem] bg-[rgba(248,113,113,0.15)] border border-[rgba(248,113,113,0.15)] rounded-[6px] text-[#e74c3c] cursor-pointer text-[0.875rem]" onClick={() => deleteLesson(lesson.id)}>删除</button>
                  </div>
                  <div className="text-[0.9375rem] leading-[1.6] text-[#CBD5E1]">{lesson.content}</div>
                  <div className="flex gap-2 flex-wrap mt-[0.5rem] text-[0.75rem] text-[#888]">
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
              className="py-2 px-[0.6rem] bg-[rgba(0,0,0,0.3)] border border-[#475569] rounded-[6px] text-[#e0e0e0] text-[0.9375rem] flex-1"
              placeholder="输入任务ID"
              value={taskId}
              onChange={(e) => setTaskId(e.target.value)}
            />
            <button className="py-2 px-4 bg-[rgba(45,212,191,0.15)] border border-[rgba(45,212,191,0.15)] rounded-[6px] text-[#3498db] cursor-pointer text-[0.9375rem]" onClick={() => loadTaskMemory(taskId)}>加载</button>
          </div>
          {loading && !taskMemory ? (
            <div className="text-[#94A3B8] text-center p-[2rem]">加载中...</div>
          ) : taskMemory ? (
            <pre className="bg-[rgba(0,0,0,0.3)] border border-[#334155] rounded-[6px] p-4 font-['Fira_Code','Consolas',monospace] text-[0.875rem] text-[#CBD5E1] overflow-x-auto whitespace-pre-wrap break-word max-h-[500px] overflow-y-auto">{JSON.stringify(taskMemory, null, 2)}</pre>
          ) : (
            <div className="text-[#94A3B8] text-center p-[2rem]">输入任务ID后加载工作记忆与情景记忆</div>
          )}
        </>
      )}

      {tab === 'stats' && stats && (
        <>
          <div className="text-[1rem] font-semibold text-[#CBD5E1] mb-[0.8rem]">按类别分布</div>
          <pre className="bg-[rgba(0,0,0,0.3)] border border-[#334155] rounded-[6px] p-4 font-['Fira_Code','Consolas',monospace] text-[0.875rem] text-[#CBD5E1] overflow-x-auto whitespace-pre-wrap break-word max-h-[500px] overflow-y-auto">{JSON.stringify(stats.by_category, null, 2)}</pre>
          <div className="text-[1rem] font-semibold text-[#CBD5E1] mt-4 mb-[0.8rem]">按问题类型分布</div>
          <pre className="bg-[rgba(0,0,0,0.3)] border border-[#334155] rounded-[6px] p-4 font-['Fira_Code','Consolas',monospace] text-[0.875rem] text-[#CBD5E1] overflow-x-auto whitespace-pre-wrap break-word max-h-[500px] overflow-y-auto">{JSON.stringify(stats.by_problem_type, null, 2)}</pre>
        </>
      )}
    </div>
  );
}
