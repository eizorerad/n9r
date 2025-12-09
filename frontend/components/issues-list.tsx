'use client'

import { useState } from 'react'
import { AlertCircle, AlertTriangle, Info, ChevronRight, ChevronDown, FileCode, Wrench, Loader2, Minimize2, Maximize2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

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
  onFixClick?: (issue: Issue) => Promise<void>
}

const severityConfig = {
  high: {
    icon: AlertCircle,
    color: 'text-white',
    iconColor: 'text-red-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'High',
  },
  medium: {
    icon: AlertTriangle,
    color: 'text-white',
    iconColor: 'text-amber-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'Medium',
  },
  low: {
    icon: Info,
    color: 'text-white',
    iconColor: 'text-blue-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'Low',
  },
}

export function IssuesList({ issues, className, onFixClick }: IssuesListProps) {
  const [fixingIssueId, setFixingIssueId] = useState<string | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  // Toggle individual issue
  const toggleIssue = (id: string, isOpen: boolean) => {
    setExpandedIds(prev => {
      const next = new Set(prev)
      if (isOpen) {
        next.add(id)
      } else {
        next.delete(id)
      }
      return next
    })
  }

  // Toggle all issues
  const toggleAll = () => {
    setExpandedIds(prev => {
      const allIds = issues.map(i => i.id)
      if (prev.size === allIds.length) {
        return new Set()
      } else {
        return new Set(allIds)
      }
    })
  }

  if (!issues || issues.length === 0) {
    return (
      <Card className={cn('border-border/50 glass-panel', className)}>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Issues</CardTitle>
        </CardHeader>
        <CardContent className="text-center py-12 text-muted-foreground/50">
          <AlertCircle className="h-10 w-10 mx-auto mb-3 opacity-50" />
          <p>No issues found</p>
        </CardContent>
      </Card>
    )
  }

  // Group by severity
  const highIssues = issues.filter(i => i.severity === 'high')
  const mediumIssues = issues.filter(i => i.severity === 'medium')
  const lowIssues = issues.filter(i => i.severity === 'low')

  return (
    <Card className={cn('border-border/50 glass-panel overflow-hidden flex flex-col h-full', className)}>
      <CardHeader className="py-2 border-b border-border/50 bg-muted/30 flex-none px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground">Issues ({issues.length})</CardTitle>
          <div className="flex items-center gap-4">
            <div className="flex gap-3 text-xs font-medium">
              {highIssues.length > 0 && (
                <span className="flex items-center gap-1.5 text-destructive">
                  <AlertCircle className="h-3.5 w-3.5" />
                  {highIssues.length}
                </span>
              )}
              {mediumIssues.length > 0 && (
                <span className="flex items-center gap-1.5 text-amber-500">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  {mediumIssues.length}
                </span>
              )}
              {lowIssues.length > 0 && (
                <span className="flex items-center gap-1.5 text-blue-500">
                  <Info className="h-3.5 w-3.5" />
                  {lowIssues.length}
                </span>
              )}
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={toggleAll}
              title={expandedIds.size === issues.length ? "Collapse all" : "Expand all"}
            >
              {expandedIds.size === issues.length ? (
                <Minimize2 className="h-3.5 w-3.5" />
              ) : (
                <Maximize2 className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
        </div>
      </CardHeader>

      <div className="divide-y divide-border/50 flex-1 min-h-0 overflow-y-auto">
        {issues.map((issue) => {
          const config = severityConfig[issue.severity]
          const Icon = config.icon
          const isFixing = fixingIssueId === issue.id
          const isBeingFixed = issue.status === 'fixing' || issue.status === 'queued'
          const expanded = expandedIds.has(issue.id)

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
            <Collapsible
              key={issue.id}
              open={expanded}
              onOpenChange={(open) => toggleIssue(issue.id, open)}
            >
              <CollapsibleTrigger asChild>
                <div className="w-full p-4 hover:bg-muted/30 transition-colors group cursor-pointer">
                  <div className="flex items-start gap-4">
                    <div className={cn(
                      'mt-0.5 p-2 rounded-lg shrink-0',
                      config.bg
                    )}>
                      <Icon className={cn('h-4 w-4', config.iconColor)} />
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                        <Badge variant="outline" className={cn(
                          'text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full border',
                          config.bg, config.border, config.color
                        )}>
                          {config.label}
                        </Badge>
                        <span className="text-xs text-muted-foreground truncate font-mono">
                          {issue.type}
                        </span>
                        {issue.auto_fixable && issue.status === 'open' && (
                          <Badge variant="outline" className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-500 border-emerald-500/20">
                            Auto-fixable
                          </Badge>
                        )}
                        {isBeingFixed && (
                          <Badge variant="outline" className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-500 border-blue-500/20 flex items-center gap-1">
                            <Loader2 className="h-3 w-3 animate-spin" />
                            Fixing...
                          </Badge>
                        )}
                        {issue.status === 'fix_pending' && (
                          <Badge variant="outline" className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-500 border-amber-500/20">
                            PR Pending
                          </Badge>
                        )}
                        {issue.status === 'fixed' && (
                          <Badge variant="outline" className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-500 border-emerald-500/20">
                            Fixed
                          </Badge>
                        )}
                      </div>

                      <h4 className="text-sm font-medium text-foreground mb-1.5 line-clamp-1 group-hover:text-primary transition-colors">
                        {issue.title}
                      </h4>

                      {issue.file_path && (
                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-mono">
                          <FileCode className="h-3 w-3" />
                          <span className="truncate">{issue.file_path}</span>
                          {issue.line_start && (
                            <span className="text-muted-foreground/60">:{issue.line_start}</span>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 self-start mt-1">
                      {issue.auto_fixable && issue.status === 'open' && onFixClick && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={handleFixClick}
                          disabled={isFixing || isBeingFixed}
                          className="h-8 px-3 text-xs border-emerald-500/30 text-emerald-500 hover:bg-emerald-500/10 hover:text-emerald-600 hover:border-emerald-500/50"
                        >
                          {isFixing ? (
                            <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
                          ) : (
                            <Wrench className="h-3 w-3 mr-1.5" />
                          )}
                          Fix
                        </Button>
                      )}
                      {expanded ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground/50 group-hover:text-muted-foreground transition-colors" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground/50 group-hover:text-muted-foreground transition-colors" />
                      )}
                    </div>
                  </div>
                </div>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="px-4 pb-4 pl-[4.5rem] text-sm text-muted-foreground">
                  <p>{issue.description}</p>
                </div>
              </CollapsibleContent>
            </Collapsible>
          )
        })}
      </div>
    </Card>
  )
}
