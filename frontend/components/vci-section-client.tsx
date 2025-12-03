'use client'

import { useEffect } from 'react'
import { VCIScoreCardCompact } from '@/components/vci-score-card-compact'
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

  // Fetch analysis data when selectedAnalysisId changes
  useEffect(() => {
    console.log('[VCI] Effect triggered:', { selectedAnalysisId, currentAnalysisId, hasData: !!analysisData })
    if (selectedAnalysisId && token && currentAnalysisId !== selectedAnalysisId) {
      console.log('[VCI] Fetching analysis:', selectedAnalysisId)
      fetchAnalysis(selectedAnalysisId, token)
    }
  }, [selectedAnalysisId, token, fetchAnalysis, currentAnalysisId])

  // Poll for updates when analysis is not completed
  useEffect(() => {
    if (!selectedAnalysisId || !token) return
    if (analysisData?.status === 'completed') return
    
    const interval = setInterval(() => {
      console.log('[VCI] Polling for analysis update')
      fetchAnalysis(selectedAnalysisId, token)
    }, 3000)
    
    return () => clearInterval(interval)
  }, [selectedAnalysisId, token, fetchAnalysis, analysisData?.status])

  // Check if data matches current selection
  const hasMatchingData = analysisData && currentAnalysisId === selectedAnalysisId

  // Show loading state
  if (loading && currentAnalysisId === selectedAnalysisId) {
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

  // Show empty state if commit has no analysis or data doesn't match
  if (!hasMatchingData) {
    return (
      <div className="glass-panel border border-border/50 rounded-xl p-3 flex flex-col items-center justify-center h-[120px]">
        <p className="text-xs text-muted-foreground">No analysis for this commit</p>
      </div>
    )
  }

  // Show loading state if analysis is still running
  if (analysisData.status !== 'completed') {
    return (
      <div className="glass-panel border border-border/50 rounded-xl p-3 flex flex-col items-center justify-center h-[120px]">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground mb-2" />
        <p className="text-xs text-muted-foreground">Analysis in progress...</p>
      </div>
    )
  }

  const score = analysisData.vci_score
  const grade = analysisData.grade

  console.log('[VCI] Rendering with data:', { 
    score, 
    grade, 
    status: analysisData.status,
    analysisId: currentAnalysisId,
    metrics: analysisData.metrics ? Object.keys(analysisData.metrics) : null,
  })

  // If analysis completed but no VCI score, show error state
  if (score === null) {
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
