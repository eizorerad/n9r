const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1";

interface RequestOptions extends RequestInit {
  token?: string;
}

class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }

  /**
   * Check if this is a rate limit error (429 or 403 with rate limit message)
   */
  isRateLimitError(): boolean {
    return (
      this.status === 429 ||
      (this.status === 403 && this.message.toLowerCase().includes("rate limit"))
    );
  }

  /**
   * Check if this is a permission error (403 without rate limit)
   */
  isPermissionError(): boolean {
    return this.status === 403 && !this.isRateLimitError();
  }

  /**
   * Check if this is an authentication error (401)
   */
  isAuthenticationError(): boolean {
    return this.status === 401;
  }
}

async function request<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { token, ...fetchOptions } = options;

  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...fetchOptions.headers,
  };

  if (token) {
    (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      error.error?.code || "UNKNOWN_ERROR",
      error.error?.message || response.statusText,
      error.error?.details
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// Auth API
export const authApi = {
  initiateGitHub: (redirectUri: string) =>
    request<{ authorization_url: string }>("/auth/github", {
      method: "POST",
      body: JSON.stringify({ redirect_uri: redirectUri }),
    }),

  callback: (code: string, state: string) =>
    request<{
      access_token: string;
      token_type: string;
      expires_in: number;
      user: {
        id: string;
        username: string;
        email: string | null;
        avatar_url: string | null;
      };
    }>("/auth/github/callback", {
      method: "POST",
      body: JSON.stringify({ code, state }),
    }),

  logout: (token: string) =>
    request<void>("/auth/logout", {
      method: "POST",
      token,
    }),
};

// User API
export const userApi = {
  me: (token: string) =>
    request<{
      id: string;
      github_id: number;
      username: string;
      email: string | null;
      avatar_url: string | null;
      created_at: string;
      organizations: Array<{
        id: string;
        name: string;
        slug: string;
        role: string;
      }>;
    }>("/users/me", { token }),

  update: (token: string, data: { email_notifications?: boolean; weekly_digest?: boolean }) =>
    request("/users/me", {
      method: "PATCH",
      token,
      body: JSON.stringify(data),
    }),
};

// Repository API
export const repositoryApi = {
  list: (
    token: string,
    params?: { org_id?: string; is_active?: boolean; page?: number; per_page?: number }
  ) => {
    const searchParams = new URLSearchParams();
    if (params?.org_id) searchParams.set("org_id", params.org_id);
    if (params?.is_active !== undefined) searchParams.set("is_active", String(params.is_active));
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.per_page) searchParams.set("per_page", String(params.per_page));

    const query = searchParams.toString();
    return request<{
      data: Array<{
        id: string;
        github_id: number;
        name: string;
        full_name: string;
        default_branch: string;
        mode: string;
        is_active: boolean;
        vci_score: number | null;
        tech_debt_level: string | null;
        last_analysis_at: string | null;
        pending_prs_count: number;
        open_issues_count: number;
      }>;
      pagination: {
        page: number;
        per_page: number;
        total: number;
        total_pages: number;
      };
    }>(`/repositories${query ? `?${query}` : ""}`, { token });
  },

  get: (token: string, repoId: string) =>
    request<{
      id: string;
      github_id: number;
      name: string;
      full_name: string;
      default_branch: string;
      mode: string;
      is_active: boolean;
      vci_score: number | null;
      vci_trend: Array<{ date: string; score: number }>;
      tech_debt_level: string | null;
      last_analysis: { id: string; status: string; completed_at: string | null } | null;
      stats: {
        total_analyses: number;
        total_prs_created: number;
        prs_merged: number;
        prs_rejected: number;
      };
      created_at: string;
    }>(`/repositories/${repoId}`, { token }),

  connect: (
    token: string,
    data: { github_id: number; org_id?: string; mode?: string }
  ) =>
    request(`/repositories`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  update: (token: string, repoId: string, data: { mode?: string; is_active?: boolean }) =>
    request(`/repositories/${repoId}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(data),
    }),

  disconnect: (token: string, repoId: string) =>
    request<void>(`/repositories/${repoId}`, {
      method: "DELETE",
      token,
    }),

  available: (token: string) =>
    request<{
      data: Array<{
        github_id: number;
        name: string;
        full_name: string;
        private: boolean;
        default_branch: string;
        is_connected: boolean;
      }>;
    }>("/repositories/available", { token }),
};

// Health API
export const healthApi = {
  check: () => request<{ status: string }>("/health"),
  ready: () => request<{ status: string }>("/health/ready"),
};

// Issues API
export const issuesApi = {
  list: (token: string, repositoryId: string, params?: { status?: string; severity?: string; type?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.severity) searchParams.set("severity", params.severity);
    if (params?.type) searchParams.set("type", params.type);
    const query = searchParams.toString();
    return request<{
      data: Array<{
        id: string;
        type: string;
        severity: string;
        title: string;
        description: string | null;
        file_path: string | null;
        line_start: number | null;
        line_end: number | null;
        confidence: number;
        status: string;
        auto_fixable: boolean;
        created_at: string;
      }>;
      total: number;
    }>(`/repositories/${repositoryId}/issues${query ? `?${query}` : ""}`, { token });
  },

  get: (token: string, issueId: string) =>
    request<{
      id: string;
      type: string;
      severity: string;
      title: string;
      description: string | null;
      file_path: string | null;
      line_start: number | null;
      line_end: number | null;
      metadata: Record<string, unknown> | null;
      confidence: number;
      status: string;
      auto_fixable: boolean;
      created_at: string;
    }>(`/issues/${issueId}`, { token }),

  update: (token: string, issueId: string, data: { status?: string }) =>
    request<{ id: string; status: string }>(`/issues/${issueId}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(data),
    }),

  fix: (token: string, issueId: string) =>
    request<{
      auto_pr_id: string;
      issue_id: string;
      task_id: string;
      status: string;
      message: string;
    }>(`/issues/${issueId}/fix`, {
      method: "POST",
      token,
    }),
};

// Auto-PR API
export const autoPrApi = {
  list: (token: string, repositoryId: string, params?: { status?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    const query = searchParams.toString();
    return request<{
      data: Array<{
        id: string;
        title: string;
        description: string | null;
        status: string;
        pr_number: number | null;
        pr_url: string | null;
        branch_name: string | null;
        files_changed: number | null;
        created_at: string;
      }>;
    }>(`/repositories/${repositoryId}/auto-prs${query ? `?${query}` : ""}`, { token });
  },

  get: (token: string, prId: string) =>
    request<{
      id: string;
      repository_id: string;
      issue_id: string | null;
      title: string;
      description: string | null;
      status: string;
      pr_number: number | null;
      pr_url: string | null;
      branch_name: string | null;
      base_branch: string | null;
      files_changed: number | null;
      additions: number | null;
      deletions: number | null;
      diff: string | null;
      test_status: string | null;
      test_output: string | null;
      review_feedback: string | null;
      created_at: string;
      merged_at: string | null;
    }>(`/auto-prs/${prId}`, { token }),

  approve: (token: string, prId: string) =>
    request<{ id: string; status: string; message: string }>(`/auto-prs/${prId}/approve`, {
      method: "POST",
      token,
    }),

  reject: (token: string, prId: string, feedback?: string) =>
    request<{ id: string; status: string }>(`/auto-prs/${prId}/reject`, {
      method: "POST",
      token,
      body: JSON.stringify({ feedback }),
    }),

  revise: (token: string, prId: string, feedback: string) =>
    request<{ id: string; status: string; task_id: string; message: string }>(`/auto-prs/${prId}/revise`, {
      method: "POST",
      token,
      body: JSON.stringify({ feedback }),
    }),
};

// Branch and Commit Types (Requirements: 1.1, 2.1, 2.2, 3.1, 3.2)
export interface Branch {
  name: string;
  commit_sha: string;
  is_default: boolean;
  is_protected: boolean;
}

export interface Commit {
  sha: string;
  short_sha: string;
  message: string;
  message_headline: string;
  author_name: string;
  author_login: string | null;
  author_avatar_url: string | null;
  committed_at: string;
  analysis_id: string | null;
  vci_score: number | null;
  analysis_status: string | null;
}

// Branch and Commit API (Requirements: 1.1, 2.1, 4.1)
export const branchApi = {
  /**
   * Fetch branches for a repository
   * Requirements: 1.1
   */
  list: (token: string, repositoryId: string) =>
    request<{ data: Branch[] }>(`/repositories/${repositoryId}/branches`, { token }),
};

export const commitApi = {
  /**
   * Fetch commits for a repository branch
   * Requirements: 2.1
   */
  list: (
    token: string,
    repositoryId: string,
    params?: { branch?: string; per_page?: number }
  ) => {
    const searchParams = new URLSearchParams();
    if (params?.branch) searchParams.set("branch", params.branch);
    if (params?.per_page) searchParams.set("per_page", String(params.per_page));
    const query = searchParams.toString();
    return request<{ commits: Commit[]; branch: string }>(
      `/repositories/${repositoryId}/commits${query ? `?${query}` : ""}`,
      { token }
    );
  },

  /**
   * Trigger analysis for a specific commit
   * Requirements: 4.1
   */
  triggerAnalysis: (token: string, repositoryId: string, commitSha: string) =>
    request<{
      id: string;
      repository_id: string;
      commit_sha: string;
      status: string;
      created_at: string;
    }>(`/repositories/${repositoryId}/analyses`, {
      method: "POST",
      token,
      body: JSON.stringify({ commit_sha: commitSha }),
    }),
};

export { ApiError };
