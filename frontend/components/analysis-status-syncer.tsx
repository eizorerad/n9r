'use client'

import { useEffect } from 'react'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import { useAnalysisDataStore } from '@/lib/stores/analysis-data-store'
import { useStatusBarStore } from '@/lib/stores/status-bar-store'

interface AnalysisStatusSyncerProps {
    token: string
}

export function AnalysisStatusSyncer({ token }: AnalysisStatusSyncerProps) {
    const { selectedAnalysisId, selectedCommitSha } = useCommitSelectionStore()
    const { analysisData, fetchAnalysis, currentAnalysisId } = useAnalysisDataStore()
    const { setDiagnostics } = useStatusBarStore()

    // Fetch analysis data when selectedAnalysisId changes
    useEffect(() => {
        if (selectedAnalysisId && token && currentAnalysisId !== selectedAnalysisId) {
            fetchAnalysis(selectedAnalysisId, token)
        }
    }, [selectedAnalysisId, token, fetchAnalysis, currentAnalysisId])

    // Sync data to status bar
    useEffect(() => {
        // If no commit selected or no analysis, reset diagnostics
        if (!selectedCommitSha || !selectedAnalysisId) {
            setDiagnostics(0, 0)
            return
        }

        // If we have matching data
        if (analysisData && currentAnalysisId === selectedAnalysisId) {
            // Logic for counting errors vs warnings
            // Assuming 'high' severity = Error, others = Warning for now
            // Or checking specific types. 
            // issues: Issue[]

            let errorCount = 0
            let warningCount = 0

            if (analysisData.issues) {
                analysisData.issues.forEach(issue => {
                    if (issue.severity === 'high') {
                        errorCount++
                    } else {
                        warningCount++
                    }
                })
            }

            setDiagnostics(errorCount, warningCount)
        }
    }, [selectedCommitSha, selectedAnalysisId, analysisData, currentAnalysisId, setDiagnostics])

    return null // This is a logic-only component
}
