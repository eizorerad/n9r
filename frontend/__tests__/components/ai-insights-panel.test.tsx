/**
 * Unit Tests for AIInsightsPanel
 * 
 * Tests rendering with cached data, without cache, and progress display.
 * Now uses unified useAnalysisStatusWithStore hook for status tracking.
 * 
 * **Feature: ai-scan-progress-fix**
 * **Validates: Requirements 3.2, 3.3, 6.1, 6.2, 6.3**
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AIInsightsPanel } from '@/components/ai-insights-panel'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import * as aiScanApi from '@/lib/ai-scan-api'
import * as useAnalysisStatusModule from '@/lib/hooks/use-analysis-status'

// Mock the AI scan API
vi.mock('@/lib/ai-scan-api', () => ({
  triggerAIScan: vi.fn(),
  getAIScanResults: vi.fn(),
  AIScanApiError: class AIScanApiError extends Error {
    status: number
    detail?: string
    constructor(status: number, message: string, detail?: string) {
      super(message)
      this.status = status
      this.detail = detail
    }
    isConflict() { return this.status === 409 }
    isNotFound() { return this.status === 404 }
  },
}))

// Mock the useAnalysisStatusWithStore hook
vi.mock('@/lib/hooks/use-analysis-status', () => ({
  useAnalysisStatusWithStore: vi.fn(),
}))

describe('AIInsightsPanel', () => {
  const mockToken = 'test-token'
  const mockRepositoryId = 'repo-123'
  const mockAnalysisId = 'analysis-456'

  // Default mock for useAnalysisStatusWithStore with all required fields
  const mockRefetch = vi.fn()
  const defaultStatusData: useAnalysisStatusModule.AnalysisFullStatus = {
    analysis_id: mockAnalysisId,
    repository_id: mockRepositoryId,
    commit_sha: 'abc123',
    analysis_status: 'completed',
    vci_score: 85,
    grade: 'B',
    embeddings_status: 'completed',
    embeddings_progress: 100,
    embeddings_stage: null,
    embeddings_message: null,
    embeddings_error: null,
    vectors_count: 100,
    semantic_cache_status: 'completed',
    has_semantic_cache: true,
    ai_scan_status: 'none',
    ai_scan_progress: 0,
    ai_scan_stage: null,
    ai_scan_message: null,
    ai_scan_error: null,
    has_ai_scan_cache: false,
    ai_scan_started_at: null,
    ai_scan_completed_at: null,
    state_updated_at: '2025-12-04T10:00:00Z',
    embeddings_started_at: null,
    embeddings_completed_at: null,
    overall_progress: 80,
    overall_stage: 'Semantic cache completed',
    is_complete: false,
  }
  
  const defaultStatusMock: useAnalysisStatusModule.UseAnalysisStatusResult = {
    data: defaultStatusData,
    isLoading: false,
    error: null,
    isComplete: false,
    overallProgress: 80,
    overallStage: 'Semantic cache completed',
    refetch: mockRefetch,
    invalidate: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    useCommitSelectionStore.getState().clearSelection()
    // Reset the mock to default behavior
    vi.mocked(useAnalysisStatusModule.useAnalysisStatusWithStore).mockReturnValue(defaultStatusMock)
  })

  /**
   * Test: When no commit is selected, show appropriate message
   * Requirements: 6.1
   */
  it('should show message when no commit is selected', async () => {
    render(<AIInsightsPanel repositoryId={mockRepositoryId} token={mockToken} />)

    await waitFor(() => {
      expect(screen.getByText('Select a commit to view AI insights')).toBeInTheDocument()
    })
  })

  /**
   * Test: When AI scan cache is empty, show informational message
   * AI scan starts automatically with main analysis
   */
  it('should show informational message when no cache exists', async () => {
    // Set up commit selection
    useCommitSelectionStore.getState().setSelectedCommit('abc123', mockAnalysisId)

    // Mock unified status hook to return ai_scan_status: 'none'
    vi.mocked(useAnalysisStatusModule.useAnalysisStatusWithStore).mockReturnValue({
      ...defaultStatusMock,
      data: {
        ...defaultStatusMock.data!,
        ai_scan_status: 'none',
      },
    })

    // Mock API to return no cache
    vi.mocked(aiScanApi.getAIScanResults).mockResolvedValue({
      analysis_id: mockAnalysisId,
      commit_sha: 'abc123',
      status: 'completed',
      repo_overview: null,
      issues: [],
      computed_at: null,
      is_cached: false,
      total_tokens_used: null,
      total_cost_usd: null,
    })

    render(<AIInsightsPanel repositoryId={mockRepositoryId} token={mockToken} />)

    await waitFor(() => {
      expect(screen.getByText('AI-Powered Analysis')).toBeInTheDocument()
    })

    expect(screen.getByText(/AI scan runs automatically when you start the main analysis/)).toBeInTheDocument()
  })

  /**
   * Test: When AI scan cache exists with issues, display issues grouped by severity
   * Requirements: 6.2
   */
  it('should display issues grouped by severity when cache exists', async () => {
    // Set up commit selection
    useCommitSelectionStore.getState().setSelectedCommit('abc123', mockAnalysisId)

    // Mock unified status hook to return ai_scan_status: 'completed'
    vi.mocked(useAnalysisStatusModule.useAnalysisStatusWithStore).mockReturnValue({
      ...defaultStatusMock,
      data: {
        ...defaultStatusMock.data!,
        ai_scan_status: 'completed',
        has_ai_scan_cache: true,
      },
    })

    // Mock API to return cached results with issues
    vi.mocked(aiScanApi.getAIScanResults).mockResolvedValue({
      analysis_id: mockAnalysisId,
      commit_sha: 'abc123',
      status: 'completed',
      repo_overview: {
        guessed_project_type: 'FastAPI backend',
        main_languages: ['python'],
        main_components: ['API'],
      },
      issues: [
        {
          id: 'sec-001',
          dimension: 'security',
          severity: 'critical',
          title: 'Hardcoded API Key',
          summary: 'Found hardcoded API key in config file',
          files: [{ path: 'config.py', line_start: 10, line_end: 10 }],
          evidence_snippets: ['API_KEY = "secret123"'],
          confidence: 'high',
          found_by_models: ['gemini', 'claude'],
          investigation_status: 'confirmed',
          suggested_fix: 'Use environment variables',
        },
        {
          id: 'health-001',
          dimension: 'code_health',
          severity: 'medium',
          title: 'Complex Function',
          summary: 'Function has high cyclomatic complexity',
          files: [{ path: 'utils.py', line_start: 50, line_end: 100 }],
          evidence_snippets: [],
          confidence: 'medium',
          found_by_models: ['gemini'],
          investigation_status: null,
          suggested_fix: null,
        },
      ],
      computed_at: '2025-12-04T10:00:00Z',
      is_cached: true,
      total_tokens_used: 50000,
      total_cost_usd: 0.15,
    })

    render(<AIInsightsPanel repositoryId={mockRepositoryId} token={mockToken} />)

    await waitFor(() => {
      expect(screen.getByText('2 issues found')).toBeInTheDocument()
    })

    // Check severity badges
    expect(screen.getByText('1 Critical')).toBeInTheDocument()
    expect(screen.getByText('1 Medium')).toBeInTheDocument()

    // Check issue titles
    expect(screen.getByText('Hardcoded API Key')).toBeInTheDocument()
    expect(screen.getByText('Complex Function')).toBeInTheDocument()

    // Check cost display
    expect(screen.getByText('$0.150')).toBeInTheDocument()
  })

  /**
   * Test: When AI scan completed with no issues, show success message
   * Requirements: 6.2
   */
  it('should show success message when scan completed with no issues', async () => {
    // Set up commit selection
    useCommitSelectionStore.getState().setSelectedCommit('abc123', mockAnalysisId)

    // Mock unified status hook to return ai_scan_status: 'completed'
    vi.mocked(useAnalysisStatusModule.useAnalysisStatusWithStore).mockReturnValue({
      ...defaultStatusMock,
      data: {
        ...defaultStatusMock.data!,
        ai_scan_status: 'completed',
        has_ai_scan_cache: true,
      },
    })

    // Mock API to return completed scan with no issues
    vi.mocked(aiScanApi.getAIScanResults).mockResolvedValue({
      analysis_id: mockAnalysisId,
      commit_sha: 'abc123',
      status: 'completed',
      repo_overview: {
        guessed_project_type: 'FastAPI backend',
        main_languages: ['python'],
        main_components: ['API'],
      },
      issues: [],
      computed_at: '2025-12-04T10:00:00Z',
      is_cached: true,
      total_tokens_used: 50000,
      total_cost_usd: 0.10,
    })

    render(<AIInsightsPanel repositoryId={mockRepositoryId} token={mockToken} />)

    await waitFor(() => {
      expect(screen.getByText('No issues found')).toBeInTheDocument()
    })

    expect(screen.getByText('AI scan completed successfully')).toBeInTheDocument()
  })

  /**
   * Test: When AI scan failed, show error and retry button
   * Requirements: 6.1
   */
  it('should show error state when scan failed', async () => {
    // Set up commit selection
    useCommitSelectionStore.getState().setSelectedCommit('abc123', mockAnalysisId)

    // Mock unified status hook to return ai_scan_status: 'failed'
    vi.mocked(useAnalysisStatusModule.useAnalysisStatusWithStore).mockReturnValue({
      ...defaultStatusMock,
      data: {
        ...defaultStatusMock.data!,
        ai_scan_status: 'failed',
        ai_scan_error: 'LLM API error',
        has_ai_scan_cache: true,
      },
    })

    // Mock API to return failed scan
    vi.mocked(aiScanApi.getAIScanResults).mockResolvedValue({
      analysis_id: mockAnalysisId,
      commit_sha: 'abc123',
      status: 'failed',
      repo_overview: null,
      issues: [],
      computed_at: null,
      is_cached: true,
      total_tokens_used: null,
      total_cost_usd: null,
    })

    render(<AIInsightsPanel repositoryId={mockRepositoryId} token={mockToken} />)

    await waitFor(() => {
      expect(screen.getByText('AI scan failed')).toBeInTheDocument()
    })

    expect(screen.getByText('Retry Scan')).toBeInTheDocument()
  })

  /**
   * Test: Issue card expands to show details when clicked
   * Requirements: 6.2
   */
  it('should expand issue card to show details when clicked', async () => {
    const user = userEvent.setup()

    // Set up commit selection
    useCommitSelectionStore.getState().setSelectedCommit('abc123', mockAnalysisId)

    // Mock unified status hook to return ai_scan_status: 'completed'
    vi.mocked(useAnalysisStatusModule.useAnalysisStatusWithStore).mockReturnValue({
      ...defaultStatusMock,
      data: {
        ...defaultStatusMock.data!,
        ai_scan_status: 'completed',
        has_ai_scan_cache: true,
      },
    })

    // Mock API to return cached results with an issue
    vi.mocked(aiScanApi.getAIScanResults).mockResolvedValue({
      analysis_id: mockAnalysisId,
      commit_sha: 'abc123',
      status: 'completed',
      repo_overview: null,
      issues: [
        {
          id: 'sec-001',
          dimension: 'security',
          severity: 'high',
          title: 'SQL Injection Risk',
          summary: 'User input is not sanitized before database query',
          files: [{ path: 'db.py', line_start: 25, line_end: 30 }],
          evidence_snippets: ['query = f"SELECT * FROM users WHERE id = {user_id}"'],
          confidence: 'high',
          found_by_models: ['claude'],
          investigation_status: 'confirmed',
          suggested_fix: 'Use parameterized queries',
        },
      ],
      computed_at: '2025-12-04T10:00:00Z',
      is_cached: true,
      total_tokens_used: 30000,
      total_cost_usd: 0.08,
    })

    render(<AIInsightsPanel repositoryId={mockRepositoryId} token={mockToken} />)

    await waitFor(() => {
      expect(screen.getByText('SQL Injection Risk')).toBeInTheDocument()
    })

    // Click to expand
    await user.click(screen.getByText('SQL Injection Risk'))

    // Check expanded content
    await waitFor(() => {
      expect(screen.getByText('User input is not sanitized before database query')).toBeInTheDocument()
    })

    expect(screen.getByText('Use parameterized queries')).toBeInTheDocument()
  })

  /**
   * Test: Shows loading state while fetching results
   * Requirements: 6.1
   */
  it('should show loading state while fetching results', async () => {
    // Set up commit selection
    useCommitSelectionStore.getState().setSelectedCommit('abc123', mockAnalysisId)

    // Mock API to delay response
    vi.mocked(aiScanApi.getAIScanResults).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve({
        analysis_id: mockAnalysisId,
        commit_sha: 'abc123',
        status: 'completed',
        repo_overview: null,
        issues: [],
        computed_at: null,
        is_cached: true,
        total_tokens_used: null,
        total_cost_usd: null,
      }), 100))
    )

    render(<AIInsightsPanel repositoryId={mockRepositoryId} token={mockToken} />)

    // Should show loading initially
    // The loading spinner is rendered as an SVG with animate-spin class
    const loadingSpinner = document.querySelector('.animate-spin')
    expect(loadingSpinner).toBeInTheDocument()
  })

  /**
   * Test: Displays multi-model badge when issue found by multiple models
   * Requirements: 6.2
   */
  it('should display multi-model badge when issue found by multiple models', async () => {
    // Set up commit selection
    useCommitSelectionStore.getState().setSelectedCommit('abc123', mockAnalysisId)

    // Mock unified status hook to return ai_scan_status: 'completed'
    vi.mocked(useAnalysisStatusModule.useAnalysisStatusWithStore).mockReturnValue({
      ...defaultStatusMock,
      data: {
        ...defaultStatusMock.data!,
        ai_scan_status: 'completed',
        has_ai_scan_cache: true,
      },
    })

    // Mock API to return issue found by multiple models
    vi.mocked(aiScanApi.getAIScanResults).mockResolvedValue({
      analysis_id: mockAnalysisId,
      commit_sha: 'abc123',
      status: 'completed',
      repo_overview: null,
      issues: [
        {
          id: 'sec-001',
          dimension: 'security',
          severity: 'high',
          title: 'Security Issue',
          summary: 'Found by multiple models',
          files: [{ path: 'app.py', line_start: 1, line_end: 1 }],
          evidence_snippets: [],
          confidence: 'high',
          found_by_models: ['gemini', 'claude', 'gpt-4'],
          investigation_status: null,
          suggested_fix: null,
        },
      ],
      computed_at: '2025-12-04T10:00:00Z',
      is_cached: true,
      total_tokens_used: 50000,
      total_cost_usd: 0.15,
    })

    render(<AIInsightsPanel repositoryId={mockRepositoryId} token={mockToken} />)

    await waitFor(() => {
      expect(screen.getByText('3 models')).toBeInTheDocument()
    })
  })

  /**
   * Test: When AI scan is running, show simplified progress message pointing to popup
   * Requirements: 3.2
   * 
   * **Feature: ai-scan-progress-fix**
   */
  it('should show simplified progress message when scan is running', async () => {
    // Set up commit selection
    useCommitSelectionStore.getState().setSelectedCommit('abc123', mockAnalysisId)

    // Mock unified status hook to return ai_scan_status: 'running'
    vi.mocked(useAnalysisStatusModule.useAnalysisStatusWithStore).mockReturnValue({
      ...defaultStatusMock,
      data: {
        ...defaultStatusMock.data!,
        ai_scan_status: 'running',
        ai_scan_progress: 45,
        ai_scan_stage: 'scanning',
        ai_scan_message: 'Scanning with AI models...',
      },
    })

    // Mock API to return no cache (scan in progress)
    vi.mocked(aiScanApi.getAIScanResults).mockResolvedValue({
      analysis_id: mockAnalysisId,
      commit_sha: 'abc123',
      status: 'running',
      repo_overview: null,
      issues: [],
      computed_at: null,
      is_cached: false,
      total_tokens_used: null,
      total_cost_usd: null,
    })

    render(<AIInsightsPanel repositoryId={mockRepositoryId} token={mockToken} />)

    await waitFor(() => {
      expect(screen.getByText('AI scan in progress...')).toBeInTheDocument()
    })

    // Should show message pointing to progress popup
    expect(screen.getByText('Check the progress popup in the bottom-right corner for details')).toBeInTheDocument()
  })

  /**
   * Test: When AI scan is pending, show simplified progress message
   * Requirements: 3.2
   * 
   * **Feature: ai-scan-progress-fix**
   */
  it('should show simplified progress message when scan is pending', async () => {
    // Set up commit selection
    useCommitSelectionStore.getState().setSelectedCommit('abc123', mockAnalysisId)

    // Mock unified status hook to return ai_scan_status: 'pending'
    vi.mocked(useAnalysisStatusModule.useAnalysisStatusWithStore).mockReturnValue({
      ...defaultStatusMock,
      data: {
        ...defaultStatusMock.data!,
        ai_scan_status: 'pending',
        ai_scan_progress: 0,
      },
    })

    // Mock API to return no cache
    vi.mocked(aiScanApi.getAIScanResults).mockResolvedValue({
      analysis_id: mockAnalysisId,
      commit_sha: 'abc123',
      status: 'pending',
      repo_overview: null,
      issues: [],
      computed_at: null,
      is_cached: false,
      total_tokens_used: null,
      total_cost_usd: null,
    })

    render(<AIInsightsPanel repositoryId={mockRepositoryId} token={mockToken} />)

    await waitFor(() => {
      expect(screen.getByText('AI scan in progress...')).toBeInTheDocument()
    })
  })
})
