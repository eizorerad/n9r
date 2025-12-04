'use client'

import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { SemanticSearch } from '@/components/semantic-search'
import { ArchitectureHealth } from '@/components/architecture-health'
import { ClusterMap } from '@/components/cluster-map'
import { SimilarCode } from '@/components/similar-code'
import { TechDebtHeatmap } from '@/components/tech-debt-heatmap'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import { useAnalysisStatusWithStore } from '@/lib/hooks/use-analysis-status'
import { Loader2 } from 'lucide-react'

interface SemanticCacheData {
  analysis_id: string
  commit_sha: string
  architecture_health: {
    overall_score?: number
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
  const [refreshKey, setRefreshKey] = useState(0)
  
  // Semantic cache state
  const { selectedAnalysisId } = useCommitSelectionStore()
  const [semanticCache, setSemanticCache] = useState<SemanticCacheData | null>(null)
  const [cacheLoading, setCacheLoading] = useState(false)
  
  // Refs to prevent redundant operations
  const isRefreshingRef = useRef(false)
  const lastRefreshedCacheStatus = useRef<string | null>(null)
  const lastRefreshedEmbeddingsStatus = useRef<string | null>(null)

  // Use the new unified status hook with store sync
  // **Feature: progress-tracking-refactor**
  // **Validates: Requirements 4.1**
  const {
    data: analysisStatus,
    isLoading: statusLoading,
  } = useAnalysisStatusWithStore({
    analysisId: selectedAnalysisId,
    repositoryId,
    token,
    enabled: !!token && !!selectedAnalysisId,
  })
  
  // Memoize derived status values to prevent object reference changes from triggering effects
  const derivedStatus = useMemo(() => {
    if (!analysisStatus) return null
    return {
      semanticCacheStatus: analysisStatus.semantic_cache_status,
      hasSemanticCache: analysisStatus.has_semantic_cache,
      embeddingsStatus: analysisStatus.embeddings_status,
      vectorsCount: analysisStatus.vectors_count,
    }
  }, [
    analysisStatus?.semantic_cache_status,
    analysisStatus?.has_semantic_cache,
    analysisStatus?.embeddings_status,
    analysisStatus?.vectors_count,
  ])

  // Try to get token from localStorage as fallback
  useEffect(() => {
    if (!token) {
      const storedToken = localStorage.getItem('n9r_token')
      if (storedToken) {
        setToken(storedToken)
      }
    }
  }, [token])

  // Stable fetch function with useCallback
  const fetchSemanticCache = useCallback(async () => {
    if (!selectedAnalysisId || !token || isRefreshingRef.current) {
      return
    }

    isRefreshingRef.current = true
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
      isRefreshingRef.current = false
    }
  }, [selectedAnalysisId, token])

  // Fetch semantic cache when selectedAnalysisId changes or refreshKey updates
  useEffect(() => {
    if (!selectedAnalysisId || !token) {
      setSemanticCache(null)
      lastRefreshedCacheStatus.current = null
      lastRefreshedEmbeddingsStatus.current = null
      return
    }

    fetchSemanticCache()
  }, [selectedAnalysisId, token, refreshKey, fetchSemanticCache])

  // Refresh semantic cache when status changes (using derived values to prevent loops)
  useEffect(() => {
    if (!derivedStatus || isRefreshingRef.current) return

    const isCached = semanticCache?.is_cached || false
    
    // Only trigger refresh if status changed AND cache is not yet available
    // Refresh when semantic cache status becomes completed
    if (
      derivedStatus.semanticCacheStatus === 'completed' &&
      derivedStatus.hasSemanticCache &&
      !isCached &&
      lastRefreshedCacheStatus.current !== 'completed'
    ) {
      console.log('[SemanticAnalysis] Semantic cache completed, refreshing...')
      lastRefreshedCacheStatus.current = 'completed'
      setRefreshKey(k => k + 1)
      return
    }
    
    // Refresh when embeddings complete (one-time only)
    if (
      derivedStatus.embeddingsStatus === 'completed' &&
      derivedStatus.vectorsCount > 0 &&
      !isCached &&
      lastRefreshedEmbeddingsStatus.current !== 'completed'
    ) {
      console.log('[SemanticAnalysis] Embeddings completed, refreshing cache...')
      lastRefreshedEmbeddingsStatus.current = 'completed'
      // Single refresh after embeddings, no timer needed
      setRefreshKey(k => k + 1)
    }
  }, [
    derivedStatus?.semanticCacheStatus,
    derivedStatus?.hasSemanticCache,
    derivedStatus?.embeddingsStatus,
    derivedStatus?.vectorsCount,
    semanticCache?.is_cached,
  ])

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

  // Show loading state when fetching cache or initial status
  if (cacheLoading || (statusLoading && !semanticCache)) {
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

  // Determine if embeddings are in progress from the unified status
  const isEmbeddingsInProgress = 
    analysisStatus?.embeddings_status === 'pending' || 
    analysisStatus?.embeddings_status === 'running'
  
  const isSemanticCacheComputing = 
    analysisStatus?.semantic_cache_status === 'pending' ||
    analysisStatus?.semantic_cache_status === 'computing'

  // Show progress if cache is missing and processing is in progress
  if (semanticCache && !semanticCache.is_cached) {
    if (isEmbeddingsInProgress || isSemanticCacheComputing) {
      const progressMessage = isSemanticCacheComputing 
        ? 'Computing semantic analysis...'
        : analysisStatus?.embeddings_message || 'Processing embeddings...'
      
      const progressPercent = isSemanticCacheComputing
        ? 95  // Semantic cache is near the end
        : analysisStatus?.embeddings_progress || 0

      return (
        <Card className="glass-panel border-border/50">
          <CardContent className="p-6">
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
              <h3 className="text-base font-semibold mb-2">Generating Semantic Analysis</h3>
              <p className="text-sm text-muted-foreground text-center max-w-sm">
                {progressMessage}
              </p>
              {progressPercent > 0 && (
                <p className="text-xs text-muted-foreground mt-2">
                  {Math.round(progressPercent)}% complete
                </p>
              )}
              {analysisStatus?.embeddings_stage && (
                <p className="text-xs text-muted-foreground mt-1">
                  Stage: {analysisStatus.embeddings_stage}
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
