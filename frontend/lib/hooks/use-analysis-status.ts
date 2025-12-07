"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useCallback } from "react";

/**
 * Analysis status response from the full-status endpoint.
 * 
 * **Feature: progress-tracking-refactor, ai-scan-progress-fix**
 * **Validates: Requirements 4.1, 4.4, 3.3**
 */
export interface AnalysisFullStatus {
  // Identity
  analysis_id: string;
  repository_id: string;
  commit_sha: string;

  // Analysis status
  analysis_status: "pending" | "running" | "completed" | "failed";
  vci_score: number | null;
  grade: string | null;

  // Embeddings status
  embeddings_status: "none" | "pending" | "running" | "completed" | "failed";
  embeddings_progress: number;
  embeddings_stage: string | null;
  embeddings_message: string | null;
  embeddings_error: string | null;
  vectors_count: number;

  // Semantic cache status
  semantic_cache_status: "none" | "pending" | "computing" | "completed" | "failed";
  has_semantic_cache: boolean;

  // AI Scan status (Requirements 3.3)
  // **Feature: ai-scan-progress-fix**
  ai_scan_status: "none" | "pending" | "running" | "completed" | "failed" | "skipped";
  ai_scan_progress: number;
  ai_scan_stage: string | null;
  ai_scan_message: string | null;
  ai_scan_error: string | null;
  has_ai_scan_cache: boolean;
  ai_scan_started_at: string | null;
  ai_scan_completed_at: string | null;

  // Timestamps
  state_updated_at: string;
  embeddings_started_at: string | null;
  embeddings_completed_at: string | null;

  // Computed fields
  overall_progress: number;
  overall_stage: string;
  is_complete: boolean;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1";

/**
 * Handle 401 Unauthorized by redirecting to login.
 */
function handleUnauthorized() {
  if (typeof window !== "undefined") {
    window.location.href = "/login?error=session_expired";
  }
}

/**
 * Fetch analysis full status from the API.
 */
async function fetchAnalysisFullStatus(
  analysisId: string,
  token: string
): Promise<AnalysisFullStatus> {
  const response = await fetch(
    `${API_BASE_URL}/analyses/${analysisId}/full-status`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    }
  );

  if (!response.ok) {
    // Handle 401 - session expired
    if (response.status === 401) {
      handleUnauthorized();
      throw new Error("Session expired. Please log in again.");
    }
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch analysis status: ${response.status}`);
  }

  return response.json();
}

/**
 * Determine polling interval based on current status.
 * 
 * Smart polling intervals:
 * - Active processing (running): 2 seconds
 * - Pending states: 3 seconds
 * - Completed/failed: stop polling (return false)
 * 
 * **Feature: progress-tracking-refactor, ai-scan-progress-fix**
 * **Validates: Requirements 4.4**
 */
function getPollingInterval(data: AnalysisFullStatus | undefined): number | false {
  if (!data) {
    // Initial load - poll quickly
    return 2000;
  }

  // Stop polling when complete
  if (data.is_complete) {
    return false;
  }

  // Stop polling on terminal failure states
  if (
    data.analysis_status === "failed" &&
    data.embeddings_status !== "running" &&
    data.embeddings_status !== "pending" &&
    data.ai_scan_status !== "running" &&
    data.ai_scan_status !== "pending"
  ) {
    return false;
  }

  // Fast polling during active processing (2s)
  // Includes AI scan running state (Requirements 4.4)
  if (
    data.analysis_status === "running" ||
    data.embeddings_status === "running" ||
    data.semantic_cache_status === "computing" ||
    data.ai_scan_status === "running"
  ) {
    return 2000;
  }

  // Medium polling for pending states (3s)
  // Includes AI scan pending state (Requirements 4.4)
  if (
    data.analysis_status === "pending" ||
    data.embeddings_status === "pending" ||
    data.semantic_cache_status === "pending" ||
    data.ai_scan_status === "pending"
  ) {
    return 3000;
  }

  // Slow polling for other states (e.g., waiting for next phase)
  return 5000;
}

export interface UseAnalysisStatusOptions {
  /** Analysis ID to track. If null, hook is disabled. */
  analysisId: string | null;
  /** Repository ID for cache key organization */
  repositoryId: string;
  /** Authentication token */
  token: string;
  /** Whether the hook is enabled. Defaults to true when analysisId is provided. */
  enabled?: boolean;
}

export interface UseAnalysisStatusResult {
  /** Full status data from the API */
  data: AnalysisFullStatus | undefined;
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Error if the fetch failed */
  error: Error | null;
  /** Whether all processing phases are complete */
  isComplete: boolean;
  /** Overall progress percentage (0-100) */
  overallProgress: number;
  /** Human-readable stage description */
  overallStage: string;
  /** Manually refetch the status */
  refetch: () => void;
  /** Invalidate the cache and refetch */
  invalidate: () => void;
}

/**
 * React Query hook for fetching and polling analysis full status.
 * 
 * Features:
 * - Fetches from /analyses/{id}/full-status endpoint
 * - Smart polling intervals based on status
 * - Stops polling when is_complete is true
 * - Provides computed convenience properties
 * 
 * **Feature: progress-tracking-refactor**
 * **Validates: Requirements 4.4**
 * 
 * @example
 * ```tsx
 * const { data, isLoading, isComplete, overallProgress, overallStage } = useAnalysisStatus({
 *   analysisId: selectedAnalysisId,
 *   repositoryId: repoId,
 *   token: authToken,
 * });
 * 
 * if (isLoading) return <Spinner />;
 * if (isComplete) return <CompletedView data={data} />;
 * return <ProgressView progress={overallProgress} stage={overallStage} />;
 * ```
 */
export function useAnalysisStatus(
  options: UseAnalysisStatusOptions
): UseAnalysisStatusResult {
  const { analysisId, repositoryId, token, enabled = true } = options;
  const queryClient = useQueryClient();

  const queryKey = ["analysis-status", repositoryId, analysisId];

  const query = useQuery({
    queryKey,
    queryFn: () => fetchAnalysisFullStatus(analysisId!, token),
    enabled: enabled && !!analysisId && !!token,
    // Smart polling based on current status
    refetchInterval: (query) => getPollingInterval(query.state.data),
    // Keep data fresh
    staleTime: 1000,
    // Retry on failure
    retry: 2,
    retryDelay: 1000,
  });

  // Invalidate function for manual cache clearing
  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey });
  }, [queryClient, queryKey]);

  // Refetch function
  const refetch = useCallback(() => {
    query.refetch();
  }, [query]);

  // Computed values with defaults
  const isComplete = query.data?.is_complete ?? false;
  const overallProgress = query.data?.overall_progress ?? 0;
  const overallStage = query.data?.overall_stage ?? "Loading...";

  return {
    data: query.data,
    isLoading: query.isLoading,
    error: query.error,
    isComplete,
    overallProgress,
    overallStage,
    refetch,
    invalidate,
  };
}

/**
 * Query key for analysis status - useful for external cache invalidation.
 */
export function getAnalysisStatusQueryKey(repositoryId: string, analysisId: string | null) {
  return ["analysis-status", repositoryId, analysisId];
}

/**
 * Hook that syncs analysis status with the global progress store.
 * 
 * This hook wraps useAnalysisStatus and automatically:
 * - Adds/updates tasks in useAnalysisProgressStore based on status
 * - Removes completed tasks after a delay
 * - Handles analysis, embeddings, and AI scan task tracking
 * 
 * **Feature: progress-tracking-refactor, ai-scan-progress-fix**
 * **Validates: Requirements 4.1, 3.3, 3.4**
 */
export function useAnalysisStatusWithStore(
  options: UseAnalysisStatusOptions
): UseAnalysisStatusResult {
  const result = useAnalysisStatus(options);
  const { analysisId, repositoryId } = options;

  // Import store functions dynamically to avoid circular dependencies
  // This effect syncs the API status with the Zustand store
  useEffect(() => {
    if (!result.data || !analysisId) return;

    // Dynamic import to avoid SSR issues
    import("@/lib/stores/analysis-progress-store").then(
      ({ useAnalysisProgressStore, getAnalysisTaskId, getEmbeddingsTaskId, getAIScanTaskId }) => {
        const store = useAnalysisProgressStore.getState();
        const analysisTaskId = getAnalysisTaskId(repositoryId);
        const embeddingsTaskId = getEmbeddingsTaskId(repositoryId);
        const aiScanTaskId = getAIScanTaskId(repositoryId);

        const data = result.data!;

        // Sync analysis task
        if (data.analysis_status === "running" || data.analysis_status === "pending") {
          if (store.hasTask(analysisTaskId)) {
            store.updateTask(analysisTaskId, {
              status: data.analysis_status === "running" ? "running" : "pending",
              progress: data.analysis_status === "running" ? 50 : 0,
              stage: data.analysis_status,
              message: data.overall_stage,
            });
          }
        } else if (data.analysis_status === "completed") {
          if (store.hasTask(analysisTaskId)) {
            store.updateTask(analysisTaskId, {
              status: "completed",
              progress: 100,
              stage: "completed",
              message: "Analysis complete",
            });
          }
        } else if (data.analysis_status === "failed") {
          if (store.hasTask(analysisTaskId)) {
            store.updateTask(analysisTaskId, {
              status: "failed",
              message: "Analysis failed",
            });
          }
        }

        // Sync embeddings task
        if (data.embeddings_status === "running" || data.embeddings_status === "pending") {
          if (store.hasTask(embeddingsTaskId)) {
            store.updateTask(embeddingsTaskId, {
              status: data.embeddings_status === "running" ? "running" : "pending",
              progress: data.embeddings_progress,
              stage: data.embeddings_stage || data.embeddings_status,
              message: data.embeddings_message,
            });
          } else {
            // Add embeddings task if it doesn't exist but embeddings are running
            store.addTask({
              id: embeddingsTaskId,
              type: "embeddings",
              repositoryId,
              status: data.embeddings_status === "running" ? "running" : "pending",
              progress: data.embeddings_progress,
              stage: data.embeddings_stage || data.embeddings_status,
              message: data.embeddings_message,
            });
          }
        } else if (data.embeddings_status === "completed") {
          if (store.hasTask(embeddingsTaskId)) {
            store.updateTask(embeddingsTaskId, {
              status: "completed",
              progress: 100,
              stage: "completed",
              message: `${data.vectors_count} vectors generated`,
            });
            // Remove completed task after delay
            setTimeout(() => {
              store.removeTask(embeddingsTaskId);
            }, 3000);
          }
        } else if (data.embeddings_status === "failed") {
          if (store.hasTask(embeddingsTaskId)) {
            store.updateTask(embeddingsTaskId, {
              status: "failed",
              message: data.embeddings_error || "Embedding generation failed",
            });
            // Remove failed task after delay
            setTimeout(() => {
              store.removeTask(embeddingsTaskId);
            }, 5000);
          }
        }

        // Sync AI scan task (Requirements 3.3, 3.4)
        // **Feature: ai-scan-progress-fix**
        if (data.ai_scan_status === "running" || data.ai_scan_status === "pending") {
          if (store.hasTask(aiScanTaskId)) {
            store.updateTask(aiScanTaskId, {
              status: data.ai_scan_status === "running" ? "running" : "pending",
              progress: data.ai_scan_progress,
              stage: data.ai_scan_stage || data.ai_scan_status,
              message: data.ai_scan_message,
            });
          } else {
            // Add AI scan task if it doesn't exist but AI scan is running/pending
            store.addTask({
              id: aiScanTaskId,
              type: "ai_scan",
              repositoryId,
              status: data.ai_scan_status === "running" ? "running" : "pending",
              progress: data.ai_scan_progress,
              stage: data.ai_scan_stage || data.ai_scan_status,
              message: data.ai_scan_message,
            });
          }
        } else if (data.ai_scan_status === "completed") {
          if (store.hasTask(aiScanTaskId)) {
            store.updateTask(aiScanTaskId, {
              status: "completed",
              progress: 100,
              stage: "completed",
              message: "AI scan complete",
            });
            // Remove completed task after delay
            setTimeout(() => {
              store.removeTask(aiScanTaskId);
            }, 3000);
          }
        } else if (data.ai_scan_status === "failed") {
          if (store.hasTask(aiScanTaskId)) {
            store.updateTask(aiScanTaskId, {
              status: "failed",
              message: data.ai_scan_error || "AI scan failed",
            });
            // Remove failed task after delay
            setTimeout(() => {
              store.removeTask(aiScanTaskId);
            }, 5000);
          }
        }
        // Note: "skipped" status doesn't need task tracking - it's a terminal state
        // that means AI scan was intentionally not run (disabled in settings)
      }
    );
  }, [result.data, analysisId, repositoryId]);

  return result;
}
