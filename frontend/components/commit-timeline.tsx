'use client'

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useQuery, useInfiniteQuery } from '@tanstack/react-query'
import { GitCommit, Loader2, RefreshCw, AlertCircle, ShieldAlert, Clock, LogOut } from 'lucide-react'
import { cn } from '@/lib/utils'
import { branchApi, commitApi, ApiError, type Commit } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import { useAnalysisDataStore } from '@/lib/stores/analysis-data-store'
import { RunAnalysisButton } from '@/components/run-analysis-button'

interface CommitTimelineProps {
  repositoryId: string
  defaultBranch: string
  token: string
  currentAnalysisCommit?: string | null
  hasAnalysis?: boolean
}

// Helper to format relative time
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSecs = Math.floor(diffMs / 1000)
  const diffMins = Math.floor(diffSecs / 60)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffDays > 30) {
    return date.toLocaleDateString()
  } else if (diffDays > 0) {
    return `${diffDays}d ago`
  } else if (diffHours > 0) {
    return `${diffHours}h ago`
  } else if (diffMins > 0) {
    return `${diffMins}m ago`
  } else {
    return 'just now'
  }
}

// VCI score color helper
function getVCIColor(score: number): string {
  if (score >= 80) return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
  if (score >= 60) return 'bg-amber-500/20 text-amber-400 border-amber-500/30'
  if (score >= 40) return 'bg-orange-500/20 text-orange-400 border-orange-500/30'
  return 'bg-red-500/20 text-red-400 border-red-500/30'
}

// CommitRow subcomponent
interface CommitRowProps {
  commit: Commit
  isLast: boolean
  isSelected: boolean
  isCurrentAnalysis: boolean
  onClick: () => void
}

function CommitRow({ commit, isLast, isSelected, isCurrentAnalysis, onClick }: CommitRowProps) {
  const hasAnalysis = commit.analysis_status !== null
  const isCompleted = commit.analysis_status === 'completed'
  const isPending = commit.analysis_status === 'pending' || commit.analysis_status === 'running'

  return (
    <div 
      className={cn(
        'flex gap-3 group rounded-lg transition-all cursor-pointer -mx-2 px-2 py-1.5',
        isSelected && 'bg-primary/10 ring-1 ring-primary/30',
        !isSelected && 'hover:bg-muted/50'
      )}
      onClick={onClick}
    >
      {/* Timeline indicator */}
      <div className="flex flex-col items-center">
        <div
          className={cn(
            'w-3 h-3 rounded-full border-2 flex-shrink-0 mt-1 transition-all',
            isSelected
              ? 'bg-primary border-primary ring-2 ring-primary/30 ring-offset-1 ring-offset-background'
              : hasAnalysis
                ? 'bg-primary border-primary'
                : 'bg-background border-muted-foreground/40'
          )}
        />
        {!isLast && (
          <div className="w-0.5 flex-1 bg-border/50 my-1" />
        )}
      </div>

      {/* Commit content */}
      <div className={cn('flex-1 min-w-0', !isLast && 'pb-2')}>
        <div className="flex items-center gap-2 mb-0.5 flex-wrap">
          <code className={cn(
            'text-xs font-mono px-1.5 py-0.5 rounded',
            isSelected 
              ? 'text-primary bg-primary/20 font-semibold' 
              : 'text-muted-foreground bg-muted/50'
          )}>
            {commit.short_sha}
          </code>
          {isCurrentAnalysis && (
            <Badge variant="default" className="text-[10px] px-1.5 py-0 h-4 bg-primary/80">
              current
            </Badge>
          )}
          {isPending && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">
              <Loader2 className="h-2.5 w-2.5 mr-1 animate-spin" />
              analyzing
            </Badge>
          )}
          {isCompleted && commit.vci_score !== null && (
            <Badge variant="outline" className={cn('text-[10px] px-1.5 py-0 h-4', getVCIColor(commit.vci_score))}>
              {commit.vci_score.toFixed(0)}
            </Badge>
          )}
        </div>
        <p className="text-sm truncate" title={commit.message}>
          {commit.message_headline}
        </p>
        <div className="flex items-center gap-1.5 mt-1 text-[11px] text-muted-foreground">
          <Avatar className="h-3.5 w-3.5">
            {commit.author_avatar_url && <AvatarImage src={commit.author_avatar_url} alt={commit.author_name} />}
            <AvatarFallback className="text-[7px]">{commit.author_name.slice(0, 2).toUpperCase()}</AvatarFallback>
          </Avatar>
          <span className="truncate">{commit.author_name}</span>
          <span>•</span>
          <span>{formatRelativeTime(commit.committed_at)}</span>
        </div>
      </div>
    </div>
  )
}

// Loading skeleton
function CommitSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="flex gap-3">
          <div className="flex flex-col items-center">
            <Skeleton className="w-3 h-3 rounded-full" />
            <Skeleton className="w-0.5 flex-1 my-1" />
          </div>
          <div className="flex-1 pb-3">
            <Skeleton className="h-4 w-20 mb-1" />
            <Skeleton className="h-4 w-3/4 mb-1.5" />
            <Skeleton className="h-3 w-32" />
          </div>
        </div>
      ))}
    </div>
  )
}


// Main component
export function CommitTimeline({ repositoryId, defaultBranch, token, currentAnalysisCommit, hasAnalysis = false }: CommitTimelineProps) {
  const [selectedBranch, setSelectedBranch] = useState<string>(defaultBranch)
  const loadMoreRef = useRef<HTMLDivElement>(null)
  
  // Use global commit selection store instead of local state
  const { 
    selectedCommitSha, 
    setSelectedCommit, 
    clearSelection,
    repositoryId: storeRepositoryId 
  } = useCommitSelectionStore()

  // Fetch branches
  const {
    data: branchesData,
    isLoading: branchesLoading,
    error: branchesError,
    refetch: refetchBranches,
  } = useQuery({
    queryKey: ['branches', repositoryId],
    queryFn: () => branchApi.list(token, repositoryId),
    enabled: !!token && !!repositoryId,
    staleTime: 5 * 60 * 1000,
  })

  // Fetch commits with infinite scroll
  // Smart polling: only poll when analysis is actively running
  const {
    data: commitsData,
    isLoading: commitsLoading,
    error: commitsError,
    refetch: refetchCommits,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['commits', repositoryId, selectedBranch],
    queryFn: ({ pageParam = 1 }) => 
      commitApi.list(token, repositoryId, { branch: selectedBranch, per_page: 30, page: pageParam }),
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.page + 1 : undefined,
    initialPageParam: 1,
    enabled: !!token && !!repositoryId && !!selectedBranch,
    staleTime: 60 * 1000,
    // Smart polling: only poll when selected commit has active analysis
    refetchInterval: (query) => {
      if (!selectedCommitSha) return false
      
      // Find the selected commit in the current data
      const commits = query.state.data?.pages.flatMap(page => page.commits) || []
      const selectedCommit = commits.find(c => c.sha === selectedCommitSha)
      
      // Only poll if analysis is actively running or pending
      if (selectedCommit?.analysis_status === 'running' || 
          selectedCommit?.analysis_status === 'pending') {
        return 5000  // Fast polling during active analysis
      }
      
      return false  // Stop polling when idle/completed/failed
    },
    // Also refetch when window regains focus (for idle state updates)
    refetchOnWindowFocus: true,
  })

  const branches = branchesData?.data || []
  // Flatten all pages into single commits array - memoized to prevent reference changes
  const commits = useMemo(() => 
    commitsData?.pages.flatMap(page => page.commits) || [],
    [commitsData?.pages]
  )

  // Intersection Observer for infinite scroll
  const handleObserver = useCallback((entries: IntersectionObserverEntry[]) => {
    const [target] = entries
    if (target.isIntersecting && hasNextPage && !isFetchingNextPage) {
      fetchNextPage()
    }
  }, [fetchNextPage, hasNextPage, isFetchingNextPage])

  useEffect(() => {
    const element = loadMoreRef.current
    if (!element) return

    const observer = new IntersectionObserver(handleObserver, {
      root: null,
      rootMargin: '100px',
      threshold: 0,
    })

    observer.observe(element)
    return () => observer.disconnect()
  }, [handleObserver])

  // Handle commit click - toggle selection or select new commit
  const handleCommitClick = (commit: Commit) => {
    if (selectedCommitSha === commit.sha) {
      clearSelection()
    } else {
      setSelectedCommit(commit.sha, commit.analysis_id || null, repositoryId)
    }
  }
  
  // Auto-select most recent analyzed commit on mount or when commits change
  useEffect(() => {
    const shouldAutoSelect = !selectedCommitSha || storeRepositoryId !== repositoryId
    
    if (shouldAutoSelect && commits.length > 0) {
      const mostRecentAnalyzed = commits.find(c => c.analysis_status === 'completed')
      
      if (mostRecentAnalyzed) {
        setSelectedCommit(
          mostRecentAnalyzed.sha, 
          mostRecentAnalyzed.analysis_id || null, 
          repositoryId
        )
      } else {
        const mostRecent = commits[0]
        if (mostRecent) {
          setSelectedCommit(mostRecent.sha, mostRecent.analysis_id || null, repositoryId)
        }
      }
    }
  }, [commits, repositoryId, selectedCommitSha, storeRepositoryId, setSelectedCommit])
  
  // Auto-update selectedAnalysisId when analysis completes
  const { selectedAnalysisId } = useCommitSelectionStore()
  
  useEffect(() => {
    if (!selectedCommitSha || !commits.length) return
    
    const currentCommit = commits.find(c => c.sha === selectedCommitSha)
    if (!currentCommit) return
    
    const newAnalysisId = currentCommit.analysis_id || null
    if (newAnalysisId && !selectedAnalysisId) {
      setSelectedCommit(selectedCommitSha, newAnalysisId, repositoryId)
    }
  }, [commits, selectedCommitSha, selectedAnalysisId, setSelectedCommit, repositoryId])

  // Invalidate analysis cache when status changes to completed
  const { invalidateAnalysis } = useAnalysisDataStore()
  const prevStatusRef = useRef<Record<string, string>>({})
  
  useEffect(() => {
    if (!commits.length || !selectedAnalysisId) return
    
    const selectedCommit = commits.find(c => c.sha === selectedCommitSha)
    if (!selectedCommit || !selectedCommit.analysis_id) return
    
    const analysisId = selectedCommit.analysis_id
    const currentStatus = selectedCommit.analysis_status
    const prevStatus = prevStatusRef.current[analysisId]
    
    if (currentStatus === 'completed' && prevStatus && prevStatus !== 'completed') {
      invalidateAnalysis(analysisId)
    }
    
    if (currentStatus) {
      prevStatusRef.current[analysisId] = currentStatus
    }
  }, [commits, selectedCommitSha, selectedAnalysisId, invalidateAnalysis])

  // Error handling
  if (branchesError || commitsError) {
    const error = branchesError || commitsError
    
    let errorIcon = <AlertCircle className="h-8 w-8 text-destructive mb-3" />
    let errorTitle = 'Failed to load'
    let errorMessage = 'An error occurred.'
    let showRetry = true
    
    if (error instanceof ApiError) {
      errorMessage = error.message || 'An error occurred.'
      if (error.isRateLimitError()) {
        errorIcon = <Clock className="h-8 w-8 text-amber-500 mb-3" />
        errorTitle = 'Rate limit'
        errorMessage = 'Try again later.'
      } else if (error.isPermissionError()) {
        errorIcon = <ShieldAlert className="h-8 w-8 text-destructive mb-3" />
        if (error.message?.toLowerCase().includes('github token')) {
          errorTitle = 'GitHub reconnection needed'
          errorMessage = 'Your GitHub access has expired.'
          return (
            <div className="flex flex-col items-center justify-center py-6 text-center">
              {errorIcon}
              <p className="text-sm font-medium mb-1">{errorTitle}</p>
              <p className="text-xs text-muted-foreground mb-3">{errorMessage}</p>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => window.location.href = '/login?error=github_token_expired'}
              >
                <LogOut className="h-3.5 w-3.5 mr-1.5" />
                Re-authenticate
              </Button>
            </div>
          )
        } else {
          errorTitle = 'Access denied'
        }
        showRetry = false
      } else if (error.isAuthenticationError()) {
        errorIcon = <ShieldAlert className="h-8 w-8 text-destructive mb-3" />
        errorTitle = 'Auth failed'
        showRetry = false
      }
    }
    
    return (
      <div className="flex flex-col items-center justify-center py-6 text-center">
        {errorIcon}
        <p className="text-sm font-medium mb-1">{errorTitle}</p>
        <p className="text-xs text-muted-foreground mb-3">{errorMessage}</p>
        {showRetry && (
          <Button variant="outline" size="sm" onClick={() => { refetchBranches(); refetchCommits() }}>
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            Retry
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Branch selector */}
      <div className="flex items-center gap-2">
        <GitCommit className="h-4 w-4 text-muted-foreground" />
        <Select value={selectedBranch} onValueChange={setSelectedBranch} disabled={branchesLoading}>
          <SelectTrigger className="w-[180px] h-8 text-sm">
            <SelectValue placeholder="Select branch" />
          </SelectTrigger>
          <SelectContent>
            {branches.map((branch) => (
              <SelectItem key={branch.name} value={branch.name}>
                <div className="flex items-center gap-2">
                  <span>{branch.name}</span>
                  {branch.is_default && (
                    <Badge variant="secondary" className="text-[10px] px-1 py-0">default</Badge>
                  )}
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Run Analysis Button */}
      <RunAnalysisButton
        repositoryId={repositoryId}
        hasAnalysis={hasAnalysis}
      />

      {/* Commits list */}
      {commitsLoading ? (
        <CommitSkeleton />
      ) : commits.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-6 text-center">
          <GitCommit className="h-8 w-8 text-muted-foreground/50 mb-2" />
          <p className="text-sm text-muted-foreground">No commits found</p>
        </div>
      ) : (
        <div className="space-y-0">
          {commits.map((commit, index) => (
            <CommitRow
              key={commit.sha}
              commit={commit}
              isLast={index === commits.length - 1 && !hasNextPage}
              isSelected={selectedCommitSha === commit.sha}
              isCurrentAnalysis={currentAnalysisCommit === commit.sha}
              onClick={() => handleCommitClick(commit)}
            />
          ))}
          
          {/* Infinite scroll trigger */}
          <div ref={loadMoreRef} className="py-2">
            {isFetchingNextPage && (
              <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Loading more...
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
