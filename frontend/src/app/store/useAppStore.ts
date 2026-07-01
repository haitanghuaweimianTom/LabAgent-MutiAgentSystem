import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Project {
  id: string;
  name: string;
  createdAt: number;
  taskIds: string[];
  description?: string;
  path?: string;
  updatedAt?: number;
}

export interface TaskFile {
  name: string;
  size: number;
  type: string;
  selected?: boolean;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description?: string;
  item_count?: number;
  created_at?: number;
  updated_at?: number;
}

export interface Paper {
  arxiv_id: string;
  title: string;
  authors: string[];
  year: number;
  abstract: string;
  url: string;
  pdf_url?: string;
  categories?: string[];
  published?: string;
  source: string;
  search_query?: string;

  // Semantic Scholar 等外部源补充的元数据
  doi?: string;
  citation_count?: number;
  reference_count?: number;
  influential_citation_count?: number;
  venue?: string;
  fields_of_study?: string[];
  publication_date?: string;
  s2_paper_id?: string;
  s2_url?: string;
  tldr?: string;
  open_access_pdf?: string;
  metadata_sources?: string[];

  // 深度调研相关
  relevance_score?: number;
  extraction?: {
    methods?: string;
    conclusion?: string;
    datasets?: string[];
    limitations?: string;
    key_findings?: string[];
  };
}

const apiBase = () => window.__API_BASE__ || 'http://localhost:8000/api/v1';

interface AppState {
  projects: Project[];
  activeProjectId: string | null;
  selectedFiles: Set<string>;
  setActiveProject: (id: string | null) => void;
  createProject: (name: string) => Promise<string>;
  deleteProject: (id: string) => Promise<void>;
  renameProject: (id: string, name: string) => Promise<void>;
  addTaskToProject: (projectId: string, taskId: string) => Promise<void>;
  loadProjects: () => Promise<void>;
  toggleFileSelection: (name: string) => void;
  selectAllFiles: (names: string[]) => void;
  clearFileSelection: () => void;
  // Knowledge bases
  knowledgeBases: KnowledgeBase[];
  activeKnowledgeBaseId: string | null;
  setKnowledgeBases: (bases: KnowledgeBase[]) => void;
  setActiveKnowledgeBase: (id: string | null) => void;
  addKnowledgeBase: (base: KnowledgeBase) => void;
  removeKnowledgeBase: (id: string) => void;
  renameKnowledgeBase: (id: string, name: string) => void;
  // v5.4.0: 多 KB 选择（任务提交用）
  selectedKBIds: Set<string>;
  toggleKBSelection: (id: string) => void;
  clearKBSelection: () => void;
  setKBSelection: (ids: string[]) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      projects: [],
      activeProjectId: null,
      selectedFiles: new Set(),

      setActiveProject: (id) => set({ activeProjectId: id }),

      loadProjects: async () => {
        try {
          const res = await fetch(apiBase() + '/projects');
          if (res.ok) {
            const data = await res.json();
            const projects: Project[] = data.map((p: any) => ({
              id: p.id,
              name: p.name,
              createdAt: p.created_at ? p.created_at * 1000 : Date.now(),
              updatedAt: p.updated_at ? p.updated_at * 1000 : Date.now(),
              taskIds: p.task_ids || [],
              description: p.description,
              path: p.path,
            }));
            set({ projects });
          }
        } catch (e) {
          console.error('Failed to load projects:', e);
        }
      },

      createProject: async (name) => {
        try {
          const res = await fetch(apiBase() + '/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description: '' }),
          });
          if (res.ok) {
            const data = await res.json();
            const p = data.project;
            const project: Project = {
              id: p.id,
              name: p.name,
              createdAt: p.created_at ? p.created_at * 1000 : Date.now(),
              updatedAt: p.updated_at ? p.updated_at * 1000 : Date.now(),
              taskIds: p.task_ids || [],
              description: p.description,
              path: p.path,
            };
            set((s) => ({ projects: [project, ...s.projects] }));
            return project.id;
          }
        } catch (e) {
          console.error('Failed to create project:', e);
        }
        // Fallback to local-only
        const id = 'proj_' + Date.now();
        set((s) => ({ projects: [...s.projects, { id, name, createdAt: Date.now(), taskIds: [] }] }));
        return id;
      },

      deleteProject: async (id) => {
        try {
          const res = await fetch(apiBase() + '/projects/' + id, { method: 'DELETE' });
          if (!res.ok && res.status !== 404) {
            console.error('Failed to delete project on server');
          }
        } catch (e) {
          console.error('Failed to delete project:', e);
        }
        set((s) => ({
          projects: s.projects.filter((p) => p.id !== id),
          activeProjectId: s.activeProjectId === id ? null : s.activeProjectId,
        }));
      },

      renameProject: async (id, name) => {
        try {
          const res = await fetch(apiBase() + '/projects/' + id + '/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
          });
          if (!res.ok) {
            console.error('Failed to rename project on server');
          }
        } catch (e) {
          console.error('Failed to rename project:', e);
        }
        set((s) => ({
          projects: s.projects.map((p) => (p.id === id ? { ...p, name } : p)),
        }));
      },

      addTaskToProject: async (projectId, taskId) => {
        try {
          const res = await fetch(apiBase() + '/projects/' + projectId + '/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_id: taskId }),
          });
          if (!res.ok) {
            console.error('Failed to add task to project on server');
          }
        } catch (e) {
          console.error('Failed to add task to project:', e);
        }
        set((s) => ({
          projects: s.projects.map((p) =>
            p.id === projectId ? { ...p, taskIds: [...p.taskIds, taskId] } : p
          ),
        }));
      },

      toggleFileSelection: (name) =>
        set((s) => {
          const next = new Set(s.selectedFiles);
          if (next.has(name)) next.delete(name);
          else next.add(name);
          return { selectedFiles: next };
        }),

      selectAllFiles: (names) => set({ selectedFiles: new Set(names) }),
      clearFileSelection: () => set({ selectedFiles: new Set() }),

      // Knowledge bases (从后端加载，不持久化到本地)
      knowledgeBases: [],
      activeKnowledgeBaseId: null,
      setKnowledgeBases: (bases) => set({ knowledgeBases: bases }),
      setActiveKnowledgeBase: (id) => set({ activeKnowledgeBaseId: id }),
      addKnowledgeBase: (base) =>
        set((s) => ({ knowledgeBases: [...s.knowledgeBases, base] })),
      removeKnowledgeBase: (id) =>
        set((s) => ({
          knowledgeBases: s.knowledgeBases.filter((b) => b.id !== id),
          activeKnowledgeBaseId: s.activeKnowledgeBaseId === id ? null : s.activeKnowledgeBaseId,
        })),
      renameKnowledgeBase: (id, name) =>
        set((s) => ({
          knowledgeBases: s.knowledgeBases.map((b) =>
            b.id === id ? { ...b, name } : b
          ),
        })),

      // v5.4.0: 多 KB 选择（任务提交时勾选）
      selectedKBIds: new Set(),
      toggleKBSelection: (id) =>
        set((s) => {
          const next = new Set(s.selectedKBIds);
          if (next.has(id)) next.delete(id);
          else next.add(id);
          return { selectedKBIds: next };
        }),
      clearKBSelection: () => set({ selectedKBIds: new Set() }),
      setKBSelection: (ids) => set({ selectedKBIds: new Set(ids) }),
    }),
    {
      name: 'app-store',
      partialize: (state) => ({
        activeProjectId: state.activeProjectId,
        // Set 不能 JSON 序列化，必须转 Array；rehydrate 时 onRehydrateStorage 转回 Set
        selectedFiles: Array.from(state.selectedFiles),
        selectedKBIds: Array.from(state.selectedKBIds),
      }),
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        // 把 Array 转回 Set（持久化时 Array.from，反序列化必须 new Set）
        if (Array.isArray((state as any).selectedFiles)) {
          (state as any).selectedFiles = new Set((state as any).selectedFiles);
        }
        if (Array.isArray((state as any).selectedKBIds)) {
          (state as any).selectedKBIds = new Set((state as any).selectedKBIds);
        } else if (!(state as any).selectedKBIds) {
          (state as any).selectedKBIds = new Set();
        }
      },
    }
  )
);
