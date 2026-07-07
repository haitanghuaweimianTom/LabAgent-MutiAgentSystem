import { create } from 'zustand';

interface LayoutState {
  sidebarCollapsed: boolean;
  detailPanelOpen: boolean;
  detailPanelContent: {
    type: 'task' | 'agent' | null;
    taskId?: string;
    agentName?: string;
  } | null;
  toggleSidebar: () => void;
  openDetailPanel: (content: LayoutState['detailPanelContent']) => void;
  closeDetailPanel: () => void;
}

export const useLayoutStore = create<LayoutState>((set) => ({
  sidebarCollapsed: false,
  detailPanelOpen: false,
  detailPanelContent: null,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  openDetailPanel: (content) => set({ detailPanelOpen: true, detailPanelContent: content }),
  closeDetailPanel: () => set({ detailPanelOpen: false, detailPanelContent: null }),
}));
