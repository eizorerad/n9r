"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { repositoryApi } from "@/lib/api";

// Hook to get current auth token (simplified - in real app use auth context)
function useToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("n9r_token");
}

export function useRepositories(params?: {
  org_id?: string;
  is_active?: boolean;
  page?: number;
  per_page?: number;
}) {
  const token = useToken();

  return useQuery({
    queryKey: ["repositories", params],
    queryFn: () => repositoryApi.list(token!, params),
    enabled: !!token,
    staleTime: 60 * 1000,
  });
}

export function useRepository(repoId: string) {
  const token = useToken();

  return useQuery({
    queryKey: ["repository", repoId],
    queryFn: () => repositoryApi.get(token!, repoId),
    enabled: !!token && !!repoId,
  });
}

export function useAvailableRepositories() {
  const token = useToken();

  return useQuery({
    queryKey: ["repositories", "available"],
    queryFn: () => repositoryApi.available(token!),
    enabled: !!token,
  });
}

export function useConnectRepository() {
  const token = useToken();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { github_id: number; org_id?: string; mode?: string }) =>
      repositoryApi.connect(token!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
}

export function useUpdateRepository() {
  const token = useToken();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ repoId, data }: { repoId: string; data: { mode?: string; is_active?: boolean } }) =>
      repositoryApi.update(token!, repoId, data),
    onSuccess: (_, { repoId }) => {
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
      queryClient.invalidateQueries({ queryKey: ["repository", repoId] });
    },
  });
}

export function useDisconnectRepository() {
  const token = useToken();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (repoId: string) => repositoryApi.disconnect(token!, repoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
}
