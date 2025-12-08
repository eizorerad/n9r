'use client'

import { memo, useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Sparkles, X, AlertTriangle, Info, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react'
import {
  useArchitectureFindings,
  useDismissInsight,
  useDismissDeadCode,
  SemanticAIInsight,
  DeadCodeFinding,
  HotSpotFinding,
} from '@/lib/hooks/use-architecture-findings'

/**
 * SemanticAIInsights component displays AI-generated insights from architecture analysis.
 *
 * **Feature: cluster-map-refactoring**
 * **Validates: Requirements 6.1, 6.2**
 */

interface SemanticAIInsightsProps {
  repositoryId: string
  analysisId?: string | null
  token: string
  className?: string
}

const priorityConfig = {
  high: {
    icon: AlertCircle,
    badge: 'bg-red-500/10 text-red-400 border-red-500/20',
    border: 'border-l-red-500',
  },
  medium: {
    icon: AlertTriangle,
    badge: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    border: 'border-l-amber-500',
  },
  low: {
    icon: Info,
    badge: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    border: 'border-l-blue-500',
  },
}

function SemanticAIInsightsComponent({ repositoryId, analysisId, token, className }: SemanticAIInsightsProps) {
  // Debug: Log props on mount and when they change
  console.log('[SemanticAIInsights] Props:', {
    repositoryId: repositoryId?.slice(0, 8),
    analysisId: analysisId?.slice(0, 8),
    hasToken: !!token,
    tokenLength: token?.length,
  })

  const { data, isLoading, error, status, fetchStatus } = useArchitectureFindings({
    repositoryId,
    analysisId,
    token,
  })

  // Debug: Log query state
  console.log('[SemanticAIInsights] Query:', {
    status,        // 'pending' | 'error' | 'success'
    fetchStatus,   // 'fetching' | 'paused' | 'idle'
    isLoading,
    hasData: !!data,
    insightsCount: data?.insights?.length,
    deadCodeCount: data?.dead_code?.length,
    hotSpotsCount: data?.hot_spots?.length,
    error: error?.message,
  })

  const dismissInsightMutation = useDismissInsight(repositoryId, token, analysisId)
  const dismissDeadCodeMutation = useDismissDeadCode(repositoryId, token, analysisId)

  // Loading state with skeleton
  if (isLoading) {
    return <SemanticAIInsightsSkeleton className={className} />
  }

  // Error state
  if (error) {
    return (
      <Card className={cn('glass-panel border-border/50', className)}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-5 w-5 text-brand-green" />
            Semantic AI Insights
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-6 text-muted-foreground">
            <p className="text-sm">Failed to load insights</p>
            <p className="text-xs mt-1">{error.message}</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Empty state - no data yet
  if (!data) {
    return (
      <Card className={cn('glass-panel border-border/50', className)}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-5 w-5 text-brand-green" />
            Semantic AI Insights (0)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-6 text-muted-foreground">
            <p className="text-sm">No insights available</p>
            <p className="text-xs mt-1">Run an analysis to generate AI insights</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const { summary, insights, dead_code, hot_spots } = data
  const totalCount = insights.length + dead_code.length + hot_spots.length

  // Empty state - analysis complete but no findings
  if (totalCount === 0) {
    return (
      <Card className={cn('glass-panel border-border/50', className)}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-5 w-5 text-brand-green" />
            Semantic AI Insights (0)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-6">
            <p className="text-emerald-400 text-sm">✓ No issues found</p>
            <p className="text-xs text-muted-foreground mt-1">
              Your codebase looks healthy!
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <SemanticAIInsightsContent
      summary={summary}
      insights={insights}
      dead_code={dead_code}
      hot_spots={hot_spots}
      totalCount={totalCount}
      dismissInsightMutation={dismissInsightMutation}
      dismissDeadCodeMutation={dismissDeadCodeMutation}
      className={className}
    />
  )
}

// Separate component to use hooks for expand/collapse state
interface SemanticAIInsightsContentProps {
  summary: {
    health_score: number
    main_concerns: string[]
  }
  insights: SemanticAIInsight[]
  dead_code: DeadCodeFinding[]
  hot_spots: HotSpotFinding[]
  totalCount: number
  dismissInsightMutation: ReturnType<typeof useDismissInsight>
  dismissDeadCodeMutation: ReturnType<typeof useDismissDeadCode>
  className?: string
}

const COLLAPSED_LIMIT = 5

function SemanticAIInsightsContent({
  summary,
  insights,
  dead_code,
  hot_spots,
  totalCount,
  dismissInsightMutation,
  dismissDeadCodeMutation,
  className,
}: SemanticAIInsightsContentProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  // Combine all items into a single list for slicing
  // Order: insights → hot_spots (churn) → dead_code
  // Hot spots (git churn analysis) shown before dead code because
  // call-graph dead code detection has more false positives
  const allItems = useMemo(() => {
    const items: Array<{
      type: 'insight' | 'dead_code' | 'hot_spot'
      data: SemanticAIInsight | DeadCodeFinding | HotSpotFinding
    }> = []
    
    // Add insights first (highest priority - LLM recommendations)
    insights.forEach(insight => items.push({ type: 'insight', data: insight }))
    // Then hot spots (git churn - more reliable signal)
    hot_spots.forEach(finding => items.push({ type: 'hot_spot', data: finding }))
    // Then dead code (call-graph analysis - may have false positives)
    dead_code.forEach(finding => items.push({ type: 'dead_code', data: finding }))
    
    return items
  }, [insights, dead_code, hot_spots])

  const visibleItems = isExpanded ? allItems : allItems.slice(0, COLLAPSED_LIMIT)
  const hiddenCount = totalCount - COLLAPSED_LIMIT
  const showExpandButton = totalCount > COLLAPSED_LIMIT

  return (
    <Card className={cn('glass-panel border-border/50', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-5 w-5 text-brand-green" />
            Semantic AI Insights ({totalCount})
          </CardTitle>
          <Badge variant="outline" className={cn(
            summary.health_score >= 80 ? 'bg-emerald-500/10 text-emerald-400' :
            summary.health_score >= 60 ? 'bg-amber-500/10 text-amber-400' :
            'bg-red-500/10 text-red-400'
          )}>
            Health: {summary.health_score}/100
          </Badge>
        </div>
        {summary.main_concerns.length > 0 && (
          <p className="text-sm text-muted-foreground mt-1">
            {summary.main_concerns[0]}
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Render visible items */}
        {visibleItems.map((item) => {
          if (item.type === 'insight') {
            const insight = item.data as SemanticAIInsight
            return (
              <InsightCard
                key={`insight-${insight.id}`}
                insight={insight}
                onDismiss={() => dismissInsightMutation.mutate(insight.id)}
                isLoading={dismissInsightMutation.isPending}
              />
            )
          } else if (item.type === 'dead_code') {
            const finding = item.data as DeadCodeFinding
            return (
              <DeadCodeCard
                key={`dead-${finding.id}`}
                finding={finding}
                onDismiss={() => dismissDeadCodeMutation.mutate(finding.id)}
                isLoading={dismissDeadCodeMutation.isPending}
              />
            )
          } else {
            const finding = item.data as HotSpotFinding
            return <HotSpotCard key={`hot-${finding.id}`} finding={finding} />
          }
        })}

        {/* Show all / Show less button */}
        {showExpandButton && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full text-muted-foreground hover:text-foreground"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            {isExpanded ? (
              <>
                <ChevronUp className="h-4 w-4 mr-2" />
                Show less
              </>
            ) : (
              <>
                <ChevronDown className="h-4 w-4 mr-2" />
                Show all ({hiddenCount} more)
              </>
            )}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

interface InsightCardProps {
  insight: SemanticAIInsight
  onDismiss: () => void
  isLoading: boolean
}

function InsightCard({ insight, onDismiss, isLoading }: InsightCardProps) {
  const config = priorityConfig[insight.priority] || priorityConfig.medium
  const Icon = config.icon

  return (
    <div className={cn(
      'p-4 rounded-lg bg-background/30 border border-border/50 border-l-2',
      config.border
    )}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 flex-1">
          <Icon className={cn('h-5 w-5 mt-0.5 shrink-0', 
            insight.priority === 'high' ? 'text-red-400' :
            insight.priority === 'medium' ? 'text-amber-400' : 'text-blue-400'
          )} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <h4 className="font-medium text-sm">{insight.title}</h4>
              <Badge variant="outline" className={cn('text-xs capitalize', config.badge)}>
                {insight.priority}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">{insight.description}</p>
            {insight.evidence && (
              <p className="text-xs text-muted-foreground mt-2">
                <span className="font-medium">Evidence:</span> {insight.evidence}
              </p>
            )}
            {insight.suggested_action && (
              <p className="text-xs mt-2">
                <span className="font-medium text-brand-green">Action:</span>{' '}
                <span className="text-muted-foreground">{insight.suggested_action}</span>
              </p>
            )}
            {insight.affected_files.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {insight.affected_files.slice(0, 3).map((file, idx) => (
                  <code key={idx} className="text-xs px-1.5 py-0.5 rounded bg-background/50">
                    {file.split('/').pop()}
                  </code>
                ))}
                {insight.affected_files.length > 3 && (
                  <span className="text-xs text-muted-foreground">
                    +{insight.affected_files.length - 3} more
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0"
          onClick={onDismiss}
          disabled={isLoading}
          title="Dismiss insight"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

interface DeadCodeCardProps {
  finding: DeadCodeFinding
  onDismiss: () => void
  isLoading: boolean
}

function DeadCodeCard({ finding, onDismiss, isLoading }: DeadCodeCardProps) {
  return (
    <div className="p-4 rounded-lg bg-background/30 border border-border/50 border-l-2 border-l-purple-500">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 flex-1">
          <span className="text-purple-400 mt-0.5">🗑️</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <code className="text-sm font-medium">{finding.function_name}</code>
              {finding.confidence === 1.0 && (
                <Badge variant="outline" className="text-xs bg-purple-500/10 text-purple-400 border-purple-500/20">
                  call-graph proven
                </Badge>
              )}
              <span className="text-xs text-muted-foreground">
                {finding.line_count} lines
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              <code>{finding.file_path}</code> (lines {finding.line_start}-{finding.line_end})
            </p>
            <p className="text-sm text-muted-foreground mt-1">{finding.evidence}</p>
            {finding.suggested_action && (
              <p className="text-xs mt-2">
                <span className="font-medium text-brand-green">Action:</span>{' '}
                <span className="text-muted-foreground">{finding.suggested_action}</span>
              </p>
            )}
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0"
          onClick={onDismiss}
          disabled={isLoading}
          title="Dismiss finding"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

interface HotSpotCardProps {
  finding: HotSpotFinding
}

function HotSpotCard({ finding }: HotSpotCardProps) {
  return (
    <div className="p-4 rounded-lg bg-background/30 border border-border/50 border-l-2 border-l-orange-500">
      <div className="flex items-start gap-3">
        <span className="text-orange-400 mt-0.5">🔥</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <code className="text-sm">{finding.file_path}</code>
            <Badge variant="outline" className="text-xs bg-orange-500/10 text-orange-400 border-orange-500/20">
              {finding.changes_90d} changes
            </Badge>
            {finding.coverage_rate !== null && (
              <Badge variant="outline" className={cn('text-xs',
                finding.coverage_rate >= 0.7 ? 'bg-emerald-500/10 text-emerald-400' :
                finding.coverage_rate >= 0.5 ? 'bg-amber-500/10 text-amber-400' :
                'bg-red-500/10 text-red-400'
              )}>
                {Math.round(finding.coverage_rate * 100)}% coverage
              </Badge>
            )}
          </div>
          {finding.risk_factors.length > 0 && (
            <ul className="text-sm text-muted-foreground mt-1 space-y-0.5">
              {finding.risk_factors.map((factor, idx) => (
                <li key={idx} className="flex items-center gap-1">
                  <span className="text-amber-400">•</span> {factor}
                </li>
              ))}
            </ul>
          )}
          {finding.suggested_action && (
            <p className="text-xs mt-2">
              <span className="font-medium text-brand-green">Action:</span>{' '}
              <span className="text-muted-foreground">{finding.suggested_action}</span>
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function SemanticAIInsightsSkeleton({ className }: { className?: string }) {
  return (
    <Card className={cn('glass-panel border-border/50', className)}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-5 w-5 text-brand-green" />
          Semantic AI Insights
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="p-4 rounded-lg bg-background/30 border border-border/50">
            <div className="flex items-start gap-3">
              <Skeleton className="h-5 w-5 rounded" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-2/3" />
              </div>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

// Memoize to prevent unnecessary re-renders
export const SemanticAIInsights = memo(SemanticAIInsightsComponent, (prevProps, nextProps) => {
  return (
    prevProps.repositoryId === nextProps.repositoryId &&
    prevProps.analysisId === nextProps.analysisId &&
    prevProps.token === nextProps.token &&
    prevProps.className === nextProps.className
  )
})

SemanticAIInsights.displayName = 'SemanticAIInsights'
