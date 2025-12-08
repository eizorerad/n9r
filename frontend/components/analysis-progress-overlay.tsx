'use client'

import { useEffect, useState } from 'react'
import { X, ChevronDown, ChevronUp, Loader2, CheckCircle, AlertCircle, Brain, Search } from 'lucide-react'
import { Progress } from '@/components/ui/progress'
import { Button } from '@/components/ui/button'
import { useAnalysisProgressStore, type ProgressTask } from '@/lib/stores/analysis-progress-store'
import { cn } from '@/lib/utils'

const STAGE_LABELS: Record<string, string> = {
  queued: 'Waiting for worker...',
  initializing: 'Initializing...',
  cloning: 'Cloning repository...',
  counting_lines: 'Counting lines of code...',
  analyzing_complexity: 'Analyzing complexity...',
  static_analysis: 'Running static analysis...',
  calculating_vci: 'Calculating VCI score...',
  saving_results: 'Saving results...',
  completed: 'Complete!',
  failed: 'Failed',
  // Embeddings stages
  waiting: 'Waiting for code analysis...',
  chunking: 'Chunking code files...',
  embedding: 'Generating embeddings...',
  storing: 'Storing vectors...',
  indexing: 'Storing vectors in Qdrant...',
  // Semantic cache stages
  computing: 'Computing clusters and outliers...',
  generating_insights: 'Generating AI insights...',
  // AI Scan stages
  pending: 'Waiting to start...',
  generating_view: 'Generating repository view...',
  scanning: 'Running AI models...',
  merging: 'Merging results...',
  investigating: 'Investigating issues...',
}

function TaskIcon({ task }: { task: ProgressTask }) {
  if (task.status === 'completed') {
    return <CheckCircle className="h-4 w-4 text-green-500" />
  }
  if (task.status === 'failed') {
    return <AlertCircle className="h-4 w-4 text-red-500" />
  }
  if (task.type === 'embeddings') {
    // Show muted icon when waiting for analysis to complete
    const isWaiting = task.stage === 'waiting'
    return <Brain className={cn(
      "h-4 w-4",
      isWaiting ? "text-muted-foreground" : "text-purple-500 animate-pulse"
    )} />
  }
  if (task.type === 'semantic_cache') {
    return <Brain className="h-4 w-4 text-amber-500 animate-pulse" />
  }
  if (task.type === 'ai_scan') {
    return <Brain className="h-4 w-4 text-emerald-500 animate-pulse" />
  }
  return <Search className="h-4 w-4 text-blue-500 animate-pulse" />
}

function TaskItem({ task }: { task: ProgressTask }) {
  const isActive = task.status === 'pending' || task.status === 'running'
  const stageLabel = STAGE_LABELS[task.stage] || task.stage || 'Processing...'
  
  return (
    <div className={cn(
      "p-3 rounded-lg border transition-colors",
      isActive 
        ? "bg-card border-border" 
        : task.status === 'completed'
          ? "bg-green-500/5 border-green-500/20"
          : "bg-red-500/5 border-red-500/20"
    )}>
      <div className="flex items-center gap-2 mb-2">
        <TaskIcon task={task} />
        <span className="text-sm font-medium flex-1 truncate">
          {task.type === 'analysis' 
            ? 'Code Analysis' 
            : task.type === 'ai_scan' 
              ? 'AI Scan' 
              : task.type === 'semantic_cache'
                ? 'Semantic Analysis'
                : 'Semantic Embeddings'}
        </span>
        {isActive && (
          <span className="text-xs text-muted-foreground">
            {task.progress}%
          </span>
        )}
      </div>
      
      {isActive && (
        <>
          <Progress value={task.progress} className="h-1.5 mb-1.5" />
          <p className="text-xs text-muted-foreground truncate">
            {task.message || stageLabel}
          </p>
        </>
      )}
      
      {task.status === 'completed' && (
        <p className="text-xs text-green-500">
          Completed successfully
        </p>
      )}
      
      {task.status === 'failed' && (
        <p className="text-xs text-red-500">
          {task.message || 'An error occurred'}
        </p>
      )}
    </div>
  )
}

export function AnalysisProgressOverlay() {
  const { tasks, minimized, setMinimized, clearCompletedTasks } = useAnalysisProgressStore()
  const [mounted, setMounted] = useState(false)
  
  // Prevent hydration mismatch
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true)
  }, [])
  
  // Debug: log tasks whenever they change
  useEffect(() => {
    console.log('[ProgressOverlay] Tasks updated:', {
      count: Object.keys(tasks).length,
      tasks: Object.values(tasks).map(t => ({ id: t.id, type: t.type, status: t.status, progress: t.progress }))
    })
  }, [tasks])
  
  const taskList = Object.values(tasks)
  const activeTasks = taskList.filter(t => t.status === 'pending' || t.status === 'running')
  const completedTasks = taskList.filter(t => t.status === 'completed' || t.status === 'failed')
  const hasCompletedTasks = completedTasks.length > 0
  
  // Auto-clear completed tasks after 5 seconds
  useEffect(() => {
    if (completedTasks.length > 0 && activeTasks.length === 0) {
      const timer = setTimeout(() => {
        clearCompletedTasks()
      }, 5000)
      return () => clearTimeout(timer)
    }
  }, [completedTasks.length, activeTasks.length, clearCompletedTasks])
  
  if (!mounted || taskList.length === 0) {
    return null
  }
  
  return (
    <div className="fixed bottom-4 right-4 z-50 w-80 animate-in slide-in-from-bottom-2 fade-in duration-300">
      <div className="bg-background/95 backdrop-blur-lg rounded-xl border border-border shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-muted/30">
          <div className="flex items-center gap-2">
            {activeTasks.length > 0 && (
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
            )}
            <span className="text-sm font-medium">
              {activeTasks.length > 0 
                ? `${activeTasks.length} task${activeTasks.length > 1 ? 's' : ''} running`
                : 'Tasks completed'
              }
            </span>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => setMinimized(!minimized)}
            >
              {minimized ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
            {hasCompletedTasks && activeTasks.length === 0 && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={clearCompletedTasks}
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
        
        {/* Content */}
        {!minimized && (
          <div className="p-3 space-y-2 max-h-80 overflow-y-auto">
            {/* Active tasks first */}
            {activeTasks.map(task => (
              <TaskItem key={task.id} task={task} />
            ))}
            
            {/* Completed tasks */}
            {completedTasks.map(task => (
              <TaskItem key={task.id} task={task} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
