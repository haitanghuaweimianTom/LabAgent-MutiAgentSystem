import { create } from 'zustand';

export interface Project {
  id: string;
  name: string;
  createdAt: number;
  taskIds: string[];
}

export interface TaskFile {
  name: string;
  size: number;
  type: string;
  selected?: boolean;
}

interface AppState {
  projects: Project[];
  activeProjectId: string | null;
  selectedFiles: Set<string>;
  setActiveProject: (id: string | null) => void;
  createProject: (name: string) => string;
  deleteProject: (id: string) => void;
  addTaskToProject: (projectId: string, taskId: string) => void;
  toggleFileSelection: (name: string) => void;
  selectAllFiles: (names: string[]) => void;
  clearFileSelection: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  projects: [],
  activeProjectId: null,
  selectedFiles: new Set(),

  setActiveProject: (id) => set({ activeProjectId: id }),

  createProject: (name) => {
    const id = 'proj_' + Date.now();
    set((s) => ({ projects: [...s.projects, { id, name, createdAt: Date.now(), taskIds: [] }] }));
    return id;
  },

  deleteProject: (id) =>
    set((s) => ({
      projects: s.projects.filter((p) => p.id !== id),
      activeProjectId: s.activeProjectId === id ? null : s.activeProjectId,
    })),

  addTaskToProject: (projectId, taskId) =>
    set((s) => ({
      projects: s.projects.map((p) =>
        p.id === projectId ? { ...p, taskIds: [...p.taskIds, taskId] } : p
      ),
    })),

  toggleFileSelection: (name) =>
    set((s) => {
      const next = new Set(s.selectedFiles);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return { selectedFiles: next };
    }),

  selectAllFiles: (names) => set({ selectedFiles: new Set(names) }),
  clearFileSelection: () => set({ selectedFiles: new Set() }),
}));
