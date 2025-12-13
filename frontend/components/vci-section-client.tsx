'use client'

import { memo, useMemo } from 'react'
import { VCIScoreCardCompact } from '@/components/vci-score-card-compact'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import { useAnalysisStatus } from '@/lib/hooks/use-analysis-status'
import { Loader2 } from 'lucide-react'

interface VCIHistoryPoint {
  date: string
  vci_score: number
  grade: string
  commit_sha: string
}

interface VCISectionClientProps {
  repositoryId: string
  token: string
  initialHistory: VCIHistoryPoint[]
  initialTrend: 'improving' | 'stable' | 'declining'
}

/**
 * VCI Section Client Component
 *
 * Refactored to use the shared useAnalysisStatus hook instead of independent polling.
 * This leverages React Query's caching and smart polling intervals.
 *
 * **Feature: progress-tracking-refactor**
 * **Validates: Requirements 4.1**
 *
 * **Optimization: Memoized to prevent re-renders from parent**
 * Uses useMemo for derived values to break object reference chains
 */
function VCISectionClientComponent({
  repositoryId,
  token,
  initialHistory,
  initialTrend,
}: VCISectionClientProps) {
  const { selectedAnalysisId, selectedCommitSha } = useCommitSelectionStore()

  // Use the shared useAnalysisStatus hook for smart polling and React Query cache
  // This replaces the manual polling logic and useAnalysisDataStore
  const {
    data: analysisStatus,
    isLoading,
  } = useAnalysisStatus({
    analysisId: selectedAnalysisId,
    repositoryId,
    token,
    enabled: !!selectedAnalysisId && !!token,
  })
  
  // Memoize derived values to prevent re-renders when object reference changes
  // but actual values remain the same
  const derivedData = useMemo(() => {
    if (!analysisStatus) return null
    
    return {
      score: analysisStatus.vci_score,
      grade: analysisStatus.grade,
      status: analysisStatus.analysis_status,
      analysisId: analysisStatus.analysis_id,
      stage: analysisStatus.overall_stage,
    }
  }, [analysisStatus])

  // Show loading state
  if (isLoading) {
    return (
      <div className="glass-panel border border-border/50 rounded-xl p-3 flex items-center justify-center h-[120px]">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // Show empty state if no commit selected or no analysis
  if (!selectedCommitSha || !selectedAnalysisId) {
    return (
      <div className="glass-panel border border-border/50 rounded-xl p-3 flex items-center justify-center h-[120px]">
        <p className="text-xs text-muted-foreground">Select a commit to view VCI</p>
      </div>
    )
  }

  // Show empty state if no data available
  if (!analysisStatus) {
    return (
      <div className="glass-panel border border-border/50 rounded-xl p-3 flex flex-col items-center justify-center h-[120px]">
        <p className="text-xs text-muted-foreground">No analysis for this commit</p>
      </div>
    )
  }

  // While analysis is running, avoid duplicating progress UI (use bottom-right progress overlay)
  if (derivedData && derivedData.status !== 'completed') {
    return (
      <div className="glass-panel border border-border/50 rounded-xl p-3 flex items-center justify-center h-[120px]">
        <p className="text-xs text-muted-foreground">VCI will appear when analysis completes</p>
      </div>
    )
  }

  const score = derivedData?.score ?? null
  const grade = derivedData?.grade ?? null

  // If analysis completed but no VCI score, show error state
  if (derivedData && score === null) {
    return (
      <div className="glass-panel border border-border/50 rounded-xl p-3 flex flex-col items-center justify-center h-[120px]">
        <p className="text-xs text-muted-foreground">VCI score not available</p>
        <p className="text-[10px] text-muted-foreground/60 mt-1">Analysis may have failed</p>
      </div>
    )
  }

  return (
    <VCIScoreCardCompact
      score={score}
      grade={grade}
      trend={initialTrend}
      historyData={initialHistory}
    />
  )
}

// Memoize component with custom comparison to prevent unnecessary re-renders
// Only re-render if actual values change, not object references
export const VCISectionClient = memo(VCISectionClientComponent, (prevProps, nextProps) => {
  return (
    prevProps.repositoryId === nextProps.repositoryId &&
    prevProps.token === nextProps.token &&
    prevProps.initialHistory === nextProps.initialHistory &&
    prevProps.initialTrend === nextProps.initialTrend
  )
})

VCISectionClient.displayName = 'VCISectionClient'
