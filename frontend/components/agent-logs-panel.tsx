'use client'

import { useEffect, useState, useRef } from 'react'
import { 
  Activity, 
  CheckCircle, 
  XCircle, 
  AlertTriangle, 
  Loader2,
  ChevronDown,
  ChevronRight
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface LogEntry {
  timestamp: string
  stage: string
  message: string
  details?: Record<string, unknown>
}

interface AgentLogsPanelProps {
  analysisId?: string
  logs?: LogEntry[]
  status?: 'pending' | 'running' | 'completed' | 'failed'
  className?: string
}

const stageIcons: Record<string, React.ReactNode> = {
  diagnosis: <Activity className="h-4 w-4" />,
  fix: <Activity className="h-4 w-4" />,
  test: <Activity className="h-4 w-4" />,
  validation: <Activity className="h-4 w-4" />,
  completed: <CheckCircle className="h-4 w-4 text-green-500" />,
  failed: <XCircle className="h-4 w-4 text-red-500" />,
  error: <AlertTriangle className="h-4 w-4 text-yellow-500" />,
}

const stageColors: Record<string, string> = {
  diagnosis: 'border-blue-500/50',
  fix: 'border-purple-500/50',
  test: 'border-cyan-500/50',
  validation: 'border-yellow-500/50',
  completed: 'border-green-500/50',
  failed: 'border-red-500/50',
  error: 'border-orange-500/50',
}

export function AgentLogsPanel({ 
  analysisId, 
  logs: initialLogs = [], 
  status = 'pending',
  className 
}: AgentLogsPanelProps) {
  const [logs, setLogs] = useState<LogEntry[]>(initialLogs)
  const [isStreaming, setIsStreaming] = useState(false)
  const [expandedLogs, setExpandedLogs] = useState<Set<number>>(new Set())
  const logsEndRef = useRef<HTMLDivElement>(null)

  // Scroll to bottom when new logs arrive
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // SSE streaming for real-time logs
  useEffect(() => {
    if (!analysisId || status !== 'running') return

    setIsStreaming(true)
    const eventSource = new EventSource(`/api/analyses/${analysisId}/logs`)

    eventSource.onmessage = (event) => {
      try {
        const log = JSON.parse(event.data) as LogEntry
        setLogs(prev => [...prev, log])
      } catch (e) {
        console.error('Failed to parse log:', e)
      }
    }

    eventSource.onerror = () => {
      setIsStreaming(false)
      eventSource.close()
    }

    return () => {
      eventSource.close()
      setIsStreaming(false)
    }
  }, [analysisId, status])

  const toggleExpand = (index: number) => {
    setExpandedLogs(prev => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp)
    return date.toLocaleTimeString('en-US', { 
      hour12: false, 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit' 
    })
  }

  return (
    <div className={cn('flex flex-col h-full bg-gray-900', className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-green-400" />
          <span className="font-medium text-sm">Agent Activity</span>
        </div>
        {isStreaming && (
          <div className="flex items-center gap-1 text-xs text-green-400">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>Live</span>
          </div>
        )}
      </div>

      {/* Status indicator */}
      <div className="px-4 py-2 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Status:</span>
          <StatusBadge status={status} />
        </div>
      </div>

      {/* Logs */}
      <div className="flex-1 overflow-y-auto">
        {logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <Activity className="h-8 w-8 mb-2 opacity-50" />
            <p className="text-sm">No activity yet</p>
            <p className="text-xs mt-1">Logs will appear here when agents run</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-800">
            {logs.map((log, index) => (
              <div 
                key={index}
                className={cn(
                  'px-4 py-3 border-l-2',
                  stageColors[log.stage] || 'border-gray-700'
                )}
              >
                <div className="flex items-start gap-2">
                  <div className="flex-shrink-0 mt-0.5">
                    {stageIcons[log.stage] || <Activity className="h-4 w-4" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-gray-400 uppercase">
                        {log.stage}
                      </span>
                      <span className="text-xs text-gray-600">
                        {formatTime(log.timestamp)}
                      </span>
                    </div>
                    <p className="text-sm text-gray-200 mt-1">
                      {log.message}
                    </p>
                    
                    {/* Details toggle */}
                    {log.details && Object.keys(log.details).length > 0 && (
                      <div className="mt-2">
                        <button
                          onClick={() => toggleExpand(index)}
                          className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300"
                        >
                          {expandedLogs.has(index) ? (
                            <ChevronDown className="h-3 w-3" />
                          ) : (
                            <ChevronRight className="h-3 w-3" />
                          )}
                          Details
                        </button>
                        
                        {expandedLogs.has(index) && (
                          <pre className="mt-2 p-2 bg-gray-800/50 rounded text-xs text-gray-400 overflow-x-auto">
                            {JSON.stringify(log.details, null, 2)}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        <div ref={logsEndRef} />
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { color: string; icon: React.ReactNode }> = {
    pending: { 
      color: 'bg-gray-700 text-gray-300', 
      icon: <Activity className="h-3 w-3" /> 
    },
    running: { 
      color: 'bg-blue-900 text-blue-300', 
      icon: <Loader2 className="h-3 w-3 animate-spin" /> 
    },
    completed: { 
      color: 'bg-green-900 text-green-300', 
      icon: <CheckCircle className="h-3 w-3" /> 
    },
    failed: { 
      color: 'bg-red-900 text-red-300', 
      icon: <XCircle className="h-3 w-3" /> 
    },
  }

  const { color, icon } = config[status] || config.pending

  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
      color
    )}>
      {icon}
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  )
}
