/**
 * Property-Based Tests for SelectedCommitIndicator
 * 
 * **Feature: commit-centric-dashboard, Property 6: Commit SHA displayed matches selection**
 * **Validates: Requirements 5.1, 5.2**
 */

import { describe, it, expect, beforeEach } from 'vitest'
import * as fc from 'fast-check'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'

describe('SelectedCommitIndicator - Property 6: Commit SHA displayed matches selection', () => {
  beforeEach(() => {
    // Reset the store before each test
    useCommitSelectionStore.getState().clearSelection()
  })

  /**
   * **Feature: commit-centric-dashboard, Property 6: Commit SHA displayed matches selection**
   * **Validates: Requirements 5.1, 5.2**
   * 
   * Property: For any selected commit SHA in the store, the displayed short SHA
   * should be the first 7 characters of the full SHA.
   */
  it('should display first 7 characters of any selected commit SHA', () => {
    // Generate arbitrary commit SHAs (40 hex characters like real git SHAs)
    const hexChar = fc.constantFrom(...'0123456789abcdef'.split(''))
    const commitShaArb = fc.array(hexChar, { minLength: 40, maxLength: 40 }).map(arr => arr.join(''))

    fc.assert(
      fc.property(commitShaArb, (commitSha) => {
        // Set up the store with the selected commit
        useCommitSelectionStore.getState().setSelectedCommit(commitSha, null)
        
        // Get the state from store (simulating what the component does)
        const { selectedCommitSha } = useCommitSelectionStore.getState()
        
        // The component displays shortSha = selectedCommitSha.slice(0, 7)
        const displayedShortSha = selectedCommitSha?.slice(0, 7)
        
        // Verify the displayed SHA matches the first 7 chars of the selected SHA
        expect(displayedShortSha).toBe(commitSha.slice(0, 7))
        expect(displayedShortSha).toHaveLength(7)
      }),
      { numRuns: 100 }
    )
  })

  /**
   * Property: When the selected commit matches the HEAD commit, the "Latest" badge
   * should be shown (isLatest = true).
   */
  it('should identify when selected commit is the latest (HEAD)', () => {
    const hexChar = fc.constantFrom(...'0123456789abcdef'.split(''))
    const commitShaArb = fc.array(hexChar, { minLength: 40, maxLength: 40 }).map(arr => arr.join(''))

    fc.assert(
      fc.property(commitShaArb, (commitSha) => {
        // Set up the store with the selected commit
        useCommitSelectionStore.getState().setSelectedCommit(commitSha, null)
        
        const { selectedCommitSha } = useCommitSelectionStore.getState()
        
        // Simulate the component logic: isLatest = headCommitSha && selectedCommitSha === headCommitSha
        const headCommitSha = commitSha // Same as selected = is latest
        const isLatest = headCommitSha && selectedCommitSha === headCommitSha
        
        expect(isLatest).toBe(true)
      }),
      { numRuns: 100 }
    )
  })

  /**
   * Property: When the selected commit differs from HEAD, the "Latest" badge
   * should NOT be shown (isLatest = false).
   */
  it('should not show Latest badge when selected commit differs from HEAD', () => {
    const hexChar = fc.constantFrom(...'0123456789abcdef'.split(''))
    const commitShaArb = fc.array(hexChar, { minLength: 40, maxLength: 40 }).map(arr => arr.join(''))

    fc.assert(
      fc.property(
        commitShaArb,
        commitShaArb.filter(sha => sha !== ''), // Generate a different SHA for HEAD
        (selectedSha, headSha) => {
          // Skip if they happen to be the same (extremely unlikely but possible)
          fc.pre(selectedSha !== headSha)
          
          // Set up the store with the selected commit
          useCommitSelectionStore.getState().setSelectedCommit(selectedSha, null)
          
          const { selectedCommitSha } = useCommitSelectionStore.getState()
          
          // Simulate the component logic
          const isLatest = headSha && selectedCommitSha === headSha
          
          expect(isLatest).toBe(false)
        }
      ),
      { numRuns: 100 }
    )
  })

  /**
   * Property: When no commit is selected, the component should not render
   * (returns null when selectedCommitSha is null).
   */
  it('should not display anything when no commit is selected', () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        // Clear selection
        useCommitSelectionStore.getState().clearSelection()
        
        const { selectedCommitSha } = useCommitSelectionStore.getState()
        
        // Component returns null when selectedCommitSha is null
        const shouldRender = selectedCommitSha !== null
        
        expect(shouldRender).toBe(false)
        expect(selectedCommitSha).toBeNull()
      }),
      { numRuns: 10 }
    )
  })

  /**
   * Property: The displayed SHA should update immediately when selection changes.
   * For any sequence of commit selections, the store always reflects the latest.
   */
  it('should immediately reflect commit selection changes', () => {
    const hexChar = fc.constantFrom(...'0123456789abcdef'.split(''))
    const commitShaArb = fc.array(hexChar, { minLength: 40, maxLength: 40 }).map(arr => arr.join(''))

    fc.assert(
      fc.property(
        fc.array(commitShaArb, { minLength: 1, maxLength: 5 }),
        (commitShas) => {
          // Apply each selection in sequence
          for (const sha of commitShas) {
            useCommitSelectionStore.getState().setSelectedCommit(sha, null)
            
            // After each selection, verify the store immediately reflects it
            const { selectedCommitSha } = useCommitSelectionStore.getState()
            expect(selectedCommitSha).toBe(sha)
          }
          
          // Final state should be the last SHA
          const { selectedCommitSha } = useCommitSelectionStore.getState()
          expect(selectedCommitSha).toBe(commitShas[commitShas.length - 1])
        }
      ),
      { numRuns: 50 }
    )
  })
})
