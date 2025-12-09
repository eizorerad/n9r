'use client'

import { memo, useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Sparkles, X, AlertTriangle, Info, AlertCircle, ChevronDown, ChevronUp, ChevronRight, HelpCircle, ArrowUpDown, FileCode, Trash2, Flame } from 'lucide-react'
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

// Category config matching AI Scan's dimension pattern
const categoryConfig = {
  dead_code: {
    icon: Trash2,
    label: 'Dead Code',
    color: 'text-white',
    iconColor: 'text-purple-400',
  },
  hot_spot: {
    icon: Flame,
    label: 'Hot Spot',
    color: 'text-white',
    iconColor: 'text-orange-400',
  },
  insight: {
    icon: Sparkles,
    label: 'Insight',
    color: 'text-white',
    iconColor: 'text-green-400',
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

  const { data, isLoading, error, status, fetchStatus, dataUpdatedAt } = useArchitectureFindings({
    repositoryId,
    analysisId,
    token,
  })

  // Debug: Log query state with more detail
  console.log('[SemanticAIInsights] Query:', {
    status,        // 'pending' | 'error' | 'success'
    fetchStatus,   // 'fetching' | 'paused' | 'idle'
    isLoading,
    hasData: !!data,
    insightsCount: data?.insights?.length ?? 0,
    deadCodeCount: data?.dead_code?.length ?? 0,
    hotSpotsCount: data?.hot_spots?.length ?? 0,
    healthScore: data?.summary?.health_score,
    dataUpdatedAt: dataUpdatedAt ? new Date(dataUpdatedAt).toISOString() : null,
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
    <div className={cn('flex flex-col h-full space-y-3', className)}>
      {/* Header with stats */}
      <div className="flex-none flex items-center justify-between px-3 pt-2">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <span className="text-xs font-medium">
            {totalCount} finding{totalCount !== 1 ? 's' : ''}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-5 w-5"
            onClick={onInfoClick}
            title="How scores are calculated"
          >
            <HelpCircle className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
          </Button>
        </div>
        <div className="flex items-center gap-2">
          {/* Sort dropdown */}
          <Select value={sortOption} onValueChange={(value) => setSortOption(value as SortOption)}>
            <SelectTrigger className="w-[100px] h-7 text-[10px]">
              <ArrowUpDown className="h-3 w-3 mr-1" />
              <SelectValue placeholder="Sort" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="score">By Score</SelectItem>
              <SelectItem value="type">By Type</SelectItem>
              <SelectItem value="file">By File</SelectItem>
            </SelectContent>
          </Select>
          <Badge
            variant="outline"
            className="text-[10px] px-2 py-0.5 rounded-full bg-transparent text-white border-white/30"
          >
            Health: {summary.health_score}/100
          </Badge>
        </div>
      </div>

      {summary.main_concerns.length > 0 && (
        <p className="flex-none text-xs text-muted-foreground px-3">
          {summary.main_concerns[0]}
        </p>
      )}

      {/* Issues list */}
      <div className="flex-1 min-h-0 overflow-y-auto divide-y divide-border/50">
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
      </div>

      {/* Show all / Show less button */}
      {showExpandButton && (
        <Button
          variant="ghost"
          size="sm"
          className="flex-none w-full text-muted-foreground hover:text-foreground"
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
    </div>
  )
}

interface InsightCardProps {
  insight: SemanticAIInsight
  onDismiss: () => void
  isLoading: boolean
}

function InsightCard({ insight, onDismiss, isLoading }: InsightCardProps) {
  const [isOpen, setIsOpen] = useState(true)
  const config = priorityConfig[insight.priority] || priorityConfig.medium
  const catConfig = categoryConfig.insight
  const PriorityIcon = config.icon
  const CategoryIcon = catConfig.icon

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button className="w-full p-3 hover:bg-muted/30 transition-colors text-left group">
          <div className="flex items-start gap-3">
            <div className={cn('p-1.5 rounded-md shrink-0', config.bg)}>
              <PriorityIcon className={cn('h-3.5 w-3.5', config.iconColor)} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <Badge
                  variant="outline"
                  className={cn(
                    'text-[9px] uppercase tracking-wider font-bold px-1.5 py-0 rounded-full border',
                    config.bg,
                    config.border,
                    config.color
                  )}
                >
                  {config.label}
                </Badge>
                <span className={cn('flex items-center gap-1 text-[10px]', catConfig.color)}>
                  <CategoryIcon className={cn('h-3 w-3', catConfig.iconColor)} />
                  {catConfig.label}
                </span>
              </div>
              <h4 className="text-xs font-medium text-foreground line-clamp-1 group-hover:text-primary transition-colors">
                {insight.title}
              </h4>
              {insight.affected_files.length > 0 && (
                <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-mono mt-1">
                  <FileCode className="h-2.5 w-2.5" />
                  <span className="truncate">{insight.affected_files[0].split('/').pop()}</span>
                </div>
              )}
            </div>
            {isOpen ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
            )}
          </div>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-3 pb-3 space-y-2">
          <p className="text-xs text-muted-foreground">{insight.description}</p>
          {insight.evidence && (
            <div className="space-y-1">
              <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                Evidence
              </span>
              <pre className="text-[10px] bg-muted/50 p-2 rounded-md overflow-x-auto font-mono">
                {insight.evidence}
              </pre>
            </div>
          )}
          {insight.suggested_action && (
            <div className="space-y-1">
              <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                Suggested Action
              </span>
              <p className="text-xs text-muted-foreground bg-emerald-500/5 p-2 rounded-md border border-emerald-500/10">
                {insight.suggested_action}
              </p>
            </div>
          )}
          <div className="flex justify-end">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-xs text-muted-foreground hover:text-destructive"
              onClick={(e) => { e.stopPropagation(); onDismiss(); }}
              disabled={isLoading}
            >
              <X className="h-3 w-3 mr-1" />
              Dismiss
            </Button>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

interface DeadCodeCardProps {
  finding: DeadCodeFinding
  onDismiss: () => void
  isLoading: boolean
}



function DeadCodeCard({ finding, onDismiss, isLoading }: DeadCodeCardProps) {
  const [isOpen, setIsOpen] = useState(true)
  const impactScore = finding.impact_score ?? 0
  const catConfig = categoryConfig.dead_code
  const CategoryIcon = catConfig.icon

  // Map impact score to priority config
  const priorityLevel = impactScore >= 70 ? 'high' : impactScore >= 40 ? 'medium' : 'low'
  const config = priorityConfig[priorityLevel]
  const PriorityIcon = config.icon

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button className="w-full p-3 hover:bg-muted/30 transition-colors text-left group">
          <div className="flex items-start gap-3">
            <div className={cn('p-1.5 rounded-md shrink-0', config.bg)}>
              <PriorityIcon className={cn('h-3.5 w-3.5', config.iconColor)} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <Badge
                  variant="outline"
                  className={cn(
                    'text-[9px] uppercase tracking-wider font-bold px-1.5 py-0 rounded-full border',
                    config.bg,
                    config.border,
                    config.color
                  )}
                >
                  {config.label}
                </Badge>
                <span className={cn('flex items-center gap-1 text-[10px]', catConfig.color)}>
                  <CategoryIcon className={cn('h-3 w-3', catConfig.iconColor)} />
                  {catConfig.label}
                </span>
                {finding.confidence === 1.0 && (
                  <Badge variant="outline" className="text-[9px] px-1.5 py-0 rounded-full bg-emerald-500/10 text-emerald-500 border-emerald-500/20">
                    proven
                  </Badge>
                )}
              </div>
              <h4 className="text-xs font-medium text-foreground line-clamp-1 group-hover:text-primary transition-colors">
                {finding.function_name}
              </h4>
              <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-mono mt-1">
                <FileCode className="h-2.5 w-2.5" />
                <span className="truncate">{finding.file_path.split('/').pop()}</span>
                <span className="text-muted-foreground/60">:{finding.line_start}</span>
              </div>
            </div>
            {isOpen ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
            )}
          </div>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-3 pb-3 space-y-2">
          <p className="text-xs text-muted-foreground">{finding.evidence}</p>
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <span>Lines {finding.line_start}-{finding.line_end}</span>
            <span>•</span>
            <span>{finding.line_count} lines</span>
            <span>•</span>
            <span>Impact: {Math.round(impactScore)}</span>
          </div>
          {finding.suggested_action && (
            <div className="space-y-1">
              <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                Suggested Action
              </span>
              <p className="text-xs text-muted-foreground bg-emerald-500/5 p-2 rounded-md border border-emerald-500/10">
                {finding.suggested_action}
              </p>
            </div>
          )}
          <div className="flex justify-end">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-xs text-muted-foreground hover:text-destructive"
              onClick={(e) => { e.stopPropagation(); onDismiss(); }}
              disabled={isLoading}
            >
              <X className="h-3 w-3 mr-1" />
              Dismiss
            </Button>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

interface HotSpotCardProps {
  finding: HotSpotFinding
}

function HotSpotCard({ finding }: HotSpotCardProps) {
  const [isOpen, setIsOpen] = useState(true)
  const riskScore = finding.risk_score ?? 0
  const catConfig = categoryConfig.hot_spot
  const CategoryIcon = catConfig.icon

  // Map risk score to priority config
  const priorityLevel = riskScore >= 70 ? 'high' : riskScore >= 40 ? 'medium' : 'low'
  const config = priorityConfig[priorityLevel]
  const PriorityIcon = config.icon

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button className="w-full p-3 hover:bg-muted/30 transition-colors text-left group">
          <div className="flex items-start gap-3">
            <div className={cn('p-1.5 rounded-md shrink-0', config.bg)}>
              <PriorityIcon className={cn('h-3.5 w-3.5', config.iconColor)} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <Badge
                  variant="outline"
                  className={cn(
                    'text-[9px] uppercase tracking-wider font-bold px-1.5 py-0 rounded-full border',
                    config.bg,
                    config.border,
                    config.color
                  )}
                >
                  {config.label}
                </Badge>
                <span className={cn('flex items-center gap-1 text-[10px]', catConfig.color)}>
                  <CategoryIcon className={cn('h-3 w-3', catConfig.iconColor)} />
                  {catConfig.label}
                </span>
                <Badge variant="outline" className="text-[9px] px-1.5 py-0 rounded-full bg-transparent text-white border-white/30">
                  {finding.changes_90d} changes
                </Badge>
              </div>
              <h4 className="text-xs font-medium text-foreground line-clamp-1 group-hover:text-primary transition-colors">
                {finding.file_path.split('/').pop()}
              </h4>
              <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-mono mt-1">
                <FileCode className="h-2.5 w-2.5" />
                <span className="truncate">{finding.file_path}</span>
              </div>
            </div>
            {isOpen ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
            )}
          </div>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-3 pb-3 space-y-2">
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <span>Risk: {Math.round(riskScore)}</span>
            {finding.coverage_rate !== null && (
              <>
                <span>•</span>
                <span>{Math.round(finding.coverage_rate * 100)}% coverage</span>
              </>
            )}
          </div>
          {finding.risk_factors.length > 0 && (
            <div className="space-y-1">
              <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                Risk Factors
              </span>
              <ul className="text-xs text-muted-foreground space-y-0.5">
                {finding.risk_factors.map((factor, idx) => (
                  <li key={idx} className="flex items-center gap-1">
                    <span className="text-muted-foreground">•</span> {factor}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {finding.suggested_action && (
            <div className="space-y-1">
              <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                Suggested Action
              </span>
              <p className="text-xs text-muted-foreground bg-emerald-500/5 p-2 rounded-md border border-emerald-500/10">
                {finding.suggested_action}
              </p>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
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
