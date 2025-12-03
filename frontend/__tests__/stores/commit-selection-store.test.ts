/**
 * Property-Based Tests for CommitSelectionStore
 * 
 * **Feature: commit-centric-dashboard, Property 1: Selected commit determines displayed data**
 * **Validates: Requirements 1.1, 1.2**
 */

import { describe, it, expect, beforeEach } from 'vitest'
import * as fc from 'fast-check'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'

// Arbitrary generators for test data
const hexChar = fc.constantFrom(...'0123456789abcdef'.split(''))
const commitShaArb = fc.array(hexChar, { minLength: 40, maxLength: 40 }).map(arr => arr.join(''))
const analysisIdArb = fc.uuid()
const repositoryIdArb = fc.uuid()

describe('CommitSelectionStore - Property 1: Selected commit determines displayed data', () => {
  beforeEach(() => {
    // Reset the store before each test
    useCommitSelectionStore.getState().clearSelection()
  })

  /**
   * **Feature: commit-centric-dashboard, Property 1: Selected commit determines displayed data**
   * **Validates: Requirements 1.1, 1.2**
   * 
   * Property: For any commit selection, the store state SHALL contain the exact
   * commit SHA and analysis ID that was set, ensuring all panels can access
   * consistent data.
   */
  it('should maintain exact commit SHA and analysis ID after selection', () => {
    fc.assert(
      fc.property(commitShaArb, analysisIdArb, repositoryIdArb, (sha, analysisId, repoId) => {
        // Set the selection
        useCommitSelectionStore.getState().setSelectedCommit(sha, analysisId, repoId)
        
        // Get the current state
        const state = useCommitSelectionStore.getState()
        
        // The store MUST contain the exact values that were set
        expect(state.selectedCommitSha).toBe(sha)
        expect(state.selectedAnalysisId).toBe(analysisId)
        expect(state.repositoryId).toBe(repoId)
      }),
      { numRuns: 100 }
    )
  })

  /**
   * Property: For any commit selection with null analysisId (unanalyzed commit),
   * the store SHALL correctly represent this state so panels can show empty states.
   */
  it('should handle commits without analysis (null analysisId)', () => {
    fc.assert(
      fc.property(commitShaArb, repositoryIdArb, (sha, repoId) => {
        // Set selection with null analysisId (commit not yet analyzed)
        useCommitSelectionStore.getState().setSelectedCommit(sha, null, repoId)
        
        const state = useCommitSelectionStore.getState()
        
        // SHA should be set, but analysisId should be null
        expect(state.selectedCommitSha).toBe(sha)
        expect(state.selectedAnalysisId).toBeNull()
        expect(state.hasSelection()).toBe(true)
      }),
      { numRuns: 100 }
    )
  })

  /**
   * Property: The isCommitSelected helper SHALL return true only for the
   * currently selected commit SHA.
   */
  it('should correctly identify selected commit via isCommitSelected', () => {
    fc.assert(
      fc.property(commitShaArb, commitShaArb, analysisIdArb, (selectedSha, otherSha, analysisId) => {
        // Set a commit as selected
        useCommitSelectionStore.getState().setSelectedCommit(selectedSha, analysisId)
        
        const state = useCommitSelectionStore.getState()
        
        // isCommitSelected should return true for the selected SHA
        expect(state.isCommitSelected(selectedSha)).toBe(true)
        
        // For a different SHA, it should return false (unless they happen to be equal)
        if (selectedSha !== otherSha) {
          expect(state.isCommitSelected(otherSha)).toBe(false)
        }
      }),
      { numRuns: 100 }
    )
  })

  /**
   * Property: After clearSelection, the store SHALL have no selection,
   * ensuring panels show appropriate empty/default states.
   */
  it('should clear all selection state on clearSelection', () => {
    fc.assert(
      fc.property(commitShaArb, analysisIdArb, repositoryIdArb, (sha, analysisId, repoId) => {
        // First set a selection
        useCommitSelectionStore.getState().setSelectedCommit(sha, analysisId, repoId)
        
        // Verify it was set
        expect(useCommitSelectionStore.getState().hasSelection()).toBe(true)
        
        // Clear the selection
        useCommitSelectionStore.getState().clearSelection()
        
        const state = useCommitSelectionStore.getState()
        
        // All selection state should be null
        expect(state.selectedCommitSha).toBeNull()
        expect(state.selectedAnalysisId).toBeNull()
        expect(state.repositoryId).toBeNull()
        expect(state.hasSelection()).toBe(false)
      }),
      { numRuns: 100 }
    )
  })

  /**
   * Property: Multiple sequential selections SHALL always result in the
   * store containing only the most recent selection.
   */
  it('should always reflect the most recent selection after multiple updates', () => {
    const selectionArb = fc.tuple(commitShaArb, fc.option(analysisIdArb, { nil: null }), repositoryIdArb)
    
    fc.assert(
      fc.property(
        fc.array(selectionArb, { minLength: 1, maxLength: 10 }),
        (selections) => {
          // Apply all selections sequentially
          for (const [sha, analysisId, repoId] of selections) {
            useCommitSelectionStore.getState().setSelectedCommit(sha, analysisId, repoId)
          }
          
          // Get the last selection
          const [lastSha, lastAnalysisId, lastRepoId] = selections[selections.length - 1]
          const state = useCommitSelectionStore.getState()
          
          // Store should contain exactly the last selection
          expect(state.selectedCommitSha).toBe(lastSha)
          expect(state.selectedAnalysisId).toBe(lastAnalysisId)
          expect(state.repositoryId).toBe(lastRepoId)
        }
      ),
      { numRuns: 100 }
    )
  })
})
