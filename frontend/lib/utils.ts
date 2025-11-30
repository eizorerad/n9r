import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function getVCIStatusColor(score: number): string {
  if (score >= 80) return "text-vci-healthy";
  if (score >= 60) return "text-vci-attention";
  if (score >= 40) return "text-vci-problems";
  return "text-vci-critical";
}

export function getVCIStatusLabel(score: number): string {
  if (score >= 80) return "Healthy";
  if (score >= 60) return "Attention";
  if (score >= 40) return "Problems";
  return "Critical";
}
