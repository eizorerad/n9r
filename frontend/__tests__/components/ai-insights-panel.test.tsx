/**
 * Unit Tests for AIInsightsPanel
 * 
 * Tests rendering with cached data, without cache, and progress display.
 * Requirements: 6.1, 6.2, 6.3
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AIInsightsPanel } from '@/components/ai-insights-panel'
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import * as aiScanApi from '@/lib/ai-scan-api'

// Mock the AI scan API
vi.mock('@/lib/ai-scan-api', () => ({
  triggerAIScan: vi.fn(),
  getAIScanResults: vi.fn(),
  getAIScanStreamUrl: vi.fn((id: string) => `http://localhost:8000/v1/analyses/${id}/ai-scan/stream`),
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

// Mock fetch for SSE streaming
const mockFetch = vi.fn()
global.fetch = mockFetch

describe('AIInsightsPanel', () => {
  const mockToken = 'test-token'
  const mockRepositoryId = 'repo-123'
  const mockAnalysisId = 'analysis-456'

  beforeEach(() => {
    vi.clearAllMocks()
    useCommitSelectionStore.getState().clearSelection()
    mockFetch.mockReset()
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
   * Test: When AI scan cache is empty, show "Run AI Scan" button
   * Requirements: 6.3
   */
  it('should show Run AI Scan button when no cache exists', async () => {
    // Set up commit selection
    useCommitSelectionStore.getState().setSelectedCommit('abc123', mockAnalysisId)

    // Mock API to return no cache - status should be 'completed' or similar
    // but is_cached: false indicates no scan has been run yet
    vi.mocked(aiScanApi.getAIScanResults).mockResolvedValue({
      analysis_id: mockAnalysisId,
      commit_sha: 'abc123',
      status: 'completed', // Not pending/running to avoid triggering SSE
      repo_overview: null,
      issues: [],
      computed_at: null,
      is_cached: false, // This is the key - no cache exists
      total_tokens_used: null,
      total_cost_usd: null,
    })

    render(<AIInsightsPanel repositoryId={mockRepositoryId} token={mockToken} />)

    await waitFor(() => {
      expect(screen.getByText('Run AI Scan')).toBeInTheDocument()
    })

    expect(screen.getByText('AI-Powered Analysis')).toBeInTheDocument()
  })

  /**
   * Test: When AI scan cache exists with issues, display issues grouped by severity
   * Requirements: 6.2
   */
  it('should display issues grouped by severity when cache exists', async () => {
    // Set up commit selection
    useCommitSelectionStore.getState().setSelectedCommit('abc123', mockAnalysisId)

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
})
