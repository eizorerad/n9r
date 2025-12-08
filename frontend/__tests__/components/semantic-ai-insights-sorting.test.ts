/**
 * Property-Based Tests for SemanticAIInsights Sorting
 * 
 * **Feature: transparent-scoring-formula, Property 7: UI Sorting Options**
 * **Validates: Requirements 7.2, 7.3, 7.4**
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { sortFindings, SortOption } from '@/components/semantic-ai-insights'
import type {
  SemanticAIInsight,
  DeadCodeFinding,
  HotSpotFinding,
} from '@/lib/hooks/use-architecture-findings'

// Type definition matching the component's FindingItem
type FindingItem = {
  type: 'insight' | 'dead_code' | 'hot_spot'
  data: SemanticAIInsight | DeadCodeFinding | HotSpotFinding
}

// Arbitrary generators for test data
const priorityArb = fc.constantFrom<'high' | 'medium' | 'low'>('high', 'medium', 'low')
const insightTypeArb = fc.constantFrom<'dead_code' | 'hot_spot' | 'architecture'>('dead_code', 'hot_spot', 'architecture')
const filePathArb = fc.string({ minLength: 5, maxLength: 50 }).map(s => 
  s.replace(/[^a-z/._-]/gi, 'x') || 'default/path.ts'
)
// Use constant date string - dates aren't relevant to sorting tests
const isoDateArb = fc.constant('2024-01-15T12:00:00.000Z')

const insightArb: fc.Arbitrary<SemanticAIInsight> = fc.record({
  id: fc.uuid(),
  insight_type: insightTypeArb,
  title: fc.string({ minLength: 1, maxLength: 50 }),
  description: fc.string({ minLength: 1, maxLength: 200 }),
  priority: priorityArb,
  affected_files: fc.array(filePathArb, { minLength: 0, maxLength: 5 }),
  evidence: fc.option(fc.string({ minLength: 1, maxLength: 100 }), { nil: null }),
  suggested_action: fc.option(fc.string({ minLength: 1, maxLength: 100 }), { nil: null }),
  is_dismissed: fc.boolean(),
  dismissed_at: fc.option(isoDateArb, { nil: null }),
  created_at: isoDateArb,
})

const deadCodeFindingArb: fc.Arbitrary<DeadCodeFinding> = fc.record({
  id: fc.uuid(),
  file_path: filePathArb,
  function_name: fc.string({ minLength: 1, maxLength: 30 }),
  line_start: fc.integer({ min: 1, max: 1000 }),
  line_end: fc.integer({ min: 1, max: 1000 }),
  line_count: fc.integer({ min: 1, max: 500 }),
  confidence: fc.double({ min: 0, max: 1, noNaN: true }),
  evidence: fc.string({ minLength: 1, maxLength: 100 }),
  suggested_action: fc.string({ minLength: 1, maxLength: 100 }),
  is_dismissed: fc.boolean(),
  dismissed_at: fc.option(isoDateArb, { nil: null }),
  created_at: isoDateArb,
  impact_score: fc.double({ min: 0, max: 100, noNaN: true }),
})

const hotSpotFindingArb: fc.Arbitrary<HotSpotFinding> = fc.record({
  id: fc.uuid(),
  file_path: filePathArb,
  changes_90d: fc.integer({ min: 1, max: 100 }),
  coverage_rate: fc.option(fc.double({ min: 0, max: 1, noNaN: true }), { nil: null }),
  unique_authors: fc.integer({ min: 1, max: 20 }),
  risk_factors: fc.array(fc.string({ minLength: 1, maxLength: 50 }), { minLength: 0, maxLength: 5 }),
  suggested_action: fc.option(fc.string({ minLength: 1, maxLength: 100 }), { nil: null }),
  created_at: isoDateArb,
  risk_score: fc.double({ min: 0, max: 100, noNaN: true }),
})

// Generator for finding items
const findingItemArb: fc.Arbitrary<FindingItem> = fc.oneof(
  insightArb.map(data => ({ type: 'insight' as const, data })),
  deadCodeFindingArb.map(data => ({ type: 'dead_code' as const, data })),
  hotSpotFindingArb.map(data => ({ type: 'hot_spot' as const, data }))
)

// Helper to get score from item (matching component logic)
function getItemScore(item: FindingItem): number {
  if (item.type === 'dead_code') {
    return (item.data as DeadCodeFinding).impact_score
  } else if (item.type === 'hot_spot') {
    return (item.data as HotSpotFinding).risk_score
  } else {
    const insight = item.data as SemanticAIInsight
    return insight.priority === 'high' ? 90 : insight.priority === 'medium' ? 60 : 30
  }
}

// Helper to get file path from item (matching component logic)
function getItemFilePath(item: FindingItem): string {
  if (item.type === 'dead_code') {
    return (item.data as DeadCodeFinding).file_path
  } else if (item.type === 'hot_spot') {
    return (item.data as HotSpotFinding).file_path
  } else {
    const insight = item.data as SemanticAIInsight
    return insight.affected_files[0] ?? ''
  }
}

describe('SemanticAIInsights Sorting - Property 7: UI Sorting Options', () => {
  /**
   * **Feature: transparent-scoring-formula, Property 7: UI Sorting Options**
   * **Validates: Requirements 7.2**
   * 
   * Property: When sorting by "score", findings SHALL be ordered by 
   * impact_score/risk_score in descending order (highest score first).
   */
  it('should sort by score in descending order', () => {
    fc.assert(
      fc.property(
        fc.array(findingItemArb, { minLength: 1, maxLength: 20 }),
        (items) => {
          const sorted = sortFindings(items, 'score')
          
          // Verify descending order by score
          for (let i = 0; i < sorted.length - 1; i++) {
            const currentScore = getItemScore(sorted[i])
            const nextScore = getItemScore(sorted[i + 1])
            expect(currentScore).toBeGreaterThanOrEqual(nextScore)
          }
          
          // Verify all original items are present
          expect(sorted.length).toBe(items.length)
        }
      ),
      { numRuns: 100 }
    )
  })

  /**
   * **Feature: transparent-scoring-formula, Property 7: UI Sorting Options**
   * **Validates: Requirements 7.3**
   * 
   * Property: When sorting by "type", findings SHALL be grouped by insight_type
   * (insights first, then hot_spots, then dead_code).
   */
  it('should group by type in correct order', () => {
    fc.assert(
      fc.property(
        fc.array(findingItemArb, { minLength: 1, maxLength: 20 }),
        (items) => {
          const sorted = sortFindings(items, 'type')
          
          // Find the boundaries between types
          let lastInsightIdx = -1
          let lastHotSpotIdx = -1
          let firstDeadCodeIdx = sorted.length
          
          sorted.forEach((item, idx) => {
            if (item.type === 'insight') lastInsightIdx = idx
            if (item.type === 'hot_spot') lastHotSpotIdx = idx
            if (item.type === 'dead_code' && firstDeadCodeIdx === sorted.length) {
              firstDeadCodeIdx = idx
            }
          })
          
          // All insights should come before hot_spots
          const hasInsights = sorted.some(i => i.type === 'insight')
          const hasHotSpots = sorted.some(i => i.type === 'hot_spot')
          const hasDeadCode = sorted.some(i => i.type === 'dead_code')
          
          if (hasInsights && hasHotSpots) {
            const firstHotSpotIdx = sorted.findIndex(i => i.type === 'hot_spot')
            expect(lastInsightIdx).toBeLessThan(firstHotSpotIdx)
          }
          
          // All hot_spots should come before dead_code
          if (hasHotSpots && hasDeadCode) {
            expect(lastHotSpotIdx).toBeLessThan(firstDeadCodeIdx)
          }
          
          // All insights should come before dead_code
          if (hasInsights && hasDeadCode) {
            expect(lastInsightIdx).toBeLessThan(firstDeadCodeIdx)
          }
          
          // Verify all original items are present
          expect(sorted.length).toBe(items.length)
        }
      ),
      { numRuns: 100 }
    )
  })

  /**
   * **Feature: transparent-scoring-formula, Property 7: UI Sorting Options**
   * **Validates: Requirements 7.4**
   * 
   * Property: When sorting by "file", findings SHALL be ordered 
   * alphabetically by file_path.
   */
  it('should sort alphabetically by file path', () => {
    fc.assert(
      fc.property(
        fc.array(findingItemArb, { minLength: 1, maxLength: 20 }),
        (items) => {
          const sorted = sortFindings(items, 'file')
          
          // Verify alphabetical order by file path
          for (let i = 0; i < sorted.length - 1; i++) {
            const currentPath = getItemFilePath(sorted[i])
            const nextPath = getItemFilePath(sorted[i + 1])
            expect(currentPath.localeCompare(nextPath)).toBeLessThanOrEqual(0)
          }
          
          // Verify all original items are present
          expect(sorted.length).toBe(items.length)
        }
      ),
      { numRuns: 100 }
    )
  })

  /**
   * Property: Sorting SHALL not modify the original array (immutability).
   */
  it('should not modify the original array', () => {
    fc.assert(
      fc.property(
        fc.array(findingItemArb, { minLength: 1, maxLength: 20 }),
        fc.constantFrom<SortOption>('score', 'type', 'file'),
        (items, sortOption) => {
          // Create a deep copy to compare
          const originalItems = JSON.stringify(items)
          
          // Sort
          sortFindings(items, sortOption)
          
          // Original should be unchanged
          expect(JSON.stringify(items)).toBe(originalItems)
        }
      ),
      { numRuns: 100 }
    )
  })

  /**
   * Property: Sorting SHALL preserve all items (no items lost or duplicated).
   */
  it('should preserve all items after sorting', () => {
    fc.assert(
      fc.property(
        fc.array(findingItemArb, { minLength: 1, maxLength: 20 }),
        fc.constantFrom<SortOption>('score', 'type', 'file'),
        (items, sortOption) => {
          const sorted = sortFindings(items, sortOption)
          
          // Same length
          expect(sorted.length).toBe(items.length)
          
          // All original items should be in sorted array
          const originalIds = items.map(i => (i.data as { id: string }).id).sort()
          const sortedIds = sorted.map(i => (i.data as { id: string }).id).sort()
          expect(sortedIds).toEqual(originalIds)
        }
      ),
      { numRuns: 100 }
    )
  })

  /**
   * Property: Empty array should return empty array for any sort option.
   */
  it('should handle empty arrays', () => {
    fc.assert(
      fc.property(
        fc.constantFrom<SortOption>('score', 'type', 'file'),
        (sortOption) => {
          const sorted = sortFindings([], sortOption)
          expect(sorted).toEqual([])
        }
      ),
      { numRuns: 10 }
    )
  })

  /**
   * Property: Single item array should return same item for any sort option.
   */
  it('should handle single item arrays', () => {
    fc.assert(
      fc.property(
        findingItemArb,
        fc.constantFrom<SortOption>('score', 'type', 'file'),
        (item, sortOption) => {
          const sorted = sortFindings([item], sortOption)
          expect(sorted.length).toBe(1)
          expect((sorted[0].data as { id: string }).id).toBe((item.data as { id: string }).id)
        }
      ),
      { numRuns: 100 }
    )
  })
})
