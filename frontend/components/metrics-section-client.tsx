'use client'

import { useEffect } from 'react'
import { AnalysisMetrics } from '@/components/analysis-metrics'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import { useAnalysisDataStore } from '@/lib/stores/analysis-data-store'
import { Loader2 } from 'lucide-react'

interface MetricsSectionClientProps {
  repositoryId: string
  token: string
}

export function MetricsSectionClient({ repositoryId, token }: MetricsSectionClientProps) {
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
        <p className="text-sm">Select a commit to view analysis metrics</p>
      </div>
    )
  }

  // Pass metrics to AnalysisMetrics (handles null case internally)
  const metrics = hasMatchingData ? analysisData?.metrics || null : null
  return <AnalysisMetrics metrics={metrics as Parameters<typeof AnalysisMetrics>[0]['metrics']} />
}
