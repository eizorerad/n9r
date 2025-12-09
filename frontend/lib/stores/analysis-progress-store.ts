import { create } from 'zustand'

export type TaskStatus = 'idle' | 'pending' | 'running' | 'completed' | 'failed'

export interface ProgressTask {
  id: string
  type: 'analysis' | 'embeddings' | 'semantic_cache' | 'ai_scan'
  repositoryId: string
  repositoryName?: string
  status: TaskStatus
  progress: number
  stage: string
  message: string | null
  startedAt: number
}

interface AnalysisProgressState {
  tasks: Record<string, ProgressTask>
  minimized: boolean
  
  // Actions
  addTask: (task: Omit<ProgressTask, 'startedAt'>) => void
  updateTask: (id: string, updates: Partial<ProgressTask>) => void
  removeTask: (id: string) => void
  clearCompletedTasks: () => void
  setMinimized: (minimized: boolean) => void
  
  // Computed
  getActiveTasks: () => ProgressTask[]
  hasActiveTasks: () => boolean
  hasTask: (id: string) => boolean
}

export const useAnalysisProgressStore = create<AnalysisProgressState>((set, get) => ({
  tasks: {},
  minimized: false,
  
  addTask: (task) => {
    console.log('[AnalysisProgressStore] addTask called:', task.id, task.type)
    set((state) => {
      const newTasks = {
        ...state.tasks,
        [task.id]: {
          ...task,
          startedAt: Date.now(),
        },
      }
      console.log('[AnalysisProgressStore] New tasks state:', Object.keys(newTasks))
      return {
        tasks: newTasks,
        minimized: false, // Expand when new task starts
      }
    })
  },
  
  updateTask: (id, updates) => {
    console.log('[AnalysisProgressStore] updateTask called:', id, updates)
    set((state) => {
      const existingTask = state.tasks[id]
      if (!existingTask) {
        console.log('[AnalysisProgressStore] Task not found:', id)
        return state
      }
      
      return {
        tasks: {
          ...state.tasks,
          [id]: {
            ...existingTask,
            ...updates,
          },
        },
      }
    })
  },
  
  removeTask: (id) => {
    set((state) => {
      const { [id]: removed, ...rest } = state.tasks
      void removed // Explicitly mark as intentionally unused
      return { tasks: rest }
    })
  },
  
  clearCompletedTasks: () => {
    set((state) => {
      const activeTasks = Object.fromEntries(
        Object.entries(state.tasks).filter(
          ([, task]) => task.status === 'pending' || task.status === 'running'
        )
      )
      return { tasks: activeTasks }
    })
  },
  
  setMinimized: (minimized) => set({ minimized }),
  
  getActiveTasks: () => {
    const { tasks } = get()
    return Object.values(tasks).filter(
      (task) => task.status === 'pending' || task.status === 'running'
    )
  },
  
  hasActiveTasks: () => {
    const { tasks } = get()
    return Object.values(tasks).some(
      (task) => task.status === 'pending' || task.status === 'running'
    )
  },
  
  hasTask: (id) => {
    const { tasks } = get()
    return id in tasks
  },
}))

// Helper to generate task IDs
export function getAnalysisTaskId(repositoryId: string) {
  return `analysis-${repositoryId}`
}

export function getEmbeddingsTaskId(repositoryId: string) {
  return `embeddings-${repositoryId}`
}

export function getSemanticCacheTaskId(repositoryId: string) {
  return `semantic_cache-${repositoryId}`
}

export function getAIScanTaskId(repositoryId: string) {
  return `ai_scan-${repositoryId}`
}
