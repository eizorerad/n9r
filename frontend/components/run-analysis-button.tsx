'use client'

import { useTransition } from 'react'
import { Play, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAnalysisStream, STAGE_LABELS } from '@/hooks/use-analysis-stream'

interface RunAnalysisButtonProps {
  repositoryId: string
  hasAnalysis: boolean
}

export function RunAnalysisButton({ repositoryId, hasAnalysis }: RunAnalysisButtonProps) {
  const [isPending, startTransition] = useTransition()
  const {
    status,
    progress,
    stage,
    message,
    vciScore,
    error,
    startAnalysis
  } = useAnalysisStream(repositoryId)

  const handleClick = () => {
    if (status === 'pending' || status === 'running') {
      return
    }

    startTransition(() => {
      startAnalysis(repositoryId)
    })
  }

  const isProcessing = status === 'pending' || status === 'running' || isPending

  return (
    <div className="flex flex-col gap-2">
      <Button
        onClick={handleClick}
        disabled={isProcessing}
        variant={hasAnalysis ? "outline" : "default"}
        className={`flex items-center gap-2 ${!hasAnalysis ? 'shadow-lg shadow-primary/20' : ''}`}
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
            {status === 'pending' || isPending ? 'Starting...' : 'Analyzing...'}
          </>
        ) : (
          <>
            <Play className="h-4 w-4" />
            {hasAnalysis ? 'Re-analyze' : 'Run Analysis'}
          </>
        )}
      </Button>

      {/* Progress bar */}
      {isProcessing && !isPending && (
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
