/**
 * Semantic Code Analysis API client
 * 
 * Provides access to vector-based code understanding features:
 * - Semantic search
 * - Related code detection
 * - Architecture health
 * - Similar code detection
 * - Refactoring suggestions
 * - Tech debt heatmap
 * - Style consistency
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1";

// Types
export interface SemanticSearchResult {
  file_path: string;
  name: string | null;
  chunk_type: string | null;
  line_start: number | null;
  line_end: number | null;
  content: string | null;
  similarity: number;
  qualified_name: string | null;
  language: string | null;
  content_truncated: boolean;  // Indicates if content was truncated at 2000 chars
  full_content_length: number | null;  // Original content length before truncation
}

export interface SemanticSearchResponse {
  query: string;
  results: SemanticSearchResult[];
  total: number;
  resolved_commit_sha: string | null;  // Actual commit SHA used for query
  requested_ref: string | null;  // Original ref requested by user
}

export interface ClusterInfo {
  id: number;
  name: string;
  file_count: number;
  chunk_count: number;
  cohesion: number;
  top_files: string[];
  dominant_language: string | null;
  status: string;
}

export interface OutlierInfo {
  file_path: string;
  chunk_name: string | null;
  chunk_type: string | null;
  nearest_similarity: number;
  nearest_file: string | null;
  suggestion: string;
  confidence: number;
  confidence_factors: string[];
  tier: string;
}

export interface CouplingHotspot {
  file_path: string;
  clusters_connected: number;
  cluster_names: string[];
  suggestion: string;
}

export interface ArchitectureHealthResponse {
  overall_score: number;
  clusters: ClusterInfo[];
  outliers: OutlierInfo[];
  coupling_hotspots: CouplingHotspot[];
  total_chunks: number;
  total_files: number;
  metrics: {
    avg_cohesion?: number;
    outlier_percentage?: number;
    cluster_count?: number;
  };
}

export interface SimilarCodeGroup {
  similarity: number;
  suggestion: string;
  chunks: Array<{
    file: string;
    name: string;
    lines: [number, number];
    chunk_type: string;
  }>;
}

export interface SimilarCodeResponse {
  groups: SimilarCodeGroup[];
  total_groups: number;
  potential_loc_reduction: number;
}

export interface RefactoringSuggestion {
  type: string;
  file: string | null;
  target: string | null;
  reason: string;
  impact: string;
  details: Record<string, unknown> | null;
}

export interface RefactoringSuggestionsResponse {
  suggestions: RefactoringSuggestion[];
  total: number;
}

export interface TechDebtHotspot {
  file_path: string;
  complexity: number | null;
  cohesion: number | null;
  bridges_clusters: number;
  risk: string;
  suggestion: string;
}

export interface TechDebtByCluster {
  cluster: string;
  avg_complexity: number;
  cohesion: number;
  health: string;
}

export interface TechDebtHeatmapResponse {
  debt_score: number;
  hotspots: TechDebtHotspot[];
  by_cluster: TechDebtByCluster[];
}

export interface StyleIssue {
  type: string;
  message: string;
  reference_file: string | null;
  reference_lines: number[] | null;
}

export interface StyleConsistencyResponse {
  file: string;
  overall_consistency: number;
  analysis: Record<string, number>;
  issues: StyleIssue[];
  suggestions: string[];
}

export interface RelatedCodeResult {
  file_path: string;
  name: string | null;
  chunk_type: string | null;
  line_start: number | null;
  line_end: number | null;
  similarity: number;
  cluster: string | null;
  qualified_name: string | null;
}

export interface RelatedCodeResponse {
  query_file: string;
  cluster: string | null;
  related: RelatedCodeResult[];
}

/**
 * Handle 401 Unauthorized by redirecting to login.
 */
function handleUnauthorized() {
  if (typeof window !== "undefined") {
    window.location.href = "/login?error=session_expired";
  }
}

// API Client
async function request<T>(
  endpoint: string,
  token: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  });

  if (!response.ok) {
    // Handle 401 - session expired
    if (response.status === 401) {
      handleUnauthorized();
      throw new Error("Session expired. Please log in again.");
    }
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || response.statusText);
  }

  return response.json();
}

export const semanticApi = {
  // Semantic search
  search: (token: string, repositoryId: string, query: string, limit = 10) =>
    request<SemanticSearchResponse>(
      `/repositories/${repositoryId}/semantic-search?q=${encodeURIComponent(query)}&limit=${limit}`,
      token
    ),

  // Related code
  relatedCode: (token: string, repositoryId: string, file: string, limit = 10) =>
    request<RelatedCodeResponse>(
      `/repositories/${repositoryId}/related-code?file=${encodeURIComponent(file)}&limit=${limit}`,
      token
    ),

  // Architecture health
  architectureHealth: (token: string, repositoryId: string) =>
    request<ArchitectureHealthResponse>(
      `/repositories/${repositoryId}/architecture-health`,
      token
    ),

  // Outliers
  outliers: (token: string, repositoryId: string) =>
    request<{ outliers: OutlierInfo[]; total_outliers: number; percentage: number }>(
      `/repositories/${repositoryId}/outliers`,
      token
    ),

  // Similar code
  similarCode: (token: string, repositoryId: string, threshold = 0.85, limit = 20) =>
    request<SimilarCodeResponse>(
      `/repositories/${repositoryId}/similar-code?threshold=${threshold}&limit=${limit}`,
      token
    ),

  // Refactoring suggestions
  refactoringSuggestions: (token: string, repositoryId: string) =>
    request<RefactoringSuggestionsResponse>(
      `/repositories/${repositoryId}/refactoring-suggestions`,
      token
    ),

  // Tech debt heatmap
  techDebtHeatmap: (token: string, repositoryId: string) =>
    request<TechDebtHeatmapResponse>(
      `/repositories/${repositoryId}/tech-debt-heatmap`,
      token
    ),

  // Style consistency
  styleConsistency: (token: string, repositoryId: string, file: string) =>
    request<StyleConsistencyResponse>(
      `/repositories/${repositoryId}/style-consistency?file=${encodeURIComponent(file)}`,
      token
    ),

  // Placement suggestion
  suggestPlacement: (token: string, repositoryId: string, file: string) =>
    request<{
      current_location: string;
      current_cluster: string | null;
      suggested_cluster: string | null;
      similar_files: RelatedCodeResult[];
      suggestion: string | null;
    }>(
      `/repositories/${repositoryId}/suggest-placement?file=${encodeURIComponent(file)}`,
      token
    ),
};
