import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

interface CommitSelectionState {
  selectedCommitSha: string | null
  selectedAnalysisId: string | null
  repositoryId: string | null
  
  // Actions
  setSelectedCommit: (sha: string, analysisId: string | null, repositoryId?: string) => void
  clearSelection: () => void
  
  // Computed helpers
  hasSelection: () => boolean
  isCommitSelected: (sha: string) => boolean
}

export const useCommitSelectionStore = create<CommitSelectionState>()(
  persist(
    (set, get) => ({
      selectedCommitSha: null,
      selectedAnalysisId: null,
      repositoryId: null,
      
      setSelectedCommit: (sha, analysisId, repositoryId) => {
        set({
          selectedCommitSha: sha,
          selectedAnalysisId: analysisId,
          ...(repositoryId !== undefined && { repositoryId }),
        })
      },
      
      clearSelection: () => {
        set({
          selectedCommitSha: null,
          selectedAnalysisId: null,
          repositoryId: null,
        })
      },
      
      hasSelection: () => {
        const { selectedCommitSha } = get()
        return selectedCommitSha !== null
      },
      
      isCommitSelected: (sha) => {
        const { selectedCommitSha } = get()
        return selectedCommitSha === sha
      },
    }),
    {
      name: 'commit-selection',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        selectedCommitSha: state.selectedCommitSha,
        selectedAnalysisId: state.selectedAnalysisId,
        repositoryId: state.repositoryId,
      }),
    }
  )
)
