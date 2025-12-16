'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Brain,
  AlertCircle,
  AlertTriangle,
  Info,
  Shield,
  Database,
  Code,
  Sparkles,
  Loader2,
  ChevronDown,
  ChevronRight,
  FileCode,
  CheckCircle,
  XCircle,
  HelpCircle,
  Minimize2,
  Maximize2,
  Bot,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  type AIScanIssue,
  type AIScanCacheResponse,
  triggerAIScan,
  getAIScanResults,
  AIScanApiError,
} from '@/lib/ai-scan-api'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import { useAnalysisStatusWithStore } from '@/lib/hooks/use-analysis-status'

// =============================================================================
// Types
// =============================================================================

interface AIInsightsPanelProps {
  repositoryId: string
  token: string
}

// =============================================================================
// Constants
// =============================================================================

const SEVERITY_CONFIG = {
  critical: {
    icon: AlertCircle,
    color: 'text-white',
    iconColor: 'text-red-500',
    bg: 'bg-transparent',
    border: 'border-white/30',
    label: 'Critical',
  },
  high: {
    icon: AlertTriangle,
    color: 'text-white',
    iconColor: 'text-orange-500',
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

const DIMENSION_CONFIG = {
  security: {
    icon: Shield,
    label: 'Security',
    color: 'text-white',
    iconColor: 'text-red-400',
  },
  db_consistency: {
    icon: Database,
    label: 'Database',
    color: 'text-white',
    iconColor: 'text-purple-400',
  },
  api_correctness: {
    icon: Code,
    label: 'API',
    color: 'text-white',
    iconColor: 'text-blue-400',
  },
  code_health: {
    icon: Sparkles,
    label: 'Code Health',
    color: 'text-white',
    iconColor: 'text-green-400',
  },
  other: {
    icon: Info,
    label: 'Other',
    color: 'text-white',
    iconColor: 'text-gray-400',
  },
}

const INVESTIGATION_STATUS_CONFIG = {
  confirmed: {
    icon: CheckCircle,
    color: 'text-red-500',
    label: 'Confirmed',
  },
  likely_real: {
    icon: AlertTriangle,
    color: 'text-orange-500',
    label: 'Likely Real',
  },
  uncertain: {
    icon: HelpCircle,
    color: 'text-amber-500',
    label: 'Uncertain',
  },
  invalid: {
    icon: XCircle,
    color: 'text-green-500',
    label: 'Invalid',
  },
}



// =============================================================================
// Helper Functions
// =============================================================================

function getModelInfo(modelId: string) {
  const id = modelId.toLowerCase()

  // Google / Gemini Models
  if (id.includes('gemini') || id.includes('google')) {
    let name = 'Gemini'
    if (id.includes('gemini-3') && id.includes('pro')) name = 'Gemini 3 Pro'
    else if (id.includes('2.5') && id.includes('flash')) name = 'Gemini 2.5 Flash'
    else if (id.includes('2.5') && id.includes('pro')) name = 'Gemini 2.5 Pro'
    else if (id.includes('2.0') && id.includes('flash')) name = 'Gemini 2.0 Flash'
    else if (id.includes('flash')) name = 'Gemini Flash'
    else if (id.includes('pro')) name = 'Gemini Pro'
    else if (id.includes('ultra')) name = 'Gemini Ultra'

    return {
      name,
      className: 'text-white',
      iconClassName: 'text-blue-400',
      icon: Sparkles
    }
  }

  // Anthropic / Claude Models
  if (id.includes('claude') || id.includes('anthropic')) {
    let name = 'Claude'
    if (id.includes('opus')) name = 'Claude Opus'
    else if (id.includes('sonnet-4-5')) name = 'Claude Sonnet 4.5'
    else if (id.includes('haiku')) name = 'Claude Haiku'

    return {
      name,
      className: 'text-white',
      iconClassName: 'text-orange-400',
      icon: Bot
    }
  }

  // OpenAI Models
  if (id.includes('gpt') || id.includes('openai') || id.includes('o1') || id.includes('o3')) {
    let name = 'GPT'
    if (id.includes('gpt-4o')) name = 'GPT-4o'
    else if (id.includes('gpt-5.2')) name = 'GPT-5.2'
    else if (id.includes('gpt-5.1')) name = 'GPT-5.1'
    else if (id.includes('o1')) name = 'o1'
    else if (id.includes('o3')) name = 'o3'

    return {
      name,
      className: 'text-white',
      iconClassName: 'text-green-400',
      icon: Bot
    }
  }

  // Generic Fallback
  return {
    name: 'AI Model',
    className: 'text-white',
    iconClassName: 'text-purple-400',
    icon: Bot
  }
}

// =============================================================================
// Issue Card Component
// =============================================================================

function IssueCard({
  issue,
  isOpen,
  onToggle
}: {
  issue: AIScanIssue
  isOpen: boolean
  onToggle: (open: boolean) => void
}) {
  const severityConfig = SEVERITY_CONFIG[issue.severity]
  const dimensionConfig = DIMENSION_CONFIG[issue.dimension]
  const SeverityIcon = severityConfig.icon
  const DimensionIcon = dimensionConfig.icon

  return (
    <Collapsible open={isOpen} onOpenChange={onToggle}>
      <CollapsibleTrigger asChild>
        <button className="w-full p-3 hover:bg-muted/30 transition-colors text-left group">
          <div className="flex items-start gap-3">
            <div className={cn('p-1.5 rounded-md shrink-0', severityConfig.bg)}>
              <SeverityIcon className={cn('h-3.5 w-3.5', severityConfig.iconColor)} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <Badge
                  variant="outline"
                  className={cn(
                    'text-[9px] uppercase tracking-wider font-bold px-1.5 py-0 rounded-full border',
                    severityConfig.bg,
                    severityConfig.border,
                    severityConfig.color
                  )}
                >
                  {severityConfig.label}
                </Badge>
                <span className={cn('flex items-center gap-1 text-[10px]', dimensionConfig.color)}>
                  <DimensionIcon className={cn('h-3 w-3', dimensionConfig.iconColor)} />
                  {dimensionConfig.label}
                </span>
                {issue.found_by_models && issue.found_by_models.map((modelId) => {
                  const modelInfo = getModelInfo(modelId)
                  const ModelIcon = modelInfo.icon
                  return (
                    <span
                      key={modelId}
                      className={cn(
                        'text-[9px] px-1.5 py-0.5 rounded-full flex items-center gap-1',
                        modelInfo.className
                      )}
                    >
                      <ModelIcon className={cn('h-3 w-3', modelInfo.iconClassName)} />
                      {modelInfo.name}
                    </span>
                  )
                })}
                {issue.investigation_status && (
                  <Badge
                    variant="outline"
                    className={cn(
                      'text-[9px] px-1.5 py-0 rounded-full',
                      INVESTIGATION_STATUS_CONFIG[issue.investigation_status].color
                    )}
                  >
                    {INVESTIGATION_STATUS_CONFIG[issue.investigation_status].label}
                  </Badge>
                )}
              </div>
              <h4 className="text-xs font-medium text-foreground line-clamp-1 group-hover:text-primary transition-colors">
                {issue.title}
              </h4>
              {issue.files.length > 0 && (
                <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-mono mt-1">
                  <FileCode className="h-2.5 w-2.5" />
                  <span className="truncate">{issue.files[0].path}</span>
                  {issue.files[0].line_start && (
                    <span className="text-muted-foreground/60">:{issue.files[0].line_start}</span>
                  )}
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
          <p className="text-xs text-muted-foreground">{issue.summary}</p>
          {issue.evidence_snippets.length > 0 && (
            <div className="space-y-1">
              <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                Evidence
              </span>
              {issue.evidence_snippets.slice(0, 2).map((snippet, i) => (
                <pre
                  key={i}
                  className="text-[10px] bg-muted/50 p-2 rounded-md overflow-x-auto font-mono"
                >
                  {snippet.slice(0, 200)}
                  {snippet.length > 200 && '...'}
                </pre>
              ))}
            </div>
          )}
          {issue.suggested_fix && (
            <div className="space-y-1">
              <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                Suggested Fix
              </span>
              <p className="text-xs text-muted-foreground bg-emerald-500/5 p-2 rounded-md border border-emerald-500/10">
                {issue.suggested_fix}
              </p>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}


// =============================================================================
// Issues By Severity Component
// =============================================================================

function IssuesBySeverity({
  issues,
  expandedIds,
  onToggle
}: {
  issues: AIScanIssue[]
  expandedIds: Set<string>
  onToggle: (id: string, isOpen: boolean) => void
}) {
  const criticalIssues = issues.filter((i) => i.severity === 'critical')
  const highIssues = issues.filter((i) => i.severity === 'high')
  const mediumIssues = issues.filter((i) => i.severity === 'medium')
  const lowIssues = issues.filter((i) => i.severity === 'low')

  const severityGroups = [
    { severity: 'critical' as const, issues: criticalIssues },
    { severity: 'high' as const, issues: highIssues },
    { severity: 'medium' as const, issues: mediumIssues },
    { severity: 'low' as const, issues: lowIssues },
  ].filter((g) => g.issues.length > 0)

  if (issues.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
        <CheckCircle className="h-8 w-8 mb-2 text-emerald-500" />
        <p className="text-sm font-medium">No issues found</p>
        <p className="text-xs">AI scan completed successfully</p>
      </div>
    )
  }

  return (
    <div className="divide-y divide-border/50">
      {severityGroups.map(({ severity, issues: groupIssues }) => (
        <div key={severity}>
          {groupIssues.map((issue) => (
            <IssueCard
              key={issue.id}
              issue={issue}
              isOpen={expandedIds.has(issue.id)}
              onToggle={(open) => onToggle(issue.id, open)}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

// =============================================================================
// Progress Display Component (Simplified - Requirements 3.2)
// =============================================================================

/**
 * Simplified progress display that points users to the unified progress popup.
 * The detailed progress is now shown in the AnalysisProgressOverlay component.
 * 
 * **Feature: ai-scan-progress-fix**
 * **Validates: Requirements 3.2**
 */
function ScanInProgress() {
  return (
    <div className="flex flex-col items-center justify-center py-6 px-4">
      <div className="relative mb-4">
        <Brain className="h-10 w-10 text-primary animate-pulse" />
        <div className="absolute -bottom-1 -right-1 bg-background rounded-full p-0.5">
          <Loader2 className="h-4 w-4 text-primary animate-spin" />
        </div>
      </div>
      <p className="text-sm font-medium mb-1">AI scan in progress...</p>
      <p className="text-xs text-muted-foreground text-center">
        Check the progress popup in the bottom-right corner for details
      </p>
    </div>
  )
}

// =============================================================================
// Main Component
// =============================================================================

/**
 * AI Insights Panel - displays AI scan results or allows triggering a scan.
 * 
 * Now uses the unified useAnalysisStatusWithStore hook for status tracking,
 * which syncs AI scan progress to the global progress popup.
 * 
 * **Feature: ai-scan-progress-fix**
 * **Validates: Requirements 3.2, 3.3, 6.1, 6.2, 6.3, 6.4**
 */
export function AIInsightsPanel({ repositoryId, token }: AIInsightsPanelProps) {
  const { selectedAnalysisId } = useCommitSelectionStore()

  // Use unified status hook for AI scan status (Requirements 3.3)
  // This automatically syncs progress to the global progress store
  const { data: fullStatus, refetch: refetchStatus } = useAnalysisStatusWithStore({
    analysisId: selectedAnalysisId,
    repositoryId,
    token,
  })

  // Local state for scan results and expansion
  const [scanData, setScanData] = useState<AIScanCacheResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  // Refs
  const isMountedRef = useRef(true)

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  // Track previous AI scan status to detect completion transitions
  const prevAiScanStatusRef = useRef<string | null>(null)

  // Unified fetch effect - handles both initial load and completion transitions
  // This replaces two separate useEffects that were causing duplicate API calls
  useEffect(() => {
    if (!selectedAnalysisId || !token) {
      setScanData(null)
      setLoading(false)
      return
    }

    const currentStatus = fullStatus?.ai_scan_status
    const prevStatus = prevAiScanStatusRef.current

    // Determine if we should fetch:
    // 1. Initial load (no previous status)
    // 2. Status just changed to 'completed' (transition detection)
    const isInitialLoad = prevStatus === null
    const justCompleted = prevStatus !== 'completed' && currentStatus === 'completed'
    const shouldFetch = isInitialLoad || justCompleted

    // Update ref for next render
    prevAiScanStatusRef.current = currentStatus ?? null

    if (!shouldFetch) {
      return
    }

    const fetchResults = async () => {
      // Only show loading on initial load, not on completion refresh
      if (isInitialLoad) {
        setLoading(true)
      }
      setError(null)

      try {
        const results = await getAIScanResults(selectedAnalysisId, token)
        if (!isMountedRef.current) return

        setScanData(results)
      } catch (err) {
        if (!isMountedRef.current) return
        if (err instanceof AIScanApiError && err.isNotFound()) {
          setScanData(null)
        } else {
          setError(err instanceof Error ? err.message : 'Failed to load AI scan results')
        }
      } finally {
        if (isMountedRef.current) {
          setLoading(false)
        }
      }
    }

    fetchResults()
  }, [selectedAnalysisId, token, fullStatus?.ai_scan_status])

  // NOTE: The previous implementation had TWO useEffects that both called getAIScanResults:
  // 1. On [selectedAnalysisId, token] change
  // 2. On [fullStatus?.ai_scan_status] change to 'completed'
  // This caused 2-4x duplicate API calls. Now unified into a single effect with transition detection.

  // Legacy comment preserved for reference - this effect was REMOVED:
  // useEffect(() => {
  //   if (fullStatus?.ai_scan_status === 'completed' && selectedAnalysisId && token) {
  //     getAIScanResults(selectedAnalysisId, token)  // DUPLICATE FETCH - REMOVED
  //   }
  // }, [fullStatus?.ai_scan_status, selectedAnalysisId, token])

  // Trigger AI scan
  const handleRunScan = useCallback(async () => {
    if (!selectedAnalysisId || !token) return

    setError(null)

    try {
      await triggerAIScan(selectedAnalysisId, token)
      // Refetch status to pick up the new pending/running state
      refetchStatus()
    } catch (err) {
      if (err instanceof AIScanApiError && err.isConflict()) {
        // Scan already in progress - just refetch status
        refetchStatus()
      } else {
        setError(err instanceof Error ? err.message : 'Failed to start AI scan')
      }
    }
  }, [selectedAnalysisId, token, refetchStatus])

  // Toggle individual issue
  const handleToggle = useCallback((id: string, isOpen: boolean) => {
    setExpandedIds(prev => {
      const next = new Set(prev)
      if (isOpen) {
        next.add(id)
      } else {
        next.delete(id)
      }
      return next
    })
  }, [])

  // Toggle all issues
  const handleToggleAll = useCallback(() => {
    if (!scanData?.issues) return

    setExpandedIds(prev => {
      // If all are expanded, collapse all. Otherwise, expand all.
      const allIds = scanData.issues.map(i => i.id)
      if (prev.size === allIds.length) {
        return new Set()
      } else {
        return new Set(allIds)
      }
    })
  }, [scanData])

  // Get AI scan status from unified status hook
  const aiScanStatus = fullStatus?.ai_scan_status

  // Render states
  if (!selectedAnalysisId) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
        <Brain className="h-8 w-8 mb-2 opacity-50" />
        <p className="text-sm">Select a commit to view AI insights</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
        <AlertCircle className="h-8 w-8 mb-2 text-destructive" />
        <p className="text-sm text-destructive">{error}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={handleRunScan}>
          Retry
        </Button>
      </div>
    )
  }

  // Scan in progress - show simplified message pointing to progress popup (Requirements 3.2)
  // Progress details are now shown in the unified AnalysisProgressOverlay
  if (aiScanStatus === 'pending' || aiScanStatus === 'running') {
    return <ScanInProgress />
  }

  // No scan yet - show informational message
  // AI scan starts automatically with the main "Run Analysis" button
  if (!scanData || !scanData.is_cached || aiScanStatus === 'none' || aiScanStatus === 'skipped') {
    return (
      <div className="flex flex-col items-center justify-center py-8">
        <Brain className="h-10 w-10 mb-3 text-primary/60" />
        <p className="text-sm font-medium mb-1">AI-Powered Analysis</p>
        <p className="text-xs text-muted-foreground text-center max-w-xs">
          AI scan runs automatically when you start the main analysis. It detects security issues, API mismatches, and code health problems.
        </p>
      </div>
    )
  }

  // Scan failed - show error and retry button
  if (aiScanStatus === 'failed' || scanData.status === 'failed') {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
        <XCircle className="h-8 w-8 mb-2 text-destructive" />
        <p className="text-sm text-destructive">AI scan failed</p>
        {fullStatus?.ai_scan_error && (
          <p className="text-xs text-muted-foreground mt-1 text-center max-w-xs">
            {fullStatus.ai_scan_error}
          </p>
        )}
        <Button variant="outline" size="sm" className="mt-3" onClick={handleRunScan}>
          Retry Scan
        </Button>
      </div>
    )
  }

  // Show results (Requirement 6.2)
  return (
    <div className="flex flex-col h-full space-y-3">
      {/* Header with stats */}
      <div className="flex-none flex items-center justify-between px-3 pt-2">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-primary" />
          <span className="text-xs font-medium">
            {scanData.issues.length} issue{scanData.issues.length !== 1 ? 's' : ''} found
          </span>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          {scanData.total_cost_usd !== null && (
            <span>${scanData.total_cost_usd.toFixed(3)}</span>
          )}
          {scanData.computed_at && (
            <span>{new Date(scanData.computed_at).toLocaleDateString()}</span>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 ml-1"
            onClick={handleToggleAll}
            title={expandedIds.size === scanData.issues.length ? "Collapse all" : "Expand all"}
          >
            {expandedIds.size === scanData.issues.length ? (
              <Minimize2 className="h-3.5 w-3.5" />
            ) : (
              <Maximize2 className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>
      </div>

      {/* Severity summary */}
      <div className="flex-none flex gap-2 px-3 flex-wrap">
        {(['critical', 'high', 'medium', 'low'] as const).map((severity) => {
          const count = scanData.issues.filter((i) => i.severity === severity).length
          if (count === 0) return null
          const config = SEVERITY_CONFIG[severity]
          return (
            <Badge
              key={severity}
              variant="outline"
              className={cn(
                'text-[10px] px-2 py-0.5 rounded-full',
                config.bg,
                config.border,
                config.color
              )}
            >
              {count} {config.label}
            </Badge>
          )
        })}
      </div>

      {/* Issues list - Adaptive height */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <IssuesBySeverity
          issues={scanData.issues}
          expandedIds={expandedIds}
          onToggle={handleToggle}
        />
      </div>
    </div>
  )
}
