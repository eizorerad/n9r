'use client'

import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { SemanticSearch } from '@/components/semantic-search'
import { ArchitectureHealth } from '@/components/architecture-health'
import { ClusterMap } from '@/components/cluster-map'
import { SimilarCode } from '@/components/similar-code'
import { TechDebtHeatmap } from '@/components/tech-debt-heatmap'
import { useAnalysisProgressStore, getEmbeddingsTaskId } from '@/lib/stores/analysis-progress-store'

interface EmbeddingStatus {
  repository_id: string
  status: 'pending' | 'running' | 'completed' | 'error' | 'none'
  stage: string | null
  progress: number
  message: string | null
  chunks_processed: number
  vectors_stored: number
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
  
  // Global progress store
  const { addTask, updateTask } = useAnalysisProgressStore()
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

  // Poll for embedding status
  const fetchEmbeddingStatus = useCallback(async () => {
    if (!token) return null
    
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
        const data: EmbeddingStatus = await response.json()
        
        console.log('[SemanticAnalysis] Polling status:', data.status, 'progress:', data.progress)
        
        // If embeddings just completed (status changed to completed), trigger a refresh
        setEmbeddingStatus(prev => {
          const wasInProgress = prev?.status === 'pending' || prev?.status === 'running'
          const isNowCompleted = data.status === 'completed' && data.vectors_stored > 0
          const isNowInProgress = data.status === 'pending' || data.status === 'running'
          
          console.log('[SemanticAnalysis] prev:', prev?.status, 'wasInProgress:', wasInProgress, 'isNowInProgress:', isNowInProgress)
          
          // Sync with global progress store
          if (isNowInProgress) {
            // Embeddings in progress - add or update task
            console.log('[SemanticAnalysis] Adding/updating embeddings task')
            addTask({
              id: taskId,
              type: 'embeddings',
              repositoryId,
              status: data.status === 'pending' ? 'pending' : 'running',
              progress: data.progress,
              stage: data.stage || 'embedding',
              message: data.message,
            })
          } else if (wasInProgress && isNowCompleted) {
            // Completed - update store and trigger refresh
            console.log('[SemanticAnalysis] Embeddings completed!')
            updateTask(taskId, { status: 'completed', progress: 100 })
            setTimeout(() => setRefreshKey(k => k + 1), 500)
          } else if (prev?.status !== 'error' && data.status === 'error') {
            // Failed
            updateTask(taskId, { status: 'failed', message: data.message })
          }
          
          return data
        })
        
        return data
      }
    } catch (error) {
      console.error('Failed to fetch embedding status:', error)
    }
    return null
  }, [repositoryId, token, addTask, updateTask, taskId])

  // Poll while embeddings are being generated
  useEffect(() => {
    if (!token) return
    
    // Initial fetch
    fetchEmbeddingStatus()
    
    // Set up polling - faster when in progress, slower when idle
    let intervalId: NodeJS.Timeout
    let lastStatus: string | undefined
    
    const poll = async () => {
      const status = await fetchEmbeddingStatus()
      const newStatus = status?.status
      
      // Adjust polling rate based on status change
      if (newStatus !== lastStatus) {
        lastStatus = newStatus
        clearInterval(intervalId)
        const interval = (newStatus === 'running' || newStatus === 'pending') 
          ? 2000  // Fast polling when in progress
          : 10000 // Slow polling when idle
        
        intervalId = setInterval(poll, interval)
      }
    }
    
    // Start with fast polling
    intervalId = setInterval(poll, 3000)
    
    return () => {
      if (intervalId) clearInterval(intervalId)
    }
  }, [token, fetchEmbeddingStatus])

  // Check if embeddings are in progress
  const isEmbeddingInProgress = embeddingStatus?.status === 'running' || embeddingStatus?.status === 'pending'

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
            key={`arch-${refreshKey}`}
            repositoryId={repositoryId}
            token={token}
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
