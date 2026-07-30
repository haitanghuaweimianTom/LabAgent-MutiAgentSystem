// 全局可视化设计模式 —— zustand store
//
// 照 useAppStore.ts 的 persist 模式：create()(persist(...)) + localStorage 'design-overrides'。
// 只持久化 entries/groups/savedAt（mode/selectedId 是运行时状态，不持久化）。

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { DesignMode, SizeOverride, PersistedDesign } from './types';

interface DesignState {
  mode: DesignMode;
  selectedId: string | null;
  entries: Record<string, SizeOverride>;
  groups: Record<string, { order: string[] }>;
  savedAt: number | null;

  setMode: (m: DesignMode) => void;
  toggleMode: () => void;
  select: (id: string | null) => void;

  setSize: (id: string, size: SizeOverride) => void;
  setGroupOrder: (groupId: string, order: string[]) => void;
  removeEntry: (id: string) => void;
  clearAll: () => void;

  markSaved: () => void;
  exportJSON: () => string;
  loadPersisted: (data: Partial<PersistedDesign>) => void;
}

export const useDesignStore = create<DesignState>()(
  persist(
    (set, get) => ({
      mode: 'view',
      selectedId: null,
      entries: {},
      groups: {},
      savedAt: null,

      setMode: (m) => set({ mode: m }),
      toggleMode: () =>
        set((s) => ({ mode: s.mode === 'edit' ? 'view' : 'edit', selectedId: s.mode === 'edit' ? s.selectedId : null })),
      select: (id) => set({ selectedId: id }),

      setSize: (id, size) =>
        set((s) => ({
          entries: { ...s.entries, [id]: { ...s.entries[id], ...size } },
        })),
      setGroupOrder: (groupId, order) =>
        set((s) => ({
          groups: { ...s.groups, [groupId]: { order } },
        })),
      removeEntry: (id) =>
        set((s) => {
          const entries = { ...s.entries };
          delete entries[id];
          return { entries, selectedId: s.selectedId === id ? null : s.selectedId };
        }),
      clearAll: () => set({ entries: {}, groups: {}, savedAt: null, selectedId: null }),

      markSaved: () => set({ savedAt: Date.now() }),
      exportJSON: () => {
        const { entries, groups, savedAt } = get();
        return JSON.stringify({ entries, groups, savedAt }, null, 2);
      },
      loadPersisted: (data) =>
        set({
          entries: data.entries || {},
          groups: data.groups || {},
          savedAt: data.savedAt ?? null,
        }),
    }),
    {
      name: 'design-overrides',
      // 只持久化数据，不持久化运行时态（mode/selectedId）
      partialize: (s) => ({
        entries: s.entries,
        groups: s.groups,
        savedAt: s.savedAt,
      }),
    }
  )
);
