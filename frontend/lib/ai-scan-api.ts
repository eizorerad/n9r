/**
 * AI Scan API client for triggering scans and retrieving results.
 * 
 * Requirements: 7.1
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1";

// =============================================================================
// Types
// =============================================================================

export type AIScanDimension = 
  | "security" 
  | "db_consistency" 
  | "api_correctness" 
  | "code_health" 
  | "other";

export type AIScanSeverity = "critical" | "high" | "medium" | "low";

export type AIScanConfidence = "high" | "medium" | "low";

export type AIScanStatus = "pending" | "running" | "completed" | "failed";

export type InvestigationStatus = 
  | "confirmed" 
  | "likely_real" 
  | "uncertain" 
  | "invalid";

export interface FileLocation {
  path: string;
  line_start: number;
  line_end: number;
}

export interface AIScanIssue {
  id: string;
  dimension: AIScanDimension;
  severity: AIScanSeverity;
  title: string;
  summary: string;
  files: FileLocation[];
  evidence_snippets: string[];
  confidence: AIScanConfidence;
  found_by_models: string[];
  investigation_status: InvestigationStatus | null;
  suggested_fix: string | null;
}

export interface RepoOverview {
  guessed_project_type: string;
  main_languages: string[];
  main_components: string[];
}

export interface AIScanCacheResponse {
  analysis_id: string;
  commit_sha: string;
  status: AIScanStatus;
  repo_overview: RepoOverview | null;
  issues: AIScanIssue[];
  computed_at: string | null;
  is_cached: boolean;
  total_tokens_used: number | null;
  total_cost_usd: number | null;
}

export interface AIScanTriggerResponse {
  analysis_id: string;
  status: AIScanStatus;
  message: string;
}

export interface AIScanRequest {
  models?: string[];
  investigate_severity?: AIScanSeverity[];
  max_issues_to_investigate?: number;
}

export interface AIScanProgressEvent {
  analysis_id: string;
  stage: string;
  progress: number;
  message: string;
  status: AIScanStatus;
}

// =============================================================================
// API Error
// =============================================================================

export class AIScanApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: string
  ) {
    super(message);
    this.name = "AIScanApiError";
  }

  isConflict(): boolean {
    return this.status === 409;
  }

  isNotFound(): boolean {
    return this.status === 404;
  }

  isUnauthorized(): boolean {
    return this.status === 401;
  }
}

/**
 * Handle 401 Unauthorized by redirecting to login.
 */
function handleUnauthorized() {
  if (typeof window !== "undefined") {
    window.location.href = "/login?error=session_expired";
  }
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Trigger an AI scan for an existing analysis.
 * 
 * Requirements: 7.1
 */
export async function triggerAIScan(
  analysisId: string,
  token: string,
  request?: AIScanRequest
): Promise<AIScanTriggerResponse> {
  const response = await fetch(
    `${API_BASE_URL}/analyses/${analysisId}/ai-scan`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: request ? JSON.stringify(request) : undefined,
    }
  );

  if (!response.ok) {
    // Handle 401 - session expired
    if (response.status === 401) {
      handleUnauthorized();
      throw new AIScanApiError(401, "Session expired. Please log in again.");
    }
    const error = await response.json().catch(() => ({}));
    throw new AIScanApiError(
      response.status,
      error.detail || response.statusText,
      error.detail
    );
  }

  return response.json();
}

/**
 * Get AI scan results from cache.
 * 
 * Requirements: 7.1
 */
export async function getAIScanResults(
  analysisId: string,
  token: string
): Promise<AIScanCacheResponse> {
  const response = await fetch(
    `${API_BASE_URL}/analyses/${analysisId}/ai-scan`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    // Handle 401 - session expired
    if (response.status === 401) {
      handleUnauthorized();
      throw new AIScanApiError(401, "Session expired. Please log in again.");
    }
    const error = await response.json().catch(() => ({}));
    throw new AIScanApiError(
      response.status,
      error.detail || response.statusText,
      error.detail
    );
  }

  return response.json();
}

/**
 * Get the SSE stream URL for AI scan progress.
 * 
 * Requirements: 6.4
 */
export function getAIScanStreamUrl(analysisId: string): string {
  return `${API_BASE_URL}/analyses/${analysisId}/ai-scan/stream`;
}
