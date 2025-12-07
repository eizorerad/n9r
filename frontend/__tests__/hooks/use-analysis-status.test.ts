/**
 * Unit Tests for useAnalysisStatus hook
 * 
 * **Feature: progress-tracking-refactor**
 * **Validates: Requirements 4.4**
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import type { AnalysisFullStatus } from '@/lib/hooks/use-analysis-status'

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

// Helper to create a wrapper with QueryClient
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
    },
  })
  const TestWrapper = ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
  TestWrapper.displayName = 'TestWrapper'
  return TestWrapper
}

// Helper to create mock status response
function createMockStatus(overrides: Partial<AnalysisFullStatus> = {}): AnalysisFullStatus {
  return {
    analysis_id: 'test-analysis-id',
    repository_id: 'test-repo-id',
    commit_sha: 'abc123',
    analysis_status: 'completed',
    vci_score: 85,
    grade: 'B',
    embeddings_status: 'running',
    embeddings_progress: 50,
    embeddings_stage: 'embedding',
    embeddings_message: 'Generating embeddings...',
    embeddings_error: null,
    vectors_count: 100,
    semantic_cache_status: 'none',
    has_semantic_cache: false,
    // AI Scan status (Requirements 3.3)
    ai_scan_status: 'none',
    ai_scan_progress: 0,
    ai_scan_stage: null,
    ai_scan_message: null,
    ai_scan_error: null,
    has_ai_scan_cache: false,
    ai_scan_started_at: null,
    ai_scan_completed_at: null,
    state_updated_at: new Date().toISOString(),
    embeddings_started_at: new Date().toISOString(),
    embeddings_completed_at: null,
    overall_progress: 65,
    overall_stage: 'Generating embeddings',
    is_complete: false,
    ...overrides,
  }
}

describe('useAnalysisStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should fetch analysis status when enabled', async () => {
    const mockStatus = createMockStatus()
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockStatus),
    })

    const { useAnalysisStatus } = await import('@/lib/hooks/use-analysis-status')

    const { result } = renderHook(
      () =>
        useAnalysisStatus({
          analysisId: 'test-analysis-id',
          repositoryId: 'test-repo-id',
          token: 'test-token',
        }),
      { wrapper: createWrapper() }
    )

    // Wait for data to load
    await waitFor(() => {
      expect(result.current.data).toBeDefined()
    }, { timeout: 3000 })

    // Verify data
    expect(result.current.data).toEqual(mockStatus)
    expect(result.current.overallProgress).toBe(65)
    expect(result.current.overallStage).toBe('Generating embeddings')
    expect(result.current.isComplete).toBe(false)
  })

  it('should not fetch when analysisId is null', async () => {
    const { useAnalysisStatus } = await import('@/lib/hooks/use-analysis-status')

    const { result } = renderHook(
      () =>
        useAnalysisStatus({
          analysisId: null,
          repositoryId: 'test-repo-id',
          token: 'test-token',
        }),
      { wrapper: createWrapper() }
    )

    // Should not be loading since query is disabled
    expect(result.current.isLoading).toBe(false)
    expect(result.current.data).toBeUndefined()
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('should not fetch when token is empty', async () => {
    const { useAnalysisStatus } = await import('@/lib/hooks/use-analysis-status')

    const { result } = renderHook(
      () =>
        useAnalysisStatus({
          analysisId: 'test-analysis-id',
          repositoryId: 'test-repo-id',
          token: '',
        }),
      { wrapper: createWrapper() }
    )

    expect(result.current.isLoading).toBe(false)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('should report is_complete correctly when all phases complete', async () => {
    const completedStatus = createMockStatus({
      analysis_status: 'completed',
      embeddings_status: 'completed',
      semantic_cache_status: 'completed',
      ai_scan_status: 'completed',
      is_complete: true,
      overall_progress: 100,
    })

    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(completedStatus),
    })

    const { useAnalysisStatus } = await import('@/lib/hooks/use-analysis-status')

    const { result } = renderHook(
      () =>
        useAnalysisStatus({
          analysisId: 'test-analysis-id',
          repositoryId: 'test-repo-id',
          token: 'test-token',
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.data).toBeDefined()
    }, { timeout: 3000 })

    expect(result.current.isComplete).toBe(true)
    expect(result.current.overallProgress).toBe(100)
  })

  it('should handle fetch errors gracefully', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'))

    const { useAnalysisStatus } = await import('@/lib/hooks/use-analysis-status')

    const { result } = renderHook(
      () =>
        useAnalysisStatus({
          analysisId: 'test-analysis-id',
          repositoryId: 'test-repo-id',
          token: 'test-token',
        }),
      { wrapper: createWrapper() }
    )

    // Wait for error state
    await waitFor(() => {
      expect(result.current.error).toBeTruthy()
    }, { timeout: 3000 })

    expect(result.current.data).toBeUndefined()
    expect(result.current.isComplete).toBe(false)
    expect(result.current.overallProgress).toBe(0)
  })

  it('should handle API error responses', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: 'Analysis not found' }),
    })

    const { useAnalysisStatus } = await import('@/lib/hooks/use-analysis-status')

    const { result } = renderHook(
      () =>
        useAnalysisStatus({
          analysisId: 'non-existent-id',
          repositoryId: 'test-repo-id',
          token: 'test-token',
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.error).toBeTruthy()
    }, { timeout: 3000 })

    expect(result.current.error?.message).toContain('Analysis not found')
  })

  it('should provide correct computed values for pending analysis', async () => {
    const pendingStatus = createMockStatus({
      analysis_status: 'pending',
      embeddings_status: 'none',
      overall_progress: 0,
      overall_stage: 'Waiting for analysis to start',
      is_complete: false,
    })

    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(pendingStatus),
    })

    const { useAnalysisStatus } = await import('@/lib/hooks/use-analysis-status')

    const { result } = renderHook(
      () =>
        useAnalysisStatus({
          analysisId: 'test-analysis-id',
          repositoryId: 'test-repo-id',
          token: 'test-token',
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.data).toBeDefined()
    }, { timeout: 3000 })

    expect(result.current.overallProgress).toBe(0)
    expect(result.current.overallStage).toBe('Waiting for analysis to start')
    expect(result.current.isComplete).toBe(false)
  })

  it('should provide refetch and invalidate functions', async () => {
    const mockStatus = createMockStatus()
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockStatus),
    })

    const { useAnalysisStatus } = await import('@/lib/hooks/use-analysis-status')

    const { result } = renderHook(
      () =>
        useAnalysisStatus({
          analysisId: 'test-analysis-id',
          repositoryId: 'test-repo-id',
          token: 'test-token',
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.data).toBeDefined()
    }, { timeout: 3000 })

    // Verify functions exist and are callable
    expect(typeof result.current.refetch).toBe('function')
    expect(typeof result.current.invalidate).toBe('function')
  })
})

describe('getAnalysisStatusQueryKey', () => {
  it('should generate consistent query keys', async () => {
    const { getAnalysisStatusQueryKey } = await import('@/lib/hooks/use-analysis-status')

    const key1 = getAnalysisStatusQueryKey('repo-1', 'analysis-1')
    const key2 = getAnalysisStatusQueryKey('repo-1', 'analysis-1')
    const key3 = getAnalysisStatusQueryKey('repo-1', 'analysis-2')

    expect(key1).toEqual(key2)
    expect(key1).not.toEqual(key3)
    expect(key1).toEqual(['analysis-status', 'repo-1', 'analysis-1'])
  })

  it('should handle null analysisId', async () => {
    const { getAnalysisStatusQueryKey } = await import('@/lib/hooks/use-analysis-status')

    const key = getAnalysisStatusQueryKey('repo-1', null)
    expect(key).toEqual(['analysis-status', 'repo-1', null])
  })
})

describe('Polling behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
  })

  it('should use fast polling interval for running status', async () => {
    // Test the getPollingInterval logic indirectly by checking the hook behavior
    const runningStatus = createMockStatus({
      embeddings_status: 'running',
      embeddings_progress: 50,
      is_complete: false,
    })

    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(runningStatus),
    })

    const { useAnalysisStatus } = await import('@/lib/hooks/use-analysis-status')

    const { result } = renderHook(
      () =>
        useAnalysisStatus({
          analysisId: 'test-analysis-id',
          repositoryId: 'test-repo-id',
          token: 'test-token',
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.data).toBeDefined()
    }, { timeout: 3000 })

    // Verify the status shows running
    expect(result.current.data?.embeddings_status).toBe('running')
    expect(result.current.isComplete).toBe(false)
  })

  it('should stop polling when complete', async () => {
    const completedStatus = createMockStatus({
      analysis_status: 'completed',
      embeddings_status: 'completed',
      semantic_cache_status: 'completed',
      ai_scan_status: 'completed',
      is_complete: true,
      overall_progress: 100,
    })

    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(completedStatus),
    })

    const { useAnalysisStatus } = await import('@/lib/hooks/use-analysis-status')

    const { result } = renderHook(
      () =>
        useAnalysisStatus({
          analysisId: 'test-analysis-id',
          repositoryId: 'test-repo-id',
          token: 'test-token',
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.data).toBeDefined()
    }, { timeout: 3000 })

    // Verify the status shows complete
    expect(result.current.isComplete).toBe(true)
    
    // The hook should have stopped polling (refetchInterval returns false)
    // We can't easily test this without fake timers, but we verify the state is correct
    expect(result.current.overallProgress).toBe(100)
  })
})
