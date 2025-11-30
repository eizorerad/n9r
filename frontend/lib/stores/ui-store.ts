import { create } from 'zustand'

interface UIState {
  // Sidebar
  sidebarOpen: boolean
  sidebarCollapsed: boolean
  
  // Modals
  connectRepoModalOpen: boolean
  settingsModalOpen: boolean
  
  // IDE panels
  fileTreeOpen: boolean
  chatPanelOpen: boolean
  agentLogsOpen: boolean
  
  // Selected items
  selectedRepoId: string | null
  selectedIssueId: string | null
  selectedFileId: string | null
  
  // Actions
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  setSidebarCollapsed: (collapsed: boolean) => void
  
  openConnectRepoModal: () => void
  closeConnectRepoModal: () => void
  openSettingsModal: () => void
  closeSettingsModal: () => void
  
  toggleFileTree: () => void
  toggleChatPanel: () => void
  toggleAgentLogs: () => void
  
  setSelectedRepo: (id: string | null) => void
  setSelectedIssue: (id: string | null) => void
  setSelectedFile: (id: string | null) => void
  
  resetUI: () => void
}

const initialState = {
  sidebarOpen: true,
  sidebarCollapsed: false,
  connectRepoModalOpen: false,
  settingsModalOpen: false,
  fileTreeOpen: true,
  chatPanelOpen: false,
  agentLogsOpen: false,
  selectedRepoId: null,
  selectedIssueId: null,
  selectedFileId: null,
}

export const useUIStore = create<UIState>()((set) => ({
  ...initialState,

  // Sidebar actions
  toggleSidebar: () =>
    set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  
  setSidebarOpen: (sidebarOpen) =>
    set({ sidebarOpen }),
  
  setSidebarCollapsed: (sidebarCollapsed) =>
    set({ sidebarCollapsed }),

  // Modal actions
  openConnectRepoModal: () =>
    set({ connectRepoModalOpen: true }),
  
  closeConnectRepoModal: () =>
    set({ connectRepoModalOpen: false }),
  
  openSettingsModal: () =>
    set({ settingsModalOpen: true }),
  
  closeSettingsModal: () =>
    set({ settingsModalOpen: false }),

  // IDE panel actions
  toggleFileTree: () =>
    set((state) => ({ fileTreeOpen: !state.fileTreeOpen })),
  
  toggleChatPanel: () =>
    set((state) => ({ chatPanelOpen: !state.chatPanelOpen })),
  
  toggleAgentLogs: () =>
    set((state) => ({ agentLogsOpen: !state.agentLogsOpen })),

  // Selection actions
  setSelectedRepo: (selectedRepoId) =>
    set({ selectedRepoId }),
  
  setSelectedIssue: (selectedIssueId) =>
    set({ selectedIssueId }),
  
  setSelectedFile: (selectedFileId) =>
    set({ selectedFileId }),

  // Reset
  resetUI: () =>
    set(initialState),
}))
