'use client'

import { useEffect } from 'react'
import { VCIScoreCard } from '@/components/vci-score-card'
import { VCITrendChart } from '@/components/vci-trend-chart'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import { useAnalysisDataStore } from '@/lib/stores/analysis-data-store'
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

export function VCISectionClient({
  repositoryId,
  token,
  initialHistory,
  initialTrend,
}: VCISectionClientProps) {
  const { selectedAnalysisId, selectedCommitSha } = useCommitSelectionStore()
  const { analysisData, loading, fetchAnalysis, currentAnalysisId } = useAnalysisDataStore()

  // Fetch analysis data when selectedAnalysisId changes or when cache is invalidated
  useEffect(() => {
    if (selectedAnalysisId && token && !analysisData && currentAnalysisId === selectedAnalysisId) {
      fetchAnalysis(selectedAnalysisId, token)
    } else if (selectedAnalysisId && token && currentAnalysisId !== selectedAnalysisId) {
      fetchAnalysis(selectedAnalysisId, token)
    }
  }, [selectedAnalysisId, token, fetchAnalysis, analysisData, currentAnalysisId])

  // Check if data matches current selection
  const hasMatchingData = analysisData && currentAnalysisId === selectedAnalysisId

  // Show loading state
  if (loading && currentAnalysisId === selectedAnalysisId) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // Show empty state if no commit selected or no analysis
  if (!selectedCommitSha || !selectedAnalysisId) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p className="text-sm">Select a commit to view VCI score</p>
      </div>
    )
  }

  // Show empty state if commit has no analysis or data doesn't match
  if (!hasMatchingData) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p className="text-sm mb-2">No analysis for this commit</p>
        <p className="text-xs">Run an analysis to see the VCI score</p>
      </div>
    )
  }

  const score = analysisData.vci_score
  const grade = analysisData.grade

  return (
    <div className="space-y-4">
      <VCIScoreCard
        score={score}
        grade={grade}
        trend={initialTrend}
      />
      {initialHistory.length > 0 && (
        <VCITrendChart data={initialHistory} />
      )}
    </div>
  )
}
