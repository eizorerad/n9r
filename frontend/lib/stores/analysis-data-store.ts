import { create } from 'zustand'

interface Issue {
  id: string
  type: string
  severity: 'high' | 'medium' | 'low'
  title: string
  description: string
  file_path: string | null
  line_start: number | null
  confidence: number
  status: string
  auto_fixable: boolean
}

interface AnalysisData {
  id: string
  vci_score: number | null
  grade: string | null
  commit_sha: string
  completed_at: string | null
  created_at: string
  status: string
  tech_debt_level: string | null
  metrics: Record<string, unknown> | null
  issues: Issue[]
  ai_report: string | null
}

interface AnalysisDataState {
  // Data
  analysisData: AnalysisData | null
  loading: boolean
  error: string | null
  currentAnalysisId: string | null
  
  // Actions
  fetchAnalysis: (analysisId: string, token: string) => Promise<void>
  clearAnalysis: () => void
  invalidateAnalysis: (analysisId: string) => void
  
  // Prevent duplicate fetches
  _fetchPromise: Promise<void> | null
}

function getGrade(score: number | null): string | null {
  if (score === null) return null
  if (score >= 90) return 'A'
  if (score >= 80) return 'B'
  if (score >= 70) return 'C'
  if (score >= 60) return 'D'
  return 'F'
}

export const useAnalysisDataStore = create<AnalysisDataState>()((set, get) => ({
  analysisData: null,
  loading: false,
  error: null,
  currentAnalysisId: null,
  _fetchPromise: null,

  fetchAnalysis: async (analysisId: string, token: string) => {
    const state = get()
    
    // If already fetching this analysis, return existing promise
    if (state.currentAnalysisId === analysisId && state._fetchPromise) {
      return state._fetchPromise
    }
    
    // Only use cache if analysis is completed - otherwise always re-fetch
    // This ensures we get updated data when analysis finishes
    if (
      state.currentAnalysisId === analysisId && 
      state.analysisData && 
      !state.error &&
      state.analysisData.status === 'completed'
    ) {
      // Ensure loading is false when returning cached data
      // This fixes the lag when switching to Static Analysis tab
      if (state.loading) {
        set({ loading: false })
      }
      return
    }

    const fetchPromise = (async () => {
      set({ loading: true, error: null, currentAnalysisId: analysisId })
      
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/analyses/${analysisId}`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        )
        
        if (!response.ok) {
          // Handle 401 - session expired, redirect to login
          if (response.status === 401 && typeof window !== "undefined") {
            window.location.href = "/login?error=session_expired"
            throw new Error('Session expired. Please log in again.')
          }
          throw new Error('Failed to fetch analysis')
        }
        
        const data = await response.json()
        
        console.log('[AnalysisDataStore] Fetched analysis data:', {
          analysisId,
          status: data.status,
          vci_score: data.vci_score,
          grade: data.grade,
          hasMetrics: !!data.metrics,
        })
        
        // Only update if this is still the current request
        if (get().currentAnalysisId === analysisId) {
          set({
            analysisData: {
              ...data,
              grade: data.grade || getGrade(data.vci_score),
            },
            loading: false,
            error: null,
            _fetchPromise: null,
          })
        }
      } catch (err) {
        // Only update if this is still the current request
        if (get().currentAnalysisId === analysisId) {
          set({
            analysisData: null,
            loading: false,
            error: err instanceof Error ? err.message : 'Failed to load analysis',
            _fetchPromise: null,
          })
        }
      }
    })()

    set({ _fetchPromise: fetchPromise })
    return fetchPromise
  },

  clearAnalysis: () => {
    set({
      analysisData: null,
      loading: false,
      error: null,
      currentAnalysisId: null,
      _fetchPromise: null,
    })
  },

  // Invalidate cache for a specific analysis to force re-fetch
  invalidateAnalysis: (analysisId: string) => {
    const state = get()
    if (state.currentAnalysisId === analysisId) {
      set({
        analysisData: null,
        _fetchPromise: null,
      })
    }
  },
}))
