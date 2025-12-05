"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { repositoryApi, ApiError } from "@/lib/api";
import { useCallback } from "react";

/**
 * Hook to get current auth token
 * In production, this should use a proper auth context
 */
function useToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("n9r_token");
}

// Types for file browser
export interface FileItem {
  name: string;
  path: string;
  type: "file" | "directory";
  size: number | null;
}

export interface FileContent {
  path: string;
  content: string;
  encoding: string;
  size: number;
  language: string | null;
}

// Query key factories for consistent caching
export const fileBrowserKeys = {
  all: (repoId: string) => ["repository-files", repoId] as const,
  directory: (repoId: string, path: string, ref?: string) =>
    ["repository-files", repoId, "dir", path, ref] as const,
  content: (repoId: string, filePath: string, ref?: string) =>
    ["repository-files", repoId, "content", filePath, ref] as const,
};

/**
 * Fetch files for a directory in a repository
 * 
 * @param repoId - Repository UUID
 * @param path - Directory path (empty string for root)
 * @param ref - Git reference (branch/tag/commit), defaults to repo's default branch
 * @param options.enabled - Whether the query should run
 * 
 * @example
 * // Fetch root directory
 * const { data, isLoading, error } = useRepositoryFiles(repoId, "");
 * 
 * // Fetch subdirectory on a specific branch
 * const { data } = useRepositoryFiles(repoId, "src/components", "develop");
 */
export function useRepositoryFiles(
  repoId: string,
  path: string = "",
  ref?: string,
  options?: { enabled?: boolean }
) {
  const token = useToken();

  // Debug enabled condition
  const isEnabled = options?.enabled !== false && !!token && !!repoId;
  console.log('[useRepositoryFiles]', {
    repoId,
    path,
    ref,
    hasToken: !!token,
    isEnabled,
  });

  return useQuery({
    queryKey: fileBrowserKeys.directory(repoId, path, ref),
    queryFn: async () => {
      const response = await repositoryApi.files(token!, repoId, { path, ref });
      return response.data;
    },
    enabled: options?.enabled !== false && !!token && !!repoId,
    staleTime: 60 * 1000, // 1 minute - directory contents don't change often
    gcTime: 10 * 60 * 1000, // Keep in cache for 10 minutes
    retry: (failureCount, error) => {
      // Don't retry on permission/auth errors
      if (error instanceof ApiError) {
        if (error.isAuthenticationError() || error.isPermissionError()) {
          return false;
        }
        // Retry rate limit after delay
        if (error.isRateLimitError()) {
          return failureCount < 2;
        }
      }
      return failureCount < 3;
    },
    retryDelay: (attemptIndex, error) => {
      // Longer delay for rate limits
      if (error instanceof ApiError && error.isRateLimitError()) {
        return Math.min(30000, 10000 * (attemptIndex + 1));
      }
      return Math.min(1000 * 2 ** attemptIndex, 10000);
    },
  });
}

/**
 * Fetch content of a specific file
 * 
 * @param repoId - Repository UUID
 * @param filePath - Path to file (null to disable query)
 * @param ref - Git reference
 * 
 * @example
 * const { data, isLoading, error } = useFileContent(repoId, selectedFile);
 */
export function useFileContent(
  repoId: string,
  filePath: string | null,
  ref?: string
) {
  const token = useToken();

  return useQuery({
    queryKey: fileBrowserKeys.content(repoId, filePath || "", ref),
    queryFn: async () => {
      const response = await repositoryApi.fileContent(token!, repoId, filePath!, ref);
      return response;
    },
    enabled: !!token && !!repoId && !!filePath,
    staleTime: 5 * 60 * 1000, // 5 minutes - file content rarely changes during session
    gcTime: 15 * 60 * 1000, // Keep in cache for 15 minutes
    retry: (failureCount, error) => {
      if (error instanceof ApiError) {
        // Don't retry on 4xx errors (auth, permission, bad request for binary files)
        if (error.status >= 400 && error.status < 500) {
          return false;
        }
      }
      return failureCount < 2;
    },
  });
}

/**
 * Hook to prefetch directory contents
 * Useful for prefetching on hover
 */
export function usePrefetchDirectory() {
  const token = useToken();
  const queryClient = useQueryClient();

  return useCallback(
    (repoId: string, path: string, ref?: string) => {
      if (!token) return;

      queryClient.prefetchQuery({
        queryKey: fileBrowserKeys.directory(repoId, path, ref),
        queryFn: async () => {
          const response = await repositoryApi.files(token, repoId, { path, ref });
          return response.data;
        },
        staleTime: 60 * 1000,
      });
    },
    [token, queryClient]
  );
}

/**
 * Hook to invalidate file browser cache
 * Useful when changing branches or after file modifications
 */
export function useInvalidateFileBrowser() {
  const queryClient = useQueryClient();

  return useCallback(
    (repoId: string) => {
      queryClient.invalidateQueries({
        queryKey: fileBrowserKeys.all(repoId),
      });
    },
    [queryClient]
  );
}

/**
 * Hook for managing expanded directories state with lazy loading
 * Returns the full file tree built from cached directory queries
 */
export function useFileTree(repoId: string, ref?: string) {
  const token = useToken();
  const queryClient = useQueryClient();

  // Debug logging
  console.log('[useFileTree Debug]', {
    repoId,
    ref,
    hasToken: !!token,
  });

  // Fetch root directory
  const rootQuery = useRepositoryFiles(repoId, "", ref);

  // Debug query state
  console.log('[useFileTree Query]', {
    data: rootQuery.data?.length,
    isLoading: rootQuery.isLoading,
    isFetching: rootQuery.isFetching,
    error: rootQuery.error?.message,
    status: rootQuery.status,
  });

  /**
   * Load children for a directory
   * This triggers a new query that gets cached
   */
  const loadDirectory = useCallback(
    async (path: string) => {
      if (!token) return;

      await queryClient.fetchQuery({
        queryKey: fileBrowserKeys.directory(repoId, path, ref),
        queryFn: async () => {
          const response = await repositoryApi.files(token, repoId, { path, ref });
          return response.data;
        },
        staleTime: 60 * 1000,
      });
    },
    [token, queryClient, repoId, ref]
  );

  /**
   * Get cached children for a path, or undefined if not loaded
   */
  const getDirectoryChildren = useCallback(
    (path: string): FileItem[] | undefined => {
      return queryClient.getQueryData(fileBrowserKeys.directory(repoId, path, ref));
    },
    [queryClient, repoId, ref]
  );

  /**
   * Check if a directory is currently loading
   */
  const isDirectoryLoading = useCallback(
    (path: string): boolean => {
      const state = queryClient.getQueryState(fileBrowserKeys.directory(repoId, path, ref));
      return state?.fetchStatus === "fetching";
    },
    [queryClient, repoId, ref]
  );

  return {
    rootFiles: rootQuery.data,
    isLoading: rootQuery.isLoading,
    error: rootQuery.error,
    refetch: rootQuery.refetch,
    loadDirectory,
    getDirectoryChildren,
    isDirectoryLoading,
  };
}

/**
 * Hook to fetch repository files with explicit token
 * Use this when the token comes from server component props
 */
export function useRepositoryFilesWithToken(
  repoId: string,
  token: string,
  path: string = "",
  ref?: string
) {
  return useQuery({
    queryKey: fileBrowserKeys.directory(repoId, path, ref),
    queryFn: async () => {
      const response = await repositoryApi.files(token, repoId, { path, ref });
      return response.data;
    },
    enabled: !!token && !!repoId,
    staleTime: 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
}

/**
 * Hook to fetch file content with explicit token
 * Use this when the token comes from server component props
 */
export function useFileContentWithToken(
  repoId: string,
  token: string,
  filePath: string | null,
  ref?: string
) {
  return useQuery({
    queryKey: fileBrowserKeys.content(repoId, filePath || "", ref),
    queryFn: async () => {
      const response = await repositoryApi.fileContent(token, repoId, filePath!, ref);
      return response;
    },
    enabled: !!token && !!repoId && !!filePath,
    staleTime: 5 * 60 * 1000,
    gcTime: 15 * 60 * 1000,
  });
}

/**
 * Hook for managing file tree with explicit token
 * Use this when the token comes from server component props
 */
export function useFileTreeWithToken(repoId: string, token: string, ref?: string) {
  const queryClient = useQueryClient();

  // Debug logging
  console.log('[useFileTreeWithToken Debug]', {
    repoId,
    ref,
    hasToken: !!token,
  });

  // Fetch root directory
  const rootQuery = useRepositoryFilesWithToken(repoId, token, "", ref);

  // Debug query state
  console.log('[useFileTreeWithToken Query]', {
    data: rootQuery.data?.length,
    isLoading: rootQuery.isLoading,
    isFetching: rootQuery.isFetching,
    error: rootQuery.error?.message,
    status: rootQuery.status,
  });

  /**
   * Load children for a directory
   */
  const loadDirectory = useCallback(
    async (path: string) => {
      if (!token) return;

      await queryClient.fetchQuery({
        queryKey: fileBrowserKeys.directory(repoId, path, ref),
        queryFn: async () => {
          const response = await repositoryApi.files(token, repoId, { path, ref });
          return response.data;
        },
        staleTime: 60 * 1000,
      });
    },
    [token, queryClient, repoId, ref]
  );

  /**
   * Check if a directory is currently loading
   */
  const isDirectoryLoading = useCallback(
    (path: string): boolean => {
      const state = queryClient.getQueryState(fileBrowserKeys.directory(repoId, path, ref));
      return state?.fetchStatus === "fetching";
    },
    [queryClient, repoId, ref]
  );

  return {
    rootFiles: rootQuery.data,
    isLoading: rootQuery.isLoading,
    error: rootQuery.error,
    refetch: rootQuery.refetch,
    loadDirectory,
    isDirectoryLoading,
  };
}
