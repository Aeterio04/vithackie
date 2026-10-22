"use client";

import { create } from "zustand";

interface UiState {
  selectedRunId: string | null;
  sidebarCollapsed: boolean;
  setSelectedRunId: (runId: string | null) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedRunId: null,
  sidebarCollapsed: false,
  setSelectedRunId: (runId) => set({ selectedRunId: runId }),
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
}));
