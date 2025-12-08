"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

/**
 * Architecture findings hook for fetching dead code, hot spots, and AI insights.
 *
 * **Feature: cluster-map-refactoring**
 * **Validates: Requirements 6.1, 6.2**
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1";

/**
 * Handle 401 Unauthorized by redirecting to login.
 */
function handleUnauthorized() {
  if (typeof window !== "undefined") {
    window.location.href = "/login?error=session_expired";
  }
}

// ============================================================================
// Types
// ============================================================================

export interface DeadCodeFinding {
  id: string;
  file_path: string;
  function_name: string;
  line_start: number;
  line_end: number;
  line_count: number;
  confidence: number;
  evidence: string;
  suggested_action: string;
  is_dismissed: boolean;
  dismissed_at: string | null;
  created_at: string;
}

export interface HotSpotFinding {
  id: string;
  file_path: string;
  changes_90d: number;
  coverage_rate: number | null;
  unique_authors: number;
  risk_factors: string[];
  suggested_action: string | null;
  created_at: string;
}

export interface SemanticAIInsight {
  id: string;
  insight_type: "dead_code" | "hot_spot" | "architecture";
  title: string;
  description: string;
  priority: "high" | "medium" | "low";
  affected_files: string[];
  evidence: string | null;
  suggested_action: string | null;
  is_dismissed: boolean;
  dismissed_at: string | null;
  created_at: string;
}

export interface ArchitectureSummary {
  health_score: number;
  main_concerns: string[];
  dead_code_count: number;
  hot_spot_count: number;
  insights_count: number;
}

export interface ArchitectureFindingsResponse {
  summary: ArchitectureSummary;
  dead_code: DeadCodeFinding[];
  hot_spots: HotSpotFinding[];
  insights: SemanticAIInsight[];
}

// ============================================================================
// API Functions
// ============================================================================

async function fetchArchitectureFindings(
  token: string,
  repositoryId: string,
  analysisId?: string | null,
  includeDismissed?: boolean
): Promise<ArchitectureFindingsResponse> {
  const params = new URLSearchParams();
  if (analysisId) {
    params.set("analysis_id", analysisId);
  }
  if (includeDismissed) {
    params.set("include_dismissed", "true");
  }
  const query = params.toString();

  const url = `${API_BASE_URL}/repositories/${repositoryId}/architecture-findings${query ? `?${query}` : ""}`;
  console.log('[useArchitectureFindings] Fetching:', url);

  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    console.error('[useArchitectureFindings] Fetch failed:', response.status);
    if (response.status === 401) {
      handleUnauthorized();
      throw new Error("Session expired. Please log in again.");
    }
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch architecture findings: ${response.status}`);
  }

  const data = await response.json();
  console.log('[useArchitectureFindings] Fetch success:', {
    insightsCount: data.insights?.length,
    deadCodeCount: data.dead_code?.length,
    hotSpotsCount: data.hot_spots?.length,
    healthScore: data.summary?.health_score,
  });
  return data;
}

async function dismissDeadCode(
  token: string,
  repositoryId: string,
  deadCodeId: string
): Promise<{ id: string; is_dismissed: boolean; dismissed_at: string | null }> {
  const response = await fetch(
    `${API_BASE_URL}/repositories/${repositoryId}/dead-code/${deadCodeId}/dismiss`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    }
  );

  if (!response.ok) {
    if (response.status === 401) {
      handleUnauthorized();
      throw new Error("Session expired. Please log in again.");
    }
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to dismiss dead code: ${response.status}`);
  }

  return response.json();
}

async function dismissInsight(
  token: string,
  repositoryId: string,
  insightId: string
): Promise<{ id: string; is_dismissed: boolean; dismissed_at: string | null }> {
  const response = await fetch(
    `${API_BASE_URL}/repositories/${repositoryId}/insights/${insightId}/dismiss`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    }
  );

  if (!response.ok) {
    if (response.status === 401) {
      handleUnauthorized();
      throw new Error("Session expired. Please log in again.");
    }
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to dismiss insight: ${response.status}`);
  }

  return response.json();
}

// ============================================================================
// Query Keys
// ============================================================================

export function getArchitectureFindingsQueryKey(
  repositoryId: string,
  analysisId?: string | null
) {
  return ["architecture-findings", repositoryId, analysisId ?? "latest"];
}

// ============================================================================
// Hooks
// ============================================================================

export interface UseArchitectureFindingsOptions {
  /** Repository ID to fetch findings for */
  repositoryId: string;
  /** Specific analysis ID. If not provided, uses latest completed analysis. */
  analysisId?: string | null;
  /** Authentication token (required) */
  token: string;
  /** Include dismissed findings in response */
  includeDismissed?: boolean;
  /** Whether the hook is enabled */
  enabled?: boolean;
}

/**
 * Hook to fetch architecture findings (dead code, hot spots, AI insights).
 *
 * Fetches from GET /v1/repositories/{id}/architecture-findings
 *
 * **Feature: cluster-map-refactoring**
 * **Validates: Requirements 6.1, 6.2**
 *
 * @example
 * ```tsx
 * const { data, isLoading, error } = useArchitectureFindings({
 *   repositoryId: repoId,
 *   analysisId: selectedAnalysisId,
 * });
 *
 * if (isLoading) return <Skeleton />;
 * if (error) return <ErrorMessage error={error} />;
 *
 * return (
 *   <div>
 *     <h2>Health Score: {data.summary.health_score}</h2>
 *     <DeadCodeList items={data.dead_code} />
 *     <HotSpotsList items={data.hot_spots} />
 *     <InsightsList items={data.insights} />
 *   </div>
 * );
 * ```
 */
export function useArchitectureFindings(options: UseArchitectureFindingsOptions) {
  const { repositoryId, analysisId, token, includeDismissed = false, enabled = true } = options;

  const queryKey = getArchitectureFindingsQueryKey(repositoryId, analysisId);

  // Compute enabled state - requires token, repositoryId, and analysisId
  const isEnabled = enabled && !!token && !!repositoryId && !!analysisId;

  return useQuery({
    queryKey,
    queryFn: () => fetchArchitectureFindings(token, repositoryId, analysisId, includeDismissed),
    enabled: isEnabled,
    // Cache for 5 minutes - findings don't change frequently
    staleTime: 5 * 60 * 1000,
    // Keep in cache for 30 minutes
    gcTime: 30 * 60 * 1000,
    // Retry on failure
    retry: 2,
    retryDelay: 1000,
    // Always refetch on mount to ensure fresh data after analysis completes
    refetchOnMount: true,
  });
}

/**
 * Hook to dismiss a dead code finding.
 *
 * Uses optimistic update for immediate UI feedback.
 *
 * **Feature: cluster-map-refactoring**
 * **Validates: Requirements 7.3**
 */
export function useDismissDeadCode(repositoryId: string, token: string, analysisId?: string | null) {
  const queryClient = useQueryClient();
  const queryKey = getArchitectureFindingsQueryKey(repositoryId, analysisId);

  return useMutation({
    mutationFn: (deadCodeId: string) => dismissDeadCode(token, repositoryId, deadCodeId),
    // Optimistic update
    onMutate: async (deadCodeId) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey });

      // Snapshot previous value
      const previousData = queryClient.getQueryData<ArchitectureFindingsResponse>(queryKey);

      // Optimistically update
      if (previousData) {
        queryClient.setQueryData<ArchitectureFindingsResponse>(queryKey, {
          ...previousData,
          dead_code: previousData.dead_code.filter((dc) => dc.id !== deadCodeId),
          summary: {
            ...previousData.summary,
            dead_code_count: previousData.summary.dead_code_count - 1,
          },
        });
      }

      return { previousData };
    },
    // Rollback on error
    onError: (_err, _deadCodeId, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(queryKey, context.previousData);
      }
    },
    // Refetch after success or error
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey });
    },
  });
}

/**
 * Hook to dismiss a semantic AI insight.
 *
 * Uses optimistic update for immediate UI feedback.
 *
 * **Feature: cluster-map-refactoring**
 */
export function useDismissInsight(repositoryId: string, token: string, analysisId?: string | null) {
  const queryClient = useQueryClient();
  const queryKey = getArchitectureFindingsQueryKey(repositoryId, analysisId);

  return useMutation({
    mutationFn: (insightId: string) => dismissInsight(token, repositoryId, insightId),
    // Optimistic update
    onMutate: async (insightId) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey });

      // Snapshot previous value
      const previousData = queryClient.getQueryData<ArchitectureFindingsResponse>(queryKey);

      // Optimistically update
      if (previousData) {
        queryClient.setQueryData<ArchitectureFindingsResponse>(queryKey, {
          ...previousData,
          insights: previousData.insights.filter((insight) => insight.id !== insightId),
          summary: {
            ...previousData.summary,
            insights_count: previousData.summary.insights_count - 1,
          },
        });
      }

      return { previousData };
    },
    // Rollback on error
    onError: (_err, _insightId, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(queryKey, context.previousData);
      }
    },
    // Refetch after success or error
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey });
    },
  });
}
