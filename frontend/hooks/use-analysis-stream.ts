import { useState, useEffect, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { runAnalysis, getApiUrl, getAccessToken, revalidateRepositoryPage } from '@/app/actions/analysis'
import { useAnalysisProgressStore, getAnalysisTaskId } from '@/lib/stores/analysis-progress-store'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import { getAnalysisStatusQueryKey } from '@/lib/hooks/use-analysis-status'
import { parseSSEEvents, parseEventData, isProgressUpdate } from '@/lib/sse-parser'

export type AnalysisStatus = 'idle' | 'pending' | 'running' | 'reconnecting' | 'completed' | 'failed'

interface ProgressUpdate {
    analysis_id: string
    stage: string
    progress: number
    message: string | null
    status: string
    vci_score?: number
    commit_sha?: string
}

// Terminal statuses that should stop streaming
const TERMINAL_STATUSES = ['completed', 'failed'] as const
type TerminalStatus = typeof TERMINAL_STATUSES[number]

function isTerminalStatus(status: string): status is TerminalStatus {
    return TERMINAL_STATUSES.includes(status as TerminalStatus)
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

// Reconnection configuration
export interface ReconnectConfig {
    maxRetries: number
    initialDelay: number
    maxDelay: number
    backoffMultiplier: number
}

const DEFAULT_RECONNECT_CONFIG: ReconnectConfig = {
    maxRetries: 5,
    initialDelay: 1000,
    maxDelay: 30000,
    backoffMultiplier: 2,
}

// HTTP status codes that should NOT trigger reconnection
const NON_RETRYABLE_STATUS_CODES = [401, 403, 404] as const

/**
 * Check if an HTTP status code should trigger reconnection
 */
function isRetryableStatusCode(statusCode: number): boolean {
    // Don't retry auth errors (401, 403) or not found (404)
    if ((NON_RETRYABLE_STATUS_CODES as readonly number[]).includes(statusCode)) {
        return false
    }
    // Retry server errors (5xx)
    if (statusCode >= 500 && statusCode < 600) {
        return true
    }
    // Don't retry other client errors (4xx)
    if (statusCode >= 400 && statusCode < 500) {
        return false
    }
    // Retry other cases (network issues, etc.)
    return true
}

/**
 * Calculate delay with exponential backoff and jitter
 * Formula: min(initialDelay * (backoffMultiplier ^ attempt), maxDelay) * jitter
 * Jitter: 0.5 + random(0, 0.5) to prevent thundering herd
 */
function calculateBackoffDelay(
    attempt: number,
    config: ReconnectConfig
): number {
    const exponentialDelay = config.initialDelay * Math.pow(config.backoffMultiplier, attempt)
    const cappedDelay = Math.min(exponentialDelay, config.maxDelay)
    // Add jitter: multiply by 0.5 to 1.0
    const jitter = 0.5 + Math.random() * 0.5
    return Math.floor(cappedDelay * jitter)
}

interface UseAnalysisStreamResult {
    status: AnalysisStatus
    progress: number
    stage: string
    message: string
    vciScore: number | null
    error: string | null
    retryCount: number
    nextRetryIn: number | null
    startAnalysis: (repositoryId: string, commitSha?: string | null) => Promise<void>
    reset: () => void
}

interface UseAnalysisStreamOptions {
    reconnectConfig?: Partial<ReconnectConfig>
}

// Cache for server action results to avoid re-fetching during reconnection
interface ServerActionCache {
    apiUrl: string | null
    accessToken: string | null
    timestamp: number
}

export function useAnalysisStream(
    repositoryId: string,
    options: UseAnalysisStreamOptions = {}
): UseAnalysisStreamResult {
    const queryClient = useQueryClient()
    const [analysisId, setAnalysisId] = useState<string | null>(null)
    const [status, setStatus] = useState<AnalysisStatus>('idle')
    const [progress, setProgress] = useState(0)
    const [stage, setStage] = useState<string>('')
    const [message, setMessage] = useState<string>('')
    const [vciScore, setVciScore] = useState<number | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [retryCount, setRetryCount] = useState(0)
    const [nextRetryIn, setNextRetryIn] = useState<number | null>(null)

    // Merge reconnect config with defaults
    const reconnectConfig: ReconnectConfig = {
        ...DEFAULT_RECONNECT_CONFIG,
        ...options.reconnectConfig,
    }

    // Refs for cleanup - AbortController and stream reader
    const abortControllerRef = useRef<AbortController | null>(null)
    const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null)
    
    // Ref for retry count (used inside effect to avoid stale closures)
    const retryCountRef = useRef(0)
    
    // Cache for server action results
    const serverActionCacheRef = useRef<ServerActionCache>({
        apiUrl: null,
        accessToken: null,
        timestamp: 0,
    })

    // Global progress store
    const { addTask, updateTask } = useAnalysisProgressStore()
    const taskId = getAnalysisTaskId(repositoryId)

    // Commit selection store - to update selectedAnalysisId when analysis completes
    const { selectedCommitSha, setSelectedCommit } = useCommitSelectionStore()

    /**
     * Get cached server action results or fetch fresh ones
     * Cache is valid for the duration of the analysis session
     */
    const getServerActionResults = useCallback(async (): Promise<{
        apiUrl: string
        accessToken: string | null
    }> => {
        const cache = serverActionCacheRef.current
        
        // Use cached values if available (cache is cleared on reset or new analysis)
        if (cache.apiUrl && cache.accessToken) {
            return {
                apiUrl: cache.apiUrl,
                accessToken: cache.accessToken,
            }
        }

        // Fetch fresh values
        const [apiUrl, accessToken] = await Promise.all([
            getApiUrl(),
            getAccessToken(),
        ])

        // Update cache
        serverActionCacheRef.current = {
            apiUrl,
            accessToken,
            timestamp: Date.now(),
        }

        return { apiUrl, accessToken }
    }, [])

    /**
     * Clear server action cache
     */
    const clearServerActionCache = useCallback(() => {
        serverActionCacheRef.current = {
            apiUrl: null,
            accessToken: null,
            timestamp: 0,
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
        setRetryCount(0)
        setNextRetryIn(null)
        retryCountRef.current = 0
        clearServerActionCache()
    }, [clearServerActionCache])

    const startAnalysis = useCallback(async (repoId: string, commitSha?: string | null) => {
        console.log('[useAnalysisStream] startAnalysis called:', { repoId, commitSha, taskId })
        
        // Clear cache for new analysis session
        clearServerActionCache()
        
        setError(null)
        setStatus('pending')
        setProgress(0)
        setStage('queued')
        setMessage('Starting analysis...')
        setVciScore(null)
        setRetryCount(0)
        setNextRetryIn(null)
        retryCountRef.current = 0

        // Add analysis task to global progress store
        // NOTE: We do NOT add the embeddings task here anymore.
        // The semantic-analysis-section.tsx polling will add it when it detects
        // embeddings actually running via the API. This prevents "ghost" tasks
        // that get stuck at 0% when the polling misses the running state.
        console.log('[useAnalysisStream] Adding analysis task to store:', taskId)
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
            // Pass commitSha to runAnalysis - if null/undefined, backend uses latest commit
            const result = await runAnalysis(repoId, commitSha ?? undefined)

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
    }, [addTask, updateTask, taskId, clearServerActionCache])

    // Connect to SSE when analysisId is set
    useEffect(() => {
        if (!analysisId || status === 'completed' || status === 'failed' || status === 'idle') {
            return
        }

        let mounted = true
        retryCountRef.current = 0

        // Create AbortController for this connection
        const abortController = new AbortController()
        abortControllerRef.current = abortController

        const connectSSE = async (): Promise<void> => {
            while (mounted && retryCountRef.current < reconnectConfig.maxRetries && !abortController.signal.aborted) {
                try {
                    // Use cached server action results to avoid re-fetching on every retry
                    const { apiUrl, accessToken } = await getServerActionResults()

                    if (!accessToken) {
                        setError('Not authenticated')
                        setStatus('failed')
                        return
                    }

                    console.log('[SSE] Connecting to:', `${apiUrl}/analyses/${analysisId}/stream`)
                    const response = await fetch(`${apiUrl}/analyses/${analysisId}/stream`, {
                        headers: {
                            'Authorization': `Bearer ${accessToken}`,
                            'Accept': 'text/event-stream',
                        },
                        signal: abortController.signal,
                    })

                    if (!response.ok) {
                        const statusCode = response.status
                        
                        // Handle non-retryable errors
                        if (!isRetryableStatusCode(statusCode)) {
                            if (statusCode === 401) {
                                // Session expired - redirect to login
                                window.location.href = "/login?error=session_expired"
                                return
                            }
                            if (statusCode === 403) {
                                setError('Access denied. You may not have permission to view this analysis.')
                                setStatus('failed')
                                return
                            }
                            if (statusCode === 404) {
                                setError('Analysis not found. It may have been deleted.')
                                setStatus('failed')
                                return
                            }
                            // Other non-retryable client errors
                            setError(`Request failed: ${statusCode}`)
                            setStatus('failed')
                            return
                        }
                        
                        // Retryable error - throw to trigger retry logic
                        throw new Error(`SSE connection failed: ${statusCode}`)
                    }

                    console.log('[SSE] Connected successfully')
                    const reader = response.body?.getReader()
                    if (!reader) throw new Error('No response body')

                    // Store reader ref for cleanup
                    readerRef.current = reader

                    // Reset retry count on successful connection
                    retryCountRef.current = 0
                    setRetryCount(0)
                    setNextRetryIn(null)
                    
                    // If we were reconnecting, switch back to running
                    if (status === 'reconnecting') {
                        setStatus('running')
                    }
                    
                    const decoder = new TextDecoder()
                    let sseBuffer = ''

                    // Helper function to process a single progress update
                    const processUpdate = (update: ProgressUpdate): 'continue' | 'stop' | 'retry' => {
                        if (!mounted || abortController.signal.aborted) return 'stop'

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

                        // Handle status transitions
                        if (update.status === 'completed') {
                            console.log('[SSE] Analysis completed! VCI:', update.vci_score)
                            
                            // Set completed status - this is now "sticky" until reset() is called
                            setStatus('completed')
                            setProgress(100)
                            setStage('completed')
                            setMessage('Analysis complete')

                            // Update global store - mark analysis as completed
                            updateTask(taskId, { status: 'completed', progress: 100, stage: 'completed', message: 'Analysis complete' })

                            // Update commit selection store with the new analysis ID
                            // This triggers all panels to re-fetch data for the completed analysis
                            if (analysisId) {
                                const commitSha = selectedCommitSha || update.commit_sha
                                if (commitSha) {
                                    setSelectedCommit(commitSha, analysisId, repositoryId)
                                }
                            }

                            // Invalidate React Query cache for commits to refresh the timeline
                            queryClient.invalidateQueries({ queryKey: ['commits', repositoryId] })

                            // Invalidate React Query cache for analysis status
                            queryClient.invalidateQueries({
                                queryKey: getAnalysisStatusQueryKey(repositoryId, analysisId)
                            })

                            // Clear local analysisId after updating store
                            setAnalysisId(null)

                            // Revalidate server data for next page load
                            revalidateRepositoryPage(repositoryId)

                            // NOTE: We no longer reset to idle here.
                            // The completed status is now "sticky" until the consumer calls reset().
                            // This prevents UI flickering and ensures the button shows "Analysis Complete"
                            // reliably until the user explicitly starts a new analysis.
                            return 'stop'
                        } else if (update.status === 'failed') {
                            // Terminal state - stop streaming, don't retry
                            setStatus('failed')
                            setError(update.message || 'Analysis failed')
                            updateTask(taskId, { status: 'failed', message: update.message || 'Analysis failed' })
                            return 'stop'
                        } else if (update.status === 'error') {
                            // Transient error from SSE - trigger retry
                            // This is a server-side transient error, should retry
                            console.log('[SSE] Received transient error status, will retry:', update.message)
                            setError(update.message || 'Temporary error occurred')
                            return 'retry'
                        } else if (update.status === 'running' || update.status === 'pending') {
                            // Normal progress updates
                            setStatus('running')
                            setError(null) // Clear any previous transient errors
                        }

                        return 'continue'
                    }

                    while (mounted && !abortController.signal.aborted) {
                        const { done, value } = await reader.read()

                        if (done) break

                        // Decode chunk and parse SSE events using proper event-boundary parsing
                        const chunk = decoder.decode(value, { stream: true })
                        const { events, remainingBuffer } = parseSSEEvents(chunk, sseBuffer)
                        sseBuffer = remainingBuffer

                        // Process each complete SSE event
                        for (const event of events) {
                            // Parse the event data as JSON
                            const update = parseEventData<ProgressUpdate>(event, {
                                logErrors: true,
                                context: 'SSE',
                            })

                            // Skip events that failed to parse or don't match expected shape
                            if (!update || !isProgressUpdate(update)) {
                                continue
                            }

                            // Process the update and check if we should stop
                            const result = processUpdate(update)
                            if (result === 'stop') {
                                return
                            }
                            if (result === 'retry') {
                                // Break out of event loop to trigger retry
                                throw new Error('Transient SSE error - retrying')
                            }
                        }
                    }

                    // Clean up reader ref after normal completion
                    readerRef.current = null

                    // Stream ended without terminal status - might need to reconnect
                    if (mounted && (status === 'running' || status === 'reconnecting') && !abortController.signal.aborted) {
                        retryCountRef.current++
                        setRetryCount(retryCountRef.current)
                        
                        if (retryCountRef.current < reconnectConfig.maxRetries) {
                            const delay = calculateBackoffDelay(retryCountRef.current - 1, reconnectConfig)
                            setStatus('reconnecting')
                            setNextRetryIn(delay)
                            setMessage(`Connection lost. Reconnecting in ${Math.ceil(delay / 1000)}s... (${retryCountRef.current}/${reconnectConfig.maxRetries})`)
                            console.log(`[SSE] Stream ended, reconnecting in ${delay}ms (attempt ${retryCountRef.current}/${reconnectConfig.maxRetries})`)
                            await new Promise(resolve => setTimeout(resolve, delay))
                            setNextRetryIn(null)
                            continue
                        }
                    }
                    break
                } catch (err) {
                    // Don't treat abort as an error
                    if (err instanceof Error && err.name === 'AbortError') {
                        console.log('[SSE] Connection aborted')
                        return
                    }
                    if (!mounted || abortController.signal.aborted) return
                    
                    retryCountRef.current++
                    setRetryCount(retryCountRef.current)
                    
                    if (retryCountRef.current >= reconnectConfig.maxRetries) {
                        console.log(`[SSE] Max retries (${reconnectConfig.maxRetries}) exceeded`)
                        setError('Connection lost after multiple retries. Click to check status or retry.')
                        setStatus('failed')
                        setNextRetryIn(null)
                        return
                    }
                    
                    const delay = calculateBackoffDelay(retryCountRef.current - 1, reconnectConfig)
                    setStatus('reconnecting')
                    setNextRetryIn(delay)
                    setMessage(`Reconnecting in ${Math.ceil(delay / 1000)}s... (${retryCountRef.current}/${reconnectConfig.maxRetries})`)
                    console.log(`[SSE] Error occurred, reconnecting in ${delay}ms (attempt ${retryCountRef.current}/${reconnectConfig.maxRetries}):`, err)
                    await new Promise(resolve => setTimeout(resolve, delay))
                    setNextRetryIn(null)
                }
            }
        }

        connectSSE()

        // Cleanup function - abort controller and cancel reader
        return () => {
            mounted = false
            console.log('[SSE] Cleaning up connection')
            
            // Abort the fetch request
            abortController.abort()
            abortControllerRef.current = null
            
            // Cancel the reader if it exists
            if (readerRef.current) {
                readerRef.current.cancel().catch(() => {
                    // Ignore cancel errors - reader may already be closed
                })
                readerRef.current = null
            }
        }
    }, [analysisId, status, repositoryId, updateTask, taskId, queryClient, selectedCommitSha, setSelectedCommit, reconnectConfig, getServerActionResults])

    return {
        status,
        progress,
        stage,
        message,
        vciScore,
        error,
        retryCount,
        nextRetryIn,
        startAnalysis,
        reset
    }
}
