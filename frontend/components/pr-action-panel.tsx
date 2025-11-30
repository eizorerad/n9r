'use client'

import { useState } from 'react'
import { 
  Check, 
  X, 
  Edit3, 
  GitPullRequest,
  Loader2,
  AlertCircle
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface PRActionPanelProps {
  prId: string
  prTitle: string
  prUrl?: string
  prNumber?: number
  status: 'pending' | 'approved' | 'rejected' | 'merged'
  onApprove?: () => Promise<void>
  onReject?: () => Promise<void>
  onRevise?: (feedback: string) => Promise<void>
  className?: string
}

export function PRActionPanel({
  prId,
  prTitle,
  prUrl,
  prNumber,
  status,
  onApprove,
  onReject,
  onRevise,
  className,
}: PRActionPanelProps) {
  const [isLoading, setIsLoading] = useState<'approve' | 'reject' | 'revise' | null>(null)
  const [showReviseForm, setShowReviseForm] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleApprove = async () => {
    if (!onApprove) return
    setIsLoading('approve')
    setError(null)
    try {
      await onApprove()
    } catch (e) {
      setError('Failed to approve PR')
    } finally {
      setIsLoading(null)
    }
  }

  const handleReject = async () => {
    if (!onReject) return
    setIsLoading('reject')
    setError(null)
    try {
      await onReject()
    } catch (e) {
      setError('Failed to reject PR')
    } finally {
      setIsLoading(null)
    }
  }

  const handleRevise = async () => {
    if (!onRevise || !feedback.trim()) return
    setIsLoading('revise')
    setError(null)
    try {
      await onRevise(feedback)
      setFeedback('')
      setShowReviseForm(false)
    } catch (e) {
      setError('Failed to submit revision request')
    } finally {
      setIsLoading(null)
    }
  }

  const isPending = status === 'pending'
  const isTerminal = status === 'merged' || status === 'rejected'

  return (
    <div className={cn('bg-gray-900 border border-gray-800 rounded-lg', className)}>
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800">
        <GitPullRequest className="h-5 w-5 text-green-400" />
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-sm truncate">{prTitle}</h3>
          {prNumber && (
            <p className="text-xs text-gray-500">#{prNumber}</p>
          )}
        </div>
        <StatusBadge status={status} />
      </div>

      {/* Actions */}
      <div className="p-4">
        {error && (
          <div className="flex items-center gap-2 mb-4 p-3 bg-red-900/20 border border-red-800 rounded-lg">
            <AlertCircle className="h-4 w-4 text-red-400" />
            <span className="text-sm text-red-300">{error}</span>
          </div>
        )}

        {isPending && !showReviseForm && (
          <div className="space-y-3">
            <p className="text-sm text-gray-400">
              Review the changes and choose an action:
            </p>
            
            <div className="flex gap-2">
              <Button
                onClick={handleApprove}
                disabled={isLoading !== null}
                className="flex-1 bg-green-600 hover:bg-green-700"
              >
                {isLoading === 'approve' ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Check className="h-4 w-4 mr-2" />
                )}
                Approve & Merge
              </Button>
              
              <Button
                onClick={handleReject}
                disabled={isLoading !== null}
                variant="destructive"
                className="flex-1"
              >
                {isLoading === 'reject' ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <X className="h-4 w-4 mr-2" />
                )}
                Reject
              </Button>
            </div>
            
            <Button
              onClick={() => setShowReviseForm(true)}
              disabled={isLoading !== null}
              variant="outline"
              className="w-full border-gray-700 hover:bg-gray-800"
            >
              <Edit3 className="h-4 w-4 mr-2" />
              Request Revisions
            </Button>
          </div>
        )}

        {isPending && showReviseForm && (
          <div className="space-y-3">
            <div>
              <label className="text-sm text-gray-400 block mb-2">
                What should be changed?
              </label>
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Describe the changes you'd like to see..."
                rows={4}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-green-500 placeholder-gray-500"
              />
            </div>
            
            <div className="flex gap-2">
              <Button
                onClick={() => setShowReviseForm(false)}
                variant="outline"
                className="flex-1 border-gray-700 hover:bg-gray-800"
              >
                Cancel
              </Button>
              <Button
                onClick={handleRevise}
                disabled={!feedback.trim() || isLoading !== null}
                className="flex-1 bg-blue-600 hover:bg-blue-700"
              >
                {isLoading === 'revise' ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Edit3 className="h-4 w-4 mr-2" />
                )}
                Submit Feedback
              </Button>
            </div>
          </div>
        )}

        {isTerminal && (
          <div className="text-center py-4">
            {status === 'merged' ? (
              <>
                <Check className="h-8 w-8 text-green-500 mx-auto mb-2" />
                <p className="text-sm text-gray-400">
                  This PR has been merged successfully.
                </p>
              </>
            ) : (
              <>
                <X className="h-8 w-8 text-red-500 mx-auto mb-2" />
                <p className="text-sm text-gray-400">
                  This PR has been rejected.
                </p>
              </>
            )}
            
            {prUrl && (
              <a
                href={prUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-green-400 hover:underline mt-2 inline-block"
              >
                View on GitHub →
              </a>
            )}
          </div>
        )}

        {status === 'approved' && (
          <div className="text-center py-4">
            <Loader2 className="h-8 w-8 text-blue-500 mx-auto mb-2 animate-spin" />
            <p className="text-sm text-gray-400">
              Merging PR...
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { color: string; label: string }> = {
    pending: { color: 'bg-yellow-900 text-yellow-300', label: 'Pending Review' },
    approved: { color: 'bg-blue-900 text-blue-300', label: 'Approved' },
    rejected: { color: 'bg-red-900 text-red-300', label: 'Rejected' },
    merged: { color: 'bg-green-900 text-green-300', label: 'Merged' },
  }

  const { color, label } = config[status] || config.pending

  return (
    <span className={cn(
      'px-2 py-0.5 rounded-full text-xs font-medium',
      color
    )}>
      {label}
    </span>
  )
}
