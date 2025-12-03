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
import { Loader2, Sparkles } from 'lucide-react'

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
    overall_score: number
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
  const [generating, setGenerating] = useState(false)
  
  // Global progress store
  const { addTask, updateTask, hasTask } = useAnalysisProgressStore()
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

  // Generate semantic cache
  const handleGenerateCache = async () => {
    if (!selectedAnalysisId || !token) return

    setGenerating(true)
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/analyses/${selectedAnalysisId}/semantic/generate`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        }
      )
      if (response.ok) {
        const data = await response.json()
        setSemanticCache(data)
      }
    } catch (error) {
      console.error('Failed to generate semantic cache:', error)
    } finally {
      setGenerating(false)
    }
  }

  // Poll for embedding status - use ref to avoid dependency issues
  const embeddingStatusRef = useRef<EmbeddingStatus | null>(null)
  
  // Keep ref in sync with state
  useEffect(() => {
    embeddingStatusRef.current = embeddingStatus
  }, [embeddingStatus])

  // Poll while embeddings are being generated
  useEffect(() => {
    if (!token) return
    
    let intervalId: NodeJS.Timeout | null = null
    let isMounted = true
    let currentInterval = 5000 // Start with moderate polling
    
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
      
      const data = await fetchStatus()
      if (!isMounted || !data) return
      
      const prev = embeddingStatusRef.current
      const wasInProgress = prev?.status === 'pending' || prev?.status === 'running'
      const isNowCompleted = data.status === 'completed' && data.vectors_stored > 0
      const isNowInProgress = data.status === 'pending' || data.status === 'running'
      
      // Update local state
      setEmbeddingStatus(data)
      
      // Sync with global progress store
      if (isNowInProgress) {
        const taskExists = hasTask(taskId)
        if (taskExists) {
          updateTask(taskId, {
            status: data.status === 'pending' ? 'pending' : 'running',
            progress: data.progress,
            stage: data.stage || 'embedding',
            message: data.message,
          })
        } else {
          addTask({
            id: taskId,
            type: 'embeddings',
            repositoryId,
            status: data.status === 'pending' ? 'pending' : 'running',
            progress: data.progress,
            stage: data.stage || 'embedding',
            message: data.message,
          })
        }
      } else if (wasInProgress && isNowCompleted) {
        updateTask(taskId, { status: 'completed', progress: 100 })
        setTimeout(() => setRefreshKey(k => k + 1), 500)
      } else if (prev?.status !== 'error' && data.status === 'error') {
        updateTask(taskId, { status: 'failed', message: data.message })
      }
      
      // Adjust polling interval based on status
      const newInterval = isNowInProgress ? 3000 : 15000
      if (newInterval !== currentInterval) {
        currentInterval = newInterval
        if (intervalId) clearInterval(intervalId)
        intervalId = setInterval(poll, currentInterval)
      }
    }
    
    // Initial fetch
    poll()
    
    // Start polling
    intervalId = setInterval(poll, currentInterval)
    
    return () => {
      isMounted = false
      if (intervalId) clearInterval(intervalId)
    }
  }, [token, repositoryId, taskId, addTask, updateTask, hasTask])

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

  // Show generate button if cache is missing
  if (semanticCache && !semanticCache.is_cached) {
    return (
      <Card className="glass-panel border-border/50">
        <CardContent className="p-6">
          <div className="text-center py-8">
            <div className="text-3xl mb-3">🔍</div>
            <h3 className="text-base font-semibold mb-2">Semantic Analysis Not Generated</h3>
            <p className="text-sm text-muted-foreground mb-4 max-w-sm mx-auto">
              Generate semantic analysis to view architecture health, clusters, and outliers for this commit.
            </p>
            <Button
              onClick={handleGenerateCache}
              disabled={generating}
              className="gap-2"
            >
              {generating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Generate Semantic Analysis
                </>
              )}
            </Button>
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
