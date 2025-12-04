'use client'

import { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { SemanticSearch } from '@/components/semantic-search'
import { ArchitectureHealth } from '@/components/architecture-health'
import { ClusterMap } from '@/components/cluster-map'
import { SimilarCode } from '@/components/similar-code'
import { TechDebtHeatmap } from '@/components/tech-debt-heatmap'
import { useAnalysisProgressStore, getEmbeddingsTaskId } from '@/lib/stores/analysis-progress-store'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import { Loader2 } from 'lucide-react'

interface EmbeddingStatus {
  repository_id: string
  status: 'pending' | 'running' | 'completed' | 'error' | 'none'
  stage: string | null
  progress: number
  message: string | null
  chunks_processed: number
  vectors_stored: number
}

interface SemanticCacheData {
  analysis_id: string
  commit_sha: string
  architecture_health: {
    overall_score?: number  // New field
    score?: number  // Legacy field for backward compatibility
    clusters: Array<{
      id: number
      name: string
      file_count: number
      chunk_count: number
      cohesion: number
      top_files: string[]
      dominant_language: string | null
      status: string
    }>
    outliers: Array<{
      file_path: string
      chunk_name: string | null
      chunk_type: string | null
      nearest_similarity: number
      nearest_file: string | null
      suggestion: string
      confidence: number
      confidence_factors: string[]
      tier: string
    }>
    coupling_hotspots: Array<{
      file_path: string
      clusters_connected: number
      cluster_names: string[]
      suggestion: string
    }>
    total_chunks: number
    total_files: number
    metrics: Record<string, number>
  } | null
  computed_at: string | null
  is_cached: boolean
}

interface SemanticAnalysisSectionProps {
  repositoryId: string
  token?: string
}

type TabType = 'search' | 'architecture' | 'clusters' | 'duplicates' | 'debt'

const tabs: { id: TabType; label: string; description: string }[] = [
  { id: 'architecture', label: 'Architecture Health', description: 'Cluster analysis & outliers' },
  { id: 'search', label: 'Semantic Search', description: 'Search code with natural language' },
  { id: 'clusters', label: 'Cluster Map', description: 'Visual code organization' },
  { id: 'duplicates', label: 'Similar Code', description: 'Find potential duplicates' },
  { id: 'debt', label: 'Tech Debt', description: 'Technical debt heatmap' },
]

export function SemanticAnalysisSection({ repositoryId, token: initialToken }: SemanticAnalysisSectionProps) {
  const [activeTab, setActiveTab] = useState<TabType>('architecture')
  const [token, setToken] = useState<string>(initialToken || '')
  const [embeddingStatus, setEmbeddingStatus] = useState<EmbeddingStatus | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  
  // Semantic cache state
  const { selectedAnalysisId } = useCommitSelectionStore()
  const [semanticCache, setSemanticCache] = useState<SemanticCacheData | null>(null)
  const [cacheLoading, setCacheLoading] = useState(false)
  
  // Global progress store
  const { addTask, updateTask, hasTask, removeTask } = useAnalysisProgressStore()
  const taskId = getEmbeddingsTaskId(repositoryId)

  // Try to get token from localStorage as fallback
  useEffect(() => {
    if (!token) {
      const storedToken = localStorage.getItem('n9r_token')
      if (storedToken) {
        setToken(storedToken)
      }
    }
  }, [token])

  // Fetch semantic cache when selectedAnalysisId changes
  useEffect(() => {
    if (!selectedAnalysisId || !token) {
      setSemanticCache(null)
      return
    }

    const fetchSemanticCache = async () => {
      setCacheLoading(true)
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/analyses/${selectedAnalysisId}/semantic`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        )
        if (response.ok) {
          const data = await response.json()
          console.log('[SemanticAnalysis] Fetched cache:', {
            is_cached: data.is_cached,
            has_architecture_health: !!data.architecture_health,
            overall_score: data.architecture_health?.overall_score,
            total_chunks: data.architecture_health?.total_chunks,
          })
          setSemanticCache(data)
        } else {
          console.log('[SemanticAnalysis] Cache fetch failed:', response.status)
          setSemanticCache(null)
        }
      } catch (error) {
        console.error('[SemanticAnalysis] Failed to fetch semantic cache:', error)
        setSemanticCache(null)
      } finally {
        setCacheLoading(false)
      }
    }

    fetchSemanticCache()
  }, [selectedAnalysisId, token, refreshKey])

  // Poll for embedding status - use refs to avoid dependency issues
  const embeddingStatusRef = useRef<EmbeddingStatus | null>(null)
  const semanticCacheRef = useRef<SemanticCacheData | null>(null)
  // Track poll count to ignore stale 'completed' on first few polls when task exists
  const pollCountRef = useRef(0)
  
  // Keep refs in sync with state
  useEffect(() => {
    embeddingStatusRef.current = embeddingStatus
  }, [embeddingStatus])
  
  useEffect(() => {
    semanticCacheRef.current = semanticCache
  }, [semanticCache])

  // Poll while embeddings are being generated
  useEffect(() => {
    if (!token) return
    
    console.log('[SemanticAnalysis] Polling effect started for repo:', repositoryId, 'analysis:', selectedAnalysisId)
    
    // Reset refs when analysis changes to avoid stale data
    semanticCacheRef.current = null
    embeddingStatusRef.current = null
    
    let intervalId: NodeJS.Timeout | null = null
    let isMounted = true
    let currentInterval = 2000 // Start with faster polling to catch embeddings start
    // Reset poll count when effect restarts
    pollCountRef.current = 0
    
    const fetchStatus = async (): Promise<EmbeddingStatus | null> => {
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/repositories/${repositoryId}/embedding-status`,
          {
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          }
        )
        
        if (response.ok) {
          return await response.json()
        }
      } catch (error) {
        console.error('Failed to fetch embedding status:', error)
      }
      return null
    }
    
    const poll = async () => {
      if (!isMounted) return
      
      pollCountRef.current += 1
      const pollCount = pollCountRef.current
      
      const data = await fetchStatus()
      if (!isMounted || !data) {
        console.log('[SemanticAnalysis] Poll: no data or unmounted')
        return
      }
      
      const prev = embeddingStatusRef.current
      const wasInProgress = prev?.status === 'pending' || prev?.status === 'running'
      const isNowCompleted = data.status === 'completed'
      const isNowInProgress = data.status === 'pending' || data.status === 'running'
      const isNone = data.status === 'none'
      // Check task existence at call time to avoid stale closure
      const taskExists = hasTask(taskId)
      
      // Ignore stale 'completed' status on first few polls when task exists
      // This handles race condition where backend hasn't reset state yet
      // Use 5 polls (10 seconds at 2s interval) to give backend time to reset state
      const isStaleCompleted = isNowCompleted && taskExists && pollCount <= 5 && !wasInProgress
      
      // Debug logging
      console.log('[SemanticAnalysis] Poll result:', {
        status: data.status,
        stage: data.stage,
        progress: data.progress,
        vectors: data.vectors_stored,
        taskExists,
        wasInProgress,
        isNowInProgress,
        isNowCompleted,
        isStaleCompleted,
        pollCount,
      })
      
      // If this looks like stale completed status, wait for backend to reset
      if (isStaleCompleted) {
        console.log('[SemanticAnalysis] Ignoring stale completed status, waiting for backend reset...')
        // Keep task in waiting state
        if (taskExists) {
          updateTask(taskId, {
            status: 'pending',
            stage: 'waiting',
            message: 'Waiting for embeddings to start...',
          })
        }
        return // Don't process this poll, wait for next one
      }
      
      // Update local state
      setEmbeddingStatus(data)
      
      // Sync with global progress store
      if (isNowInProgress) {
        // Embeddings are actively running - update or create task
        if (taskExists) {
          updateTask(taskId, {
            status: data.status === 'pending' ? 'pending' : 'running',
            progress: data.progress || 0,
            stage: data.stage || 'embedding',
            message: data.message,
          })
        } else {
          addTask({
            id: taskId,
            type: 'embeddings',
            repositoryId,
            status: data.status === 'pending' ? 'pending' : 'running',
            progress: data.progress || 0,
            stage: data.stage || 'embedding',
            message: data.message,
          })
        }
      } else if (isNowCompleted) {
        // Embeddings are done - handle completion regardless of previous state
        // This fixes the race condition where we miss the "running" state
        console.log('[SemanticAnalysis] Embeddings completed:', {
          taskExists,
          wasInProgress,
          vectors: data.vectors_stored,
          cacheStatus: semanticCacheRef.current?.is_cached,
        })
        
        if (taskExists) {
          updateTask(taskId, { 
            status: 'completed', 
            progress: 100, 
            stage: 'completed', 
            message: `${data.vectors_stored} vectors available` 
          })
          setTimeout(() => {
            removeTask(taskId)
          }, 2000)
        } else if (wasInProgress) {
          // Task wasn't in store but we saw it running - show brief completion
          // This handles the case where polling missed adding the task
          addTask({
            id: taskId,
            type: 'embeddings',
            repositoryId,
            status: 'completed',
            progress: 100,
            stage: 'completed',
            message: `${data.vectors_stored} vectors generated`,
          })
          setTimeout(() => {
            removeTask(taskId)
          }, 3000)
        }
        
        // Always refresh semantic data when embeddings complete
        // Use a small delay to ensure backend has saved the cache
        // Check if we need to refresh:
        // - Cache must be loaded (not null) AND show is_cached: false
        // - OR we just saw embeddings complete (wasInProgress or taskExists)
        const cacheLoaded = semanticCacheRef.current !== null
        const cacheShowsNotCached = cacheLoaded && !semanticCacheRef.current?.is_cached
        const justCompleted = wasInProgress || taskExists
        const needsRefresh = cacheShowsNotCached || justCompleted
        
        console.log('[SemanticAnalysis] Cache refresh check:', {
          needsRefresh,
          cacheLoaded,
          cacheShowsNotCached,
          justCompleted,
          cacheRef: semanticCacheRef.current?.is_cached,
          vectors: data.vectors_stored,
        })
        
        if (needsRefresh) {
          console.log('[SemanticAnalysis] Triggering cache refresh after delay...')
          // Small delay to ensure backend has saved the semantic cache
          setTimeout(() => {
            console.log('[SemanticAnalysis] Executing cache refresh now')
            setRefreshKey(k => k + 1)
          }, 500)
        }
      } else if (isNone && taskExists) {
        // No embeddings exist yet but task was created by startAnalysis
        // Keep the task in "waiting" state - embeddings will start after analysis completes
        // Don't update the task here - it already has the right "waiting" message
      } else if (data.status === 'error') {
        if (taskExists) {
          updateTask(taskId, { status: 'failed', message: data.message })
          setTimeout(() => removeTask(taskId), 5000)
        }
      }
      
      // Stop polling when:
      // 1. Embeddings completed AND no task in store (task was removed after completion)
      // 2. Error status AND no task in store
      // 3. No embeddings ('none') AND no task waiting
      // Key: if taskExists, keep polling to track progress even if API shows old 'completed' status
      const shouldStopPolling = 
        (data.status === 'completed' && !taskExists) || 
        (data.status === 'error' && !taskExists) ||
        (data.status === 'none' && !taskExists)
      
      if (shouldStopPolling) {
        if (intervalId) {
          clearInterval(intervalId)
          intervalId = null
        }
        return
      }
      
      // Adjust polling interval based on status
      // Use faster polling when waiting for embeddings to start or when in progress
      // Also use fast polling on first few polls to catch the transition from completed to pending
      const shouldPollFast = isNowInProgress || (isNone && taskExists) || pollCount <= 5
      const newInterval = shouldPollFast ? 2000 : 10000
      if (newInterval !== currentInterval) {
        currentInterval = newInterval
        if (intervalId) clearInterval(intervalId)
        intervalId = setInterval(poll, currentInterval)
      }
    }
    
    // Initial fetch
    poll()
    
    // Start polling (will stop automatically when completed)
    intervalId = setInterval(poll, currentInterval)
    
    return () => {
      console.log('[SemanticAnalysis] Polling effect cleanup')
      isMounted = false
      if (intervalId) clearInterval(intervalId)
    }
  }, [token, repositoryId, taskId, selectedAnalysisId, addTask, updateTask, hasTask, removeTask])

  if (!token) {
    return (
      <Card className="glass-panel border-border/50">
        <CardContent className="p-6">
          <div className="text-center py-6">
            <div className="text-3xl mb-3">🔍</div>
            <h3 className="text-base font-semibold mb-2">Vector-Based Code Understanding</h3>
            <p className="text-sm text-muted-foreground mb-4 max-w-sm mx-auto">
              Uses AI embeddings to understand architecture, find patterns, and detect tech debt.
            </p>
            <div className="grid grid-cols-5 gap-2 max-w-md mx-auto text-xs">
              <div className="p-2 rounded-lg bg-background/50 border border-border/50">
                <div className="font-medium">Search</div>
              </div>
              <div className="p-2 rounded-lg bg-background/50 border border-border/50">
                <div className="font-medium">Clusters</div>
              </div>
              <div className="p-2 rounded-lg bg-background/50 border border-border/50">
                <div className="font-medium">Outliers</div>
              </div>
              <div className="p-2 rounded-lg bg-background/50 border border-border/50">
                <div className="font-medium">Duplicates</div>
              </div>
              <div className="p-2 rounded-lg bg-background/50 border border-border/50">
                <div className="font-medium">Debt</div>
              </div>
            </div>
            <p className="text-xs text-muted-foreground mt-3">
              Run an analysis to generate embeddings.
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Show loading state when fetching cache
  if (cacheLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-3 text-muted-foreground">Loading semantic analysis...</span>
      </div>
    )
  }

  // Show empty state if no analysis selected
  if (!selectedAnalysisId) {
    return (
      <Card className="glass-panel border-border/50">
        <CardContent className="p-6">
          <div className="text-center py-8 text-muted-foreground">
            <p className="text-sm">Select a commit to view semantic analysis</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Check if embeddings are being generated
  const isEmbeddingsInProgress = embeddingStatus?.status === 'pending' || embeddingStatus?.status === 'running'

  // Show spinner if cache is missing and embeddings are in progress
  if (semanticCache && !semanticCache.is_cached) {
    if (isEmbeddingsInProgress) {
      return (
        <Card className="glass-panel border-border/50">
          <CardContent className="p-6">
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
              <h3 className="text-base font-semibold mb-2">Generating Semantic Analysis</h3>
              <p className="text-sm text-muted-foreground text-center max-w-sm">
                {embeddingStatus?.message || 'Processing embeddings...'}
              </p>
              {embeddingStatus?.progress !== undefined && embeddingStatus.progress > 0 && (
                <p className="text-xs text-muted-foreground mt-2">
                  {Math.round(embeddingStatus.progress)}% complete
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )
    }

    return (
      <Card className="glass-panel border-border/50">
        <CardContent className="p-6">
          <div className="text-center py-8">
            <div className="text-3xl mb-3">🔍</div>
            <h3 className="text-base font-semibold mb-2">Semantic Analysis Not Generated</h3>
            <p className="text-sm text-muted-foreground max-w-sm mx-auto">
              Run an analysis to generate semantic data for this commit.
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div>
      {/* Tab Navigation */}
      <div className="flex flex-wrap gap-1.5 sm:gap-2 mb-3 sm:mb-4">
        {tabs.map((tab) => (
          <Button
            key={tab.id}
            variant={activeTab === tab.id ? 'default' : 'outline'}
            size="sm"
            onClick={() => setActiveTab(tab.id)}
            className="flex flex-col items-start h-auto py-1.5 sm:py-2 px-2 sm:px-4 text-xs sm:text-sm"
          >
            <span className="font-medium">{tab.label}</span>
            <span className="text-[10px] sm:text-xs opacity-70 hidden sm:block">{tab.description}</span>
          </Button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="min-h-[300px] sm:min-h-[400px]">
        {activeTab === 'search' && (
          <SemanticSearch
            key={`search-${refreshKey}`}
            repositoryId={repositoryId}
            token={token}
          />
        )}
        {activeTab === 'architecture' && (
          <ArchitectureHealth
            key={`arch-${refreshKey}-${selectedAnalysisId}`}
            repositoryId={repositoryId}
            token={token}
            cachedData={semanticCache?.architecture_health || undefined}
          />
        )}
        {activeTab === 'clusters' && (
          <ClusterMap
            key={`clusters-${refreshKey}`}
            repositoryId={repositoryId}
            token={token}
          />
        )}
        {activeTab === 'duplicates' && (
          <SimilarCode
            key={`similar-${refreshKey}`}
            repositoryId={repositoryId}
            token={token}
          />
        )}
        {activeTab === 'debt' && (
          <TechDebtHeatmap
            key={`debt-${refreshKey}`}
            repositoryId={repositoryId}
            token={token}
          />
        )}
      </div>
    </div>
  )
}

// Server wrapper component to pass token
export async function SemanticAnalysisSectionServer({ repositoryId }: { repositoryId: string }) {
  // This would be called from a server component
  // For now, we'll use the client component directly
  return <SemanticAnalysisSection repositoryId={repositoryId} />
}
