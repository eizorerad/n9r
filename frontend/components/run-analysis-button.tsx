'use client'

import { useState, useTransition, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { Play, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { runAnalysis, getApiUrl, getAccessToken, revalidateRepositoryPage } from '@/app/actions/analysis'

interface RunAnalysisButtonProps {
  repositoryId: string
  hasAnalysis: boolean
}

type AnalysisStatus = 'idle' | 'pending' | 'running' | 'completed' | 'failed'

interface ProgressUpdate {
  analysis_id: string
  stage: string
  progress: number
  message: string | null
  status: string
  vci_score?: number
}

// Stage labels for user-friendly display
const STAGE_LABELS: Record<string, string> = {
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

export function RunAnalysisButton({ repositoryId, hasAnalysis }: RunAnalysisButtonProps) {
  const router = useRouter()
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)
  const [analysisId, setAnalysisId] = useState<string | null>(null)
  const [status, setStatus] = useState<AnalysisStatus>('idle')
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState<string>('')
  const [message, setMessage] = useState<string>('')
  const [vciScore, setVciScore] = useState<number | null>(null)
  
  const eventSourceRef = useRef<EventSource | null>(null)
  const isMountedRef = useRef(true)
  
  // Track mount state with ref (survives re-renders)
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
  
  // Connect to SSE when analysisId is set (with auto-reconnection)
  useEffect(() => {
    if (!analysisId || status === 'completed' || status === 'failed' || status === 'idle') {
      return
    }
    
    let mounted = true
    let retryCount = 0
    const maxRetries = 5
    const baseDelay = 1000 // 1 second
    
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
          
          // Close existing connection
          if (eventSourceRef.current) {
            eventSourceRef.current.close()
          }
          
          // Create SSE connection with auth header
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
          if (!reader) {
            throw new Error('No response body')
          }
          
          // Reset retry count on successful connection
          retryCount = 0
          
          const decoder = new TextDecoder()
          let buffer = '' // Buffer for incomplete chunks
          
          // Read SSE stream
          while (mounted) {
            const { done, value } = await reader.read()
            
            if (done) {
              // Stream ended - check if we got terminal status
              // If not, try to reconnect
              break
            }
            
            // Append to buffer and process complete lines
            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            
            // Keep last incomplete line in buffer
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
                  
                  if (update.vci_score !== undefined) {
                    setVciScore(update.vci_score)
                  }
                  
                  if (update.status === 'completed') {
                    // Reset state immediately - don't wait for async operations
                    setStatus('idle')
                    setProgress(0)
                    setStage('')
                    setMessage('')
                    setAnalysisId(null)
                    
                    // Revalidate cache and refresh page in background
                    revalidateRepositoryPage(repositoryId).then(() => {
                      if (isMountedRef.current) {
                        router.refresh()
                      }
                    })
                    return // Success - exit completely
                  } else if (update.status === 'failed') {
                    setStatus('failed')
                    setError(update.message || 'Analysis failed')
                    return // Failed - exit completely
                  } else if (update.status === 'running') {
                    setStatus('running')
                  }
                } catch {
                  // Ignore parse errors for non-JSON lines
                }
              }
            }
          }
          
          // Stream ended without terminal status - reconnect
          if (mounted && status === 'running') {
            retryCount++
            if (retryCount < maxRetries) {
              const delay = Math.min(baseDelay * Math.pow(2, retryCount - 1), 10000)
              setMessage(`Connection lost. Reconnecting... (${retryCount}/${maxRetries})`)
              await new Promise(resolve => setTimeout(resolve, delay))
              continue // Retry
            }
          }
          
          break // Exit retry loop
          
        } catch (err) {
          if (!mounted) return
          
          console.error('SSE error:', err)
          retryCount++
          
          if (retryCount >= maxRetries) {
            // Max retries reached - show error with recovery hint
            setError('Connection lost. Click to check status or retry.')
            setStatus('failed')
            return
          }
          
          // Calculate delay with exponential backoff (max 10 seconds)
          const delay = Math.min(baseDelay * Math.pow(2, retryCount - 1), 10000)
          setMessage(`Reconnecting... (${retryCount}/${maxRetries})`)
          await new Promise(resolve => setTimeout(resolve, delay))
          // Continue to retry
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
  }, [analysisId, status, router])
  
  const handleClick = () => {
    // Prevent double-click
    if (status === 'pending' || status === 'running') {
      return
    }
    
    setError(null)
    setStatus('pending')
    setProgress(0)
    setStage('queued')
    setMessage('Starting analysis...')
    setVciScore(null)
    
    startTransition(async () => {
      const result = await runAnalysis(repositoryId)
      
      if (result.success && result.analysisId) {
        setAnalysisId(result.analysisId)
        setStatus('running')
      } else {
        setStatus('failed')
        setError(result.error || 'Failed to start analysis')
        setProgress(0)
      }
    })
  }
  
  const isProcessing = status === 'pending' || status === 'running'
  
  return (
    <div className="flex flex-col gap-2">
      <Button 
        onClick={handleClick}
        disabled={isPending || isProcessing}
        variant={hasAnalysis ? "outline" : "default"}
        className="flex items-center gap-2"
      >
        {status === 'completed' ? (
          <>
            <CheckCircle className="h-4 w-4 text-green-500" />
            Analysis Complete
            {vciScore !== null && ` (VCI: ${vciScore})`}
          </>
        ) : isProcessing ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            {status === 'pending' ? 'Starting...' : 'Analyzing...'}
          </>
        ) : (
          <>
            <Play className="h-4 w-4" />
            {hasAnalysis ? 'Re-analyze' : 'Run Analysis'}
          </>
        )}
      </Button>
      
      {/* Progress bar */}
      {isProcessing && (
        <div className="w-full">
          <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
            <div 
              className="h-full bg-blue-500 transition-all duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-gray-400 mt-1 text-center">
            {message || STAGE_LABELS[stage] || stage}
          </p>
        </div>
      )}
      
      {/* Status messages */}
      {status === 'completed' && (
        <div className="flex items-center gap-2 text-sm text-green-400">
          <CheckCircle className="h-3 w-3" />
          <Loader2 className="h-3 w-3 animate-spin" />
          Updating results...
        </div>
      )}
      
      {error && (
        <div className="flex items-center gap-2 text-sm text-red-400">
          <AlertCircle className="h-3 w-3" />
          {error}
        </div>
      )}
    </div>
  )
}
