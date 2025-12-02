import { create } from 'zustand'

export type TaskStatus = 'idle' | 'pending' | 'running' | 'completed' | 'failed'

export interface ProgressTask {
  id: string
  type: 'analysis' | 'embeddings'
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
}

export const useAnalysisProgressStore = create<AnalysisProgressState>((set, get) => ({
  tasks: {},
  minimized: false,
  
  addTask: (task) => {
    set((state) => ({
      tasks: {
        ...state.tasks,
        [task.id]: {
          ...task,
          startedAt: Date.now(),
        },
      },
      minimized: false, // Expand when new task starts
    }))
  },
  
  updateTask: (id, updates) => {
    set((state) => {
      const existingTask = state.tasks[id]
      if (!existingTask) return state
      
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
      const { [id]: _, ...rest } = state.tasks
      return { tasks: rest }
    })
  },
  
  clearCompletedTasks: () => {
    set((state) => {
      const activeTasks = Object.fromEntries(
        Object.entries(state.tasks).filter(
          ([_, task]) => task.status === 'pending' || task.status === 'running'
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
}))

// Helper to generate task IDs
export function getAnalysisTaskId(repositoryId: string) {
  return `analysis-${repositoryId}`
}

export function getEmbeddingsTaskId(repositoryId: string) {
  return `embeddings-${repositoryId}`
}
