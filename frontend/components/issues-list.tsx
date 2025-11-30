'use client'

import { useState } from 'react'
import { AlertCircle, AlertTriangle, Info, ChevronRight, FileCode, Wrench, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

interface Issue {
  id: string
  type: string
  severity: 'high' | 'medium' | 'low'
  title: string
  description: string
  file_path: string | null
  line_start: number | null
  confidence: number
  status: string
  auto_fixable: boolean
}

interface IssuesListProps {
  issues: Issue[]
  className?: string
  onIssueClick?: (issue: Issue) => void
  onFixClick?: (issue: Issue) => Promise<void>
}

const severityConfig = {
  high: {
    icon: AlertCircle,
    color: 'text-red-400',
    bg: 'bg-red-400/10',
    border: 'border-red-400/30',
    label: 'High',
  },
  medium: {
    icon: AlertTriangle,
    color: 'text-yellow-400',
    bg: 'bg-yellow-400/10',
    border: 'border-yellow-400/30',
    label: 'Medium',
  },
  low: {
    icon: Info,
    color: 'text-blue-400',
    bg: 'bg-blue-400/10',
    border: 'border-blue-400/30',
    label: 'Low',
  },
}

export function IssuesList({ issues, className, onIssueClick, onFixClick }: IssuesListProps) {
  const [fixingIssueId, setFixingIssueId] = useState<string | null>(null)
  if (!issues || issues.length === 0) {
    return (
      <div className={cn('rounded-xl border border-gray-800 bg-gray-900/50 p-6', className)}>
        <h3 className="text-sm font-medium text-gray-400 mb-4">Issues</h3>
        <div className="text-center py-8 text-gray-500">
          <AlertCircle className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p>No issues found</p>
        </div>
      </div>
    )
  }

  // Group by severity
  const highIssues = issues.filter(i => i.severity === 'high')
  const mediumIssues = issues.filter(i => i.severity === 'medium')
  const lowIssues = issues.filter(i => i.severity === 'low')

  return (
    <div className={cn('rounded-xl border border-gray-800 bg-gray-900/50', className)}>
      <div className="p-4 border-b border-gray-800 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-400">Issues ({issues.length})</h3>
        <div className="flex gap-3 text-xs">
          {highIssues.length > 0 && (
            <span className="flex items-center gap-1 text-red-400">
              <AlertCircle className="h-3 w-3" />
              {highIssues.length}
            </span>
          )}
          {mediumIssues.length > 0 && (
            <span className="flex items-center gap-1 text-yellow-400">
              <AlertTriangle className="h-3 w-3" />
              {mediumIssues.length}
            </span>
          )}
          {lowIssues.length > 0 && (
            <span className="flex items-center gap-1 text-blue-400">
              <Info className="h-3 w-3" />
              {lowIssues.length}
            </span>
          )}
        </div>
      </div>
      
      <div className="divide-y divide-gray-800 max-h-96 overflow-y-auto">
        {issues.map((issue) => {
          const config = severityConfig[issue.severity]
          const Icon = config.icon
          const isFixing = fixingIssueId === issue.id
          const isBeingFixed = issue.status === 'fixing' || issue.status === 'queued'
          
          const handleFixClick = async (e: React.MouseEvent) => {
            e.stopPropagation()
            if (!onFixClick || isFixing || isBeingFixed) return
            
            setFixingIssueId(issue.id)
            try {
              await onFixClick(issue)
            } finally {
              setFixingIssueId(null)
            }
          }
          
          return (
            <div
              key={issue.id}
              className="w-full p-4 hover:bg-gray-800/50 transition-colors group"
            >
              <div className="flex items-start gap-3">
                <button
                  onClick={() => onIssueClick?.(issue)}
                  className="flex-1 text-left flex items-start gap-3"
                >
                  <div className={cn(
                    'mt-0.5 p-1.5 rounded-lg',
                    config.bg
                  )}>
                    <Icon className={cn('h-4 w-4', config.color)} />
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className={cn(
                        'text-xs px-2 py-0.5 rounded-full border',
                        config.bg, config.border, config.color
                      )}>
                        {config.label}
                      </span>
                      <span className="text-xs text-gray-500 truncate">
                        {issue.type}
                      </span>
                      {issue.auto_fixable && issue.status === 'open' && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-green-400/10 text-green-400 border border-green-400/30">
                          Auto-fixable
                        </span>
                      )}
                      {isBeingFixed && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-blue-400/10 text-blue-400 border border-blue-400/30 flex items-center gap-1">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Fixing...
                        </span>
                      )}
                      {issue.status === 'fix_pending' && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-400/10 text-yellow-400 border border-yellow-400/30">
                          PR Pending
                        </span>
                      )}
                      {issue.status === 'fixed' && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-green-400/10 text-green-400 border border-green-400/30">
                          Fixed
                        </span>
                      )}
                    </div>
                    
                    <h4 className="text-sm font-medium text-white mb-1 line-clamp-1">
                      {issue.title}
                    </h4>
                    
                    {issue.file_path && (
                      <div className="flex items-center gap-1 text-xs text-gray-500">
                        <FileCode className="h-3 w-3" />
                        <span className="truncate">{issue.file_path}</span>
                        {issue.line_start && (
                          <span>:{issue.line_start}</span>
                        )}
                      </div>
                    )}
                  </div>
                </button>
                
                <div className="flex items-center gap-2">
                  {issue.auto_fixable && issue.status === 'open' && onFixClick && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleFixClick}
                      disabled={isFixing || isBeingFixed}
                      className="h-8 px-3 text-xs border-green-500/30 text-green-400 hover:bg-green-500/10 hover:text-green-300"
                    >
                      {isFixing ? (
                        <Loader2 className="h-3 w-3 animate-spin mr-1" />
                      ) : (
                        <Wrench className="h-3 w-3 mr-1" />
                      )}
                      Fix
                    </Button>
                  )}
                  <ChevronRight className="h-4 w-4 text-gray-600 group-hover:text-gray-400 transition-colors" />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
