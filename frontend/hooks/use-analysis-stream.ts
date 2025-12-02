import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { runAnalysis, getApiUrl, getAccessToken, revalidateRepositoryPage } from '@/app/actions/analysis'
import { useAnalysisProgressStore, getAnalysisTaskId } from '@/lib/stores/analysis-progress-store'

export type AnalysisStatus = 'idle' | 'pending' | 'running' | 'completed' | 'failed'

interface ProgressUpdate {
    analysis_id: string
    stage: string
    progress: number
    message: string | null
    status: string
    vci_score?: number
}

// Stage labels for user-friendly display
export const STAGE_LABELS: Record<string, string> = {
    queued: 'Waiting for worker...',
    initializing: 'Initializing...',
    cloning: 'Cloning repository...',
    counting_lines: 'Counting lines of code...',
    analyzing_complexity: 'Analyzing complexity...',
    static_analysis: 'Running static analysis...',
    calculating_vci: 'Calculating VCI score...',
    saving_results: 'Saving results...',
    completed: 'Analysis complete!',
    failed: 'Analysis failed',
}

interface UseAnalysisStreamResult {
    status: AnalysisStatus
    progress: number
    stage: string
    message: string
    vciScore: number | null
    error: string | null
    startAnalysis: (repositoryId: string) => Promise<void>
    reset: () => void
}

export function useAnalysisStream(repositoryId: string): UseAnalysisStreamResult {
    const router = useRouter()
    const [analysisId, setAnalysisId] = useState<string | null>(null)
    const [status, setStatus] = useState<AnalysisStatus>('idle')
    const [progress, setProgress] = useState(0)
    const [stage, setStage] = useState<string>('')
    const [message, setMessage] = useState<string>('')
    const [vciScore, setVciScore] = useState<number | null>(null)
    const [error, setError] = useState<string | null>(null)

    const eventSourceRef = useRef<EventSource | null>(null)
    const isMountedRef = useRef(true)
    
    // Global progress store
    const { addTask, updateTask, removeTask } = useAnalysisProgressStore()
    const taskId = getAnalysisTaskId(repositoryId)

    // Track mount state
    useEffect(() => {
        isMountedRef.current = true
        return () => {
            isMountedRef.current = false
        }
    }, [])

    // Cleanup SSE connection on unmount
    useEffect(() => {
        return () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close()
            }
        }
    }, [])

    const reset = useCallback(() => {
        setStatus('idle')
        setProgress(0)
        setStage('')
        setMessage('')
        setVciScore(null)
        setError(null)
        setAnalysisId(null)
        if (eventSourceRef.current) {
            eventSourceRef.current.close()
            eventSourceRef.current = null
        }
    }, [])

    const startAnalysis = useCallback(async (repoId: string) => {
        setError(null)
        setStatus('pending')
        setProgress(0)
        setStage('queued')
        setMessage('Starting analysis...')
        setVciScore(null)

        // Add to global progress store
        addTask({
            id: taskId,
            type: 'analysis',
            repositoryId: repoId,
            status: 'pending',
            progress: 0,
            stage: 'queued',
            message: 'Starting analysis...',
        })

        try {
            const result = await runAnalysis(repoId)

            if (result.success && result.analysisId) {
                setAnalysisId(result.analysisId)
                setStatus('running')
                updateTask(taskId, { status: 'running' })
            } else {
                setStatus('failed')
                setError(result.error || 'Failed to start analysis')
                setProgress(0)
                updateTask(taskId, { status: 'failed', message: result.error || 'Failed to start analysis' })
            }
        } catch (err) {
            setStatus('failed')
            const errorMsg = err instanceof Error ? err.message : 'Failed to start analysis'
            setError(errorMsg)
            updateTask(taskId, { status: 'failed', message: errorMsg })
        }
    }, [addTask, updateTask, taskId])

    // Connect to SSE when analysisId is set
    useEffect(() => {
        if (!analysisId || status === 'completed' || status === 'failed' || status === 'idle') {
            return
        }

        let mounted = true
        let retryCount = 0
        const maxRetries = 5
        const baseDelay = 1000

        const connectSSE = async (): Promise<void> => {
            while (mounted && retryCount < maxRetries) {
                try {
                    const [apiUrl, accessToken] = await Promise.all([
                        getApiUrl(),
                        getAccessToken(),
                    ])

                    if (!accessToken) {
                        setError('Not authenticated')
                        setStatus('failed')
                        return
                    }

                    if (eventSourceRef.current) {
                        eventSourceRef.current.close()
                    }

                    const response = await fetch(`${apiUrl}/analyses/${analysisId}/stream`, {
                        headers: {
                            'Authorization': `Bearer ${accessToken}`,
                            'Accept': 'text/event-stream',
                        },
                    })

                    if (!response.ok) {
                        throw new Error(`SSE connection failed: ${response.status}`)
                    }

                    const reader = response.body?.getReader()
                    if (!reader) throw new Error('No response body')

                    retryCount = 0
                    const decoder = new TextDecoder()
                    let buffer = ''

                    while (mounted) {
                        const { done, value } = await reader.read()

                        if (done) break

                        buffer += decoder.decode(value, { stream: true })
                        const lines = buffer.split('\n')
                        buffer = lines.pop() || ''

                        for (const line of lines) {
                            if (line.startsWith('data: ')) {
                                const data = line.slice(6)
                                try {
                                    const update: ProgressUpdate = JSON.parse(data)
                                    if (!mounted) return

                                    setProgress(update.progress)
                                    setStage(update.stage)
                                    setMessage(update.message || STAGE_LABELS[update.stage] || update.stage)
                                    
                                    // Sync with global store
                                    updateTask(taskId, {
                                        progress: update.progress,
                                        stage: update.stage,
                                        message: update.message || STAGE_LABELS[update.stage] || update.stage,
                                    })

                                    if (update.vci_score !== undefined) {
                                        setVciScore(update.vci_score)
                                    }

                                    if (update.status === 'completed') {
                                        setStatus('idle') // Reset to idle or completed? The original code reset to idle.
                                        // Actually, original code set status to 'idle' but showed 'completed' UI momentarily?
                                        // Wait, original code:
                                        // if (update.status === 'completed') {
                                        //   setStatus('idle')
                                        //   ...
                                        //   return
                                        // }
                                        // But the UI checks `status === 'completed'` to show success message.
                                        // Ah, the original code had:
                                        // if (update.status === 'completed') {
                                        //    setStatus('idle') ...
                                        // }
                                        // But the UI has:
                                        // {status === 'completed' ? ( ... ) : ... }
                                        // So if it sets it to 'idle', the UI will go back to "Run Analysis".
                                        // The original code revalidated and refreshed.
                                        // Maybe we should expose a "completed" state that persists until reset?
                                        // Let's look at the original code again.

                                        // Original:
                                        // if (update.status === 'completed') {
                                        //   setStatus('idle')
                                        //   ...
                                        //   revalidateRepositoryPage(repositoryId).then(...)
                                        //   return
                                        // }

                                        // So it resets to IDLE. The user sees the button go back to "Run Analysis" (or "Re-analyze").
                                        // But wait, the UI has:
                                        // {status === 'completed' ? ( <CheckCircle ... /> ) : ... }
                                        // If status is set to 'idle', this block is NOT shown.
                                        // So the "Analysis Complete" message is NEVER shown in the original code?
                                        // Let's re-read step 15 carefully.

                                        // Line 157: if (update.status === 'completed') {
                                        // Line 159:   setStatus('idle')
                                        // ...
                                        // Line 171:   return
                                        // }

                                        // Line 268: {status === 'completed' ? ( ... )

                                        // You are right. The "Analysis Complete" state is unreachable in the original code if it immediately sets it to 'idle'.
                                        // Unless... `update.status` comes from the server.
                                        // But `setStatus` is the local state.
                                        // So yes, the original code seems to flash or just reset.
                                        // However, maybe I should IMPROVE this behavior?
                                        // The user probably wants to see "Analysis Complete".
                                        // But the page refreshes.
                                        // If the page refreshes, the component remounts.
                                        // If the component remounts, `status` is 'idle'.
                                        // So the "Analysis Complete" state is ephemeral anyway.

                                        // I will stick to the original logic for now to avoid changing behavior too much, 
                                        // BUT I will set it to 'completed' first, then maybe let the parent handle the reset or just leave it.
                                        // Actually, if the page refreshes, the data `hasAnalysis` will become true.
                                        // So the button will show "Re-analyze".

                                        // Let's replicate the logic:
                                        // setStatus('idle')
                                        // revalidate...

                                        setStatus('idle')
                                        setProgress(0)
                                        setStage('')
                                        setMessage('')
                                        setAnalysisId(null)
                                        
                                        // Update global store
                                        updateTask(taskId, { status: 'completed', progress: 100 })

                                        revalidateRepositoryPage(repositoryId).then(() => {
                                            if (isMountedRef.current) {
                                                router.refresh()
                                            }
                                        })
                                        return
                                    } else if (update.status === 'failed') {
                                        setStatus('failed')
                                        setError(update.message || 'Analysis failed')
                                        updateTask(taskId, { status: 'failed', message: update.message || 'Analysis failed' })
                                        return
                                    } else if (update.status === 'running') {
                                        setStatus('running')
                                    }
                                } catch { }
                            }
                        }
                    }

                    if (mounted && status === 'running') {
                        retryCount++
                        if (retryCount < maxRetries) {
                            const delay = Math.min(baseDelay * Math.pow(2, retryCount - 1), 10000)
                            setMessage(`Connection lost. Reconnecting... (${retryCount}/${maxRetries})`)
                            await new Promise(resolve => setTimeout(resolve, delay))
                            continue
                        }
                    }
                    break
                } catch (err) {
                    if (!mounted) return
                    retryCount++
                    if (retryCount >= maxRetries) {
                        setError('Connection lost. Click to check status or retry.')
                        setStatus('failed')
                        return
                    }
                    const delay = Math.min(baseDelay * Math.pow(2, retryCount - 1), 10000)
                    setMessage(`Reconnecting... (${retryCount}/${maxRetries})`)
                    await new Promise(resolve => setTimeout(resolve, delay))
                }
            }
        }

        connectSSE()

        return () => {
            mounted = false
            if (eventSourceRef.current) {
                eventSourceRef.current.close()
            }
        }
    }, [analysisId, status, router, repositoryId, updateTask, taskId])

    return {
        status,
        progress,
        stage,
        message,
        vciScore,
        error,
        startAnalysis,
        reset
    }
}
