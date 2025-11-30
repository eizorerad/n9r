"use client";

import { useMemo, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type ColumnFiltersState,
} from "@tanstack/react-table";
import { ArrowUpDown, MoreHorizontal, GitBranch, AlertCircle, GitPullRequest } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Repository {
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
}

interface RepositoriesTableProps {
  data: Repository[];
  isLoading?: boolean;
  onRowClick?: (repo: Repository) => void;
}

function getVCIColor(score: number | null): string {
  if (score === null) return "text-gray-400";
  if (score >= 80) return "text-green-500";
  if (score >= 60) return "text-yellow-500";
  if (score >= 40) return "text-orange-500";
  return "text-red-500";
}

function getVCIBgColor(score: number | null): string {
  if (score === null) return "bg-gray-500/10";
  if (score >= 80) return "bg-green-500/10";
  if (score >= 60) return "bg-yellow-500/10";
  if (score >= 40) return "bg-orange-500/10";
  return "bg-red-500/10";
}

export function RepositoriesTable({ data, isLoading, onRowClick }: RepositoriesTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  const columns = useMemo<ColumnDef<Repository>[]>(
    () => [
      {
        accessorKey: "full_name",
        header: ({ column }) => (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="p-0 hover:bg-transparent"
          >
            Repository
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        ),
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-gray-400" />
            <div>
              <div className="font-medium">{row.original.full_name}</div>
              <div className="text-xs text-gray-500">{row.original.default_branch}</div>
            </div>
          </div>
        ),
      },
      {
        accessorKey: "vci_score",
        header: ({ column }) => (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="p-0 hover:bg-transparent"
          >
            VCI Score
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        ),
        cell: ({ row }) => {
          const score = row.original.vci_score;
          return (
            <div
              className={cn(
                "inline-flex items-center px-2.5 py-0.5 rounded-full text-sm font-medium",
                getVCIBgColor(score),
                getVCIColor(score)
              )}
            >
              {score !== null ? score.toFixed(0) : "—"}
            </div>
          );
        },
      },
      {
        accessorKey: "tech_debt_level",
        header: "Tech Debt",
        cell: ({ row }) => {
          const level = row.original.tech_debt_level;
          const colors: Record<string, string> = {
            low: "text-green-500",
            moderate: "text-yellow-500",
            high: "text-orange-500",
            critical: "text-red-500",
          };
          return (
            <span className={cn("capitalize", colors[level ?? ""] || "text-gray-400")}>
              {level || "—"}
            </span>
          );
        },
      },
      {
        accessorKey: "mode",
        header: "Mode",
        cell: ({ row }) => (
          <span
            className={cn(
              "inline-flex px-2 py-1 rounded text-xs font-medium",
              row.original.mode === "auto_fix"
                ? "bg-green-500/10 text-green-500"
                : row.original.mode === "assisted"
                ? "bg-blue-500/10 text-blue-500"
                : "bg-gray-500/10 text-gray-400"
            )}
          >
            {row.original.mode === "auto_fix"
              ? "Auto-Fix"
              : row.original.mode === "assisted"
              ? "Assisted"
              : "View Only"}
          </span>
        ),
      },
      {
        accessorKey: "open_issues_count",
        header: "Issues",
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <AlertCircle className="h-4 w-4 text-gray-400" />
            <span>{row.original.open_issues_count}</span>
          </div>
        ),
      },
      {
        accessorKey: "pending_prs_count",
        header: "Pending PRs",
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <GitPullRequest className="h-4 w-4 text-gray-400" />
            <span>{row.original.pending_prs_count}</span>
          </div>
        ),
      },
      {
        id: "actions",
        cell: ({ row }) => (
          <Button variant="ghost" size="icon" onClick={(e) => e.stopPropagation()}>
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        ),
      },
    ],
    []
  );

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      columnFilters,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  if (isLoading) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900/50">
        <div className="p-8 text-center text-gray-400">Loading repositories...</div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/50 overflow-hidden">
      <table className="w-full">
        <thead className="bg-gray-800/50">
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  className="px-4 py-3 text-left text-sm font-medium text-gray-400"
                >
                  {header.isPlaceholder
                    ? null
                    : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-gray-400">
                No repositories found
              </td>
            </tr>
          ) : (
            table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => onRowClick?.(row.original)}
                className="border-t border-gray-800 hover:bg-gray-800/30 cursor-pointer transition-colors"
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-4 py-3 text-sm">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>

      {/* Pagination */}
      <div className="flex items-center justify-between px-4 py-3 border-t border-gray-800">
        <div className="text-sm text-gray-400">
          {table.getFilteredRowModel().rows.length} repositories
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
