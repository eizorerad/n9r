'use client'

import { memo, useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Sparkles, X, AlertTriangle, Info, AlertCircle, ChevronDown, ChevronUp, HelpCircle, ArrowUpDown } from 'lucide-react'
import {
  useArchitectureFindings,
  useDismissInsight,
  useDismissDeadCode,
  SemanticAIInsight,
  DeadCodeFinding,
  HotSpotFinding,
} from '@/lib/hooks/use-architecture-findings'
import { ScoringFormulaDialog } from '@/components/scoring-formula-dialog'

/**
 * Sort options for findings list
 * **Feature: transparent-scoring-formula**
 * **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
 */
export type SortOption = 'score' | 'type' | 'file'

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
  const [formulaDialogOpen, setFormulaDialogOpen] = useState(false)

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
    return (
      <>
        <SemanticAIInsightsSkeleton className={className} onInfoClick={() => setFormulaDialogOpen(true)} />
        <ScoringFormulaDialog open={formulaDialogOpen} onOpenChange={setFormulaDialogOpen} />
      </>
    )
  }

  // Error state
  if (error) {
    return (
      <>
        <Card className={cn('glass-panel border-border/50', className)}>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-5 w-5 text-brand-green" />
              Semantic AI Insights
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5 ml-1"
                onClick={() => setFormulaDialogOpen(true)}
                title="How scores are calculated"
              >
                <HelpCircle className="h-4 w-4 text-muted-foreground hover:text-foreground" />
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-center py-6 text-muted-foreground">
              <p className="text-sm">Failed to load insights</p>
              <p className="text-xs mt-1">{error.message}</p>
            </div>
          </CardContent>
        </Card>
        <ScoringFormulaDialog open={formulaDialogOpen} onOpenChange={setFormulaDialogOpen} />
      </>
    )
  }

  // Empty state - no data yet
  if (!data) {
    return (
      <>
        <Card className={cn('glass-panel border-border/50', className)}>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-5 w-5 text-brand-green" />
              Semantic AI Insights (0)
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5 ml-1"
                onClick={() => setFormulaDialogOpen(true)}
                title="How scores are calculated"
              >
                <HelpCircle className="h-4 w-4 text-muted-foreground hover:text-foreground" />
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-center py-6 text-muted-foreground">
              <p className="text-sm">No insights available</p>
              <p className="text-xs mt-1">Run an analysis to generate AI insights</p>
            </div>
          </CardContent>
        </Card>
        <ScoringFormulaDialog open={formulaDialogOpen} onOpenChange={setFormulaDialogOpen} />
      </>
    )
  }

  const { summary, insights, dead_code, hot_spots } = data
  const totalCount = insights.length + dead_code.length + hot_spots.length

  // Empty state - analysis complete but no findings
  if (totalCount === 0) {
    return (
      <>
        <Card className={cn('glass-panel border-border/50', className)}>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-5 w-5 text-brand-green" />
              Semantic AI Insights (0)
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5 ml-1"
                onClick={() => setFormulaDialogOpen(true)}
                title="How scores are calculated"
              >
                <HelpCircle className="h-4 w-4 text-muted-foreground hover:text-foreground" />
              </Button>
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
        <ScoringFormulaDialog open={formulaDialogOpen} onOpenChange={setFormulaDialogOpen} />
      </>
    )
  }

  return (
    <>
      <SemanticAIInsightsContent
        summary={summary}
        insights={insights}
        dead_code={dead_code}
        hot_spots={hot_spots}
        totalCount={totalCount}
        dismissInsightMutation={dismissInsightMutation}
        dismissDeadCodeMutation={dismissDeadCodeMutation}
        className={className}
        onInfoClick={() => setFormulaDialogOpen(true)}
      />
      <ScoringFormulaDialog open={formulaDialogOpen} onOpenChange={setFormulaDialogOpen} />
    </>
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
  onInfoClick: () => void
}

const COLLAPSED_LIMIT = 5

/**
 * Type for combined finding items used in sorting
 */
type FindingItem = {
  type: 'insight' | 'dead_code' | 'hot_spot'
  data: SemanticAIInsight | DeadCodeFinding | HotSpotFinding
}

/**
 * Get the score for a finding item (impact_score for dead_code, risk_score for hot_spot)
 * Insights don't have numeric scores, so we map priority to score values
 */
function getItemScore(item: FindingItem): number {
  if (item.type === 'dead_code') {
    return (item.data as DeadCodeFinding).impact_score ?? 0
  } else if (item.type === 'hot_spot') {
    return (item.data as HotSpotFinding).risk_score ?? 0
  } else {
    // Map insight priority to score: high=90, medium=60, low=30
    const insight = item.data as SemanticAIInsight
    return insight.priority === 'high' ? 90 : insight.priority === 'medium' ? 60 : 30
  }
}

/**
 * Get the file path for a finding item
 */
function getItemFilePath(item: FindingItem): string {
  if (item.type === 'dead_code') {
    return (item.data as DeadCodeFinding).file_path
  } else if (item.type === 'hot_spot') {
    return (item.data as HotSpotFinding).file_path
  } else {
    // For insights, use first affected file or empty string
    const insight = item.data as SemanticAIInsight
    return insight.affected_files[0] ?? ''
  }
}

/**
 * Sort findings based on the selected sort option
 * **Feature: transparent-scoring-formula, Property 7: UI Sorting Options**
 * **Validates: Requirements 7.2, 7.3, 7.4**
 */
export function sortFindings(items: FindingItem[], sortOption: SortOption): FindingItem[] {
  const sorted = [...items]
  
  switch (sortOption) {
    case 'score':
      // Sort by impact_score/risk_score descending
      sorted.sort((a, b) => getItemScore(b) - getItemScore(a))
      break
    case 'type':
      // Group by insight_type: insights first, then hot_spots, then dead_code
      const typeOrder = { insight: 0, hot_spot: 1, dead_code: 2 }
      sorted.sort((a, b) => typeOrder[a.type] - typeOrder[b.type])
      break
    case 'file':
      // Sort alphabetically by file_path
      sorted.sort((a, b) => getItemFilePath(a).localeCompare(getItemFilePath(b)))
      break
  }
  
  return sorted
}

function SemanticAIInsightsContent({
  summary,
  insights,
  dead_code,
  hot_spots,
  totalCount,
  dismissInsightMutation,
  dismissDeadCodeMutation,
  className,
  onInfoClick,
}: SemanticAIInsightsContentProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [sortOption, setSortOption] = useState<SortOption>('score')

  // Combine all items into a single list
  const allItems = useMemo(() => {
    const items: FindingItem[] = []
    
    // Add all items without pre-sorting - sorting is handled separately
    insights.forEach(insight => items.push({ type: 'insight', data: insight }))
    hot_spots.forEach(finding => items.push({ type: 'hot_spot', data: finding }))
    dead_code.forEach(finding => items.push({ type: 'dead_code', data: finding }))
    
    return items
  }, [insights, dead_code, hot_spots])

  // Apply sorting based on selected option
  const sortedItems = useMemo(() => {
    return sortFindings(allItems, sortOption)
  }, [allItems, sortOption])

  const visibleItems = isExpanded ? sortedItems : sortedItems.slice(0, COLLAPSED_LIMIT)
  const hiddenCount = totalCount - COLLAPSED_LIMIT
  const showExpandButton = totalCount > COLLAPSED_LIMIT

  return (
    <Card className={cn('glass-panel border-border/50', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-5 w-5 text-brand-green" />
            Semantic AI Insights ({totalCount})
            <Button
              variant="ghost"
              size="icon"
              className="h-5 w-5 ml-1"
              onClick={onInfoClick}
              title="How scores are calculated"
            >
              <HelpCircle className="h-4 w-4 text-muted-foreground hover:text-foreground" />
            </Button>
          </CardTitle>
          <div className="flex items-center gap-2">
            {/* Sort dropdown - Feature: transparent-scoring-formula, Validates: Requirements 7.1 */}
            <Select value={sortOption} onValueChange={(value) => setSortOption(value as SortOption)}>
              <SelectTrigger className="w-[130px] h-8 text-xs">
                <ArrowUpDown className="h-3 w-3 mr-1" />
                <SelectValue placeholder="Sort by" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="score">By Score</SelectItem>
                <SelectItem value="type">By Type</SelectItem>
                <SelectItem value="file">By File</SelectItem>
              </SelectContent>
            </Select>
            <Badge variant="outline" className={cn(
              summary.health_score >= 80 ? 'bg-emerald-500/10 text-emerald-400' :
              summary.health_score >= 60 ? 'bg-amber-500/10 text-amber-400' :
              'bg-red-500/10 text-red-400'
            )}>
              Health: {summary.health_score}/100
            </Badge>
          </div>
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

/**
 * Get color classes for score badge based on score value.
 * - green: 0-39 (low priority)
 * - amber: 40-69 (medium priority)
 * - red: 70-100 (high priority)
 */
function getScoreBadgeClasses(score: number): string {
  if (score < 40) {
    return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
  } else if (score < 70) {
    return 'bg-amber-500/10 text-amber-400 border-amber-500/20'
  } else {
    return 'bg-red-500/10 text-red-400 border-red-500/20'
  }
}

function DeadCodeCard({ finding, onDismiss, isLoading }: DeadCodeCardProps) {
  const impactScore = finding.impact_score ?? 0

  return (
    <div className="p-4 rounded-lg bg-background/30 border border-border/50 border-l-2 border-l-purple-500">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 flex-1">
          <span className="text-purple-400 mt-0.5">🗑️</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <code className="text-sm font-medium">{finding.function_name}</code>
              <Badge variant="outline" className={cn('text-xs', getScoreBadgeClasses(impactScore))}>
                Impact: {Math.round(impactScore)}
              </Badge>
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
  const riskScore = finding.risk_score ?? 0

  return (
    <div className="p-4 rounded-lg bg-background/30 border border-border/50 border-l-2 border-l-orange-500">
      <div className="flex items-start gap-3">
        <span className="text-orange-400 mt-0.5">🔥</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <code className="text-sm">{finding.file_path}</code>
            <Badge variant="outline" className={cn('text-xs', getScoreBadgeClasses(riskScore))}>
              Risk: {Math.round(riskScore)}
            </Badge>
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

function SemanticAIInsightsSkeleton({ className, onInfoClick }: { className?: string; onInfoClick?: () => void }) {
  return (
    <Card className={cn('glass-panel border-border/50', className)}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-5 w-5 text-brand-green" />
          Semantic AI Insights
          {onInfoClick && (
            <Button
              variant="ghost"
              size="icon"
              className="h-5 w-5 ml-1"
              onClick={onInfoClick}
              title="How scores are calculated"
            >
              <HelpCircle className="h-4 w-4 text-muted-foreground hover:text-foreground" />
            </Button>
          )}
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
